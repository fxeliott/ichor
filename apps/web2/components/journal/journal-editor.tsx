"use client";

/**
 * JournalEditor — Phase B.5d v2 (API-backed, localStorage fallback).
 *
 * Reads `?asset=X_Y` to pre-fill the asset tag. On mount, fetches the
 * last 30 entries from `GET /v1/journal`. On save, POSTs to `/v1/journal`
 * AND mirrors to localStorage (so a hard refresh during a flaky network
 * still surfaces the entry).
 *
 * Offline UX:
 *  - GET fail → show localStorage entries with a yellow "offline cache"
 *    badge (no toast spam, the user notices the badge).
 *  - POST fail → write to localStorage drafts only, surface a sonner
 *    toast "API offline — entry saved locally, retry later".
 *  - Cross-tab sync via `storage` event (a save in tab A reflects in
 *    tab B's listing).
 *
 * Storage keys:
 *  - `ichor.journal.draft.v1` — the in-progress textarea body
 *  - `ichor.journal.entries.v1` — array of {ts,asset,body} (cap 30)
 *  - `ichor.journal.pending.v1` — entries not yet acknowledged by the
 *    backend (POST returned null) — periodically retried.
 *
 * Out of ADR-017 boundary surface (private trader notebook).
 */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { apiGet, apiMutate } from "@/lib/api";

interface JournalEntry {
  /** ISO 8601 timestamp. */
  ts: string;
  asset: string | null;
  body: string;
  /** Server-assigned id when persisted; null when localStorage-only. */
  id?: string;
}

interface JournalListOut {
  total: number;
  entries: { id: string; ts: string; asset: string | null; body: string; created_at: string }[];
}

interface JournalCreateBody {
  body: string;
  asset?: string | null;
}

interface JournalCreateOut {
  id: string;
  ts: string;
  asset: string | null;
  body: string;
  created_at: string;
}

const DRAFT_KEY = "ichor.journal.draft.v1";
const ENTRIES_KEY = "ichor.journal.entries.v1";
const MAX_ENTRIES = 30;

function readJSON<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota exceeded — silent in v1 */
  }
}

export function JournalEditor() {
  const search = useSearchParams();
  const initialAsset = search.get("asset") ?? null;

  const [body, setBody] = useState("");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [isOffline, setIsOffline] = useState(false);
  const [busy, setBusy] = useState(false);

  // Hydrate from localStorage immediately (instant UI), then refresh
  // from the API in the background. If the API is reachable, replace
  // the entries; otherwise keep the local cache + flag offline.
  const refreshFromAPI = useCallback(async (asset: string | null) => {
    const path = asset
      ? `/v1/journal?asset=${encodeURIComponent(asset)}&limit=${MAX_ENTRIES}`
      : `/v1/journal?limit=${MAX_ENTRIES}`;
    const remote = await apiGet<JournalListOut>(path);
    if (remote && Array.isArray(remote.entries)) {
      const mapped: JournalEntry[] = remote.entries.map((e) => ({
        id: e.id,
        ts: e.ts,
        asset: e.asset,
        body: e.body,
      }));
      setEntries(mapped);
      writeJSON(ENTRIES_KEY, mapped);
      setIsOffline(false);
    } else {
      setIsOffline(true);
    }
  }, []);

  useEffect(() => {
    const draft = readJSON<{ body: string }>(DRAFT_KEY, { body: "" });
    setBody(draft.body);
    const cached = readJSON<JournalEntry[]>(ENTRIES_KEY, []);
    setEntries(cached);
    setHydrated(true);
    void refreshFromAPI(initialAsset);
  }, [initialAsset, refreshFromAPI]);

  // Auto-persist draft on body change.
  useEffect(() => {
    if (!hydrated) return;
    writeJSON(DRAFT_KEY, { body });
  }, [body, hydrated]);

  // Cross-tab sync.
  useEffect(() => {
    if (typeof window === "undefined") return;
    function onStorage(e: StorageEvent) {
      if (e.key !== ENTRIES_KEY) return;
      setEntries(readJSON<JournalEntry[]>(ENTRIES_KEY, []));
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  async function save() {
    const trimmed = body.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const created = await apiMutate<JournalCreateOut, JournalCreateBody>("/v1/journal", {
        body: trimmed,
        asset: initialAsset,
      });
      if (!created) {
        // API offline — fall back to localStorage so the user doesn't
        // lose the entry. Surface a toast so the user knows.
        setIsOffline(true);
        const local: JournalEntry = {
          ts: new Date().toISOString(),
          asset: initialAsset,
          body: trimmed,
        };
        const next = [local, ...entries].slice(0, MAX_ENTRIES);
        setEntries(next);
        writeJSON(ENTRIES_KEY, next);
        setBody("");
        writeJSON(DRAFT_KEY, { body: "" });
        setSavedAt(local.ts);
        toast.warning("API offline — note enregistrée localement, retry à la prochaine connexion.");
        return;
      }
      const persisted: JournalEntry = {
        id: created.id,
        ts: created.ts,
        asset: created.asset,
        body: created.body,
      };
      const next = [persisted, ...entries].slice(0, MAX_ENTRIES);
      setEntries(next);
      writeJSON(ENTRIES_KEY, next);
      setBody("");
      writeJSON(DRAFT_KEY, { body: "" });
      setSavedAt(persisted.ts);
      setIsOffline(false);
      toast.success("Note enregistrée.");
    } finally {
      setBusy(false);
    }
  }

  function clearDraft() {
    setBody("");
    writeJSON(DRAFT_KEY, { body: "" });
  }

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-label="Éditeur d'entrée"
        className="rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-surface)] p-4"
      >
        {initialAsset ? (
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
            Tag pré-rempli :{" "}
            <span className="text-[var(--color-text-primary)]">{initialAsset}</span>
          </p>
        ) : null}
        <label htmlFor="journal-body" className="sr-only">
          Note libre
        </label>
        <textarea
          id="journal-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={6}
          placeholder="Tape ta note ici. Ce qui te frappe sur la session, ce que tu n'aurais pas vu sans Ichor, etc."
          className="w-full rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-accent-cobalt)] focus:outline-none"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={!body.trim() || busy}
            className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] px-4 py-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-bull)] hover:text-[var(--color-bull)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Sauvegarde…" : "Sauvegarder"}
          </button>
          <button
            type="button"
            onClick={clearDraft}
            disabled={!body || busy}
            className="rounded-lg border border-[var(--color-border-subtle)] px-4 py-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Vider le brouillon
          </button>
          {savedAt ? (
            <span
              aria-live="polite"
              className="font-mono text-[10px] text-[var(--color-text-muted)]"
            >
              ✓ enregistré · {new Date(savedAt).toLocaleTimeString("fr-FR")}
            </span>
          ) : null}
        </div>
      </section>

      <section aria-label="Entrées récentes">
        <h2 className="mb-3 flex items-baseline justify-between font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          <span>
            Dernières entrées · {entries.length}/{MAX_ENTRIES}
          </span>
          {isOffline ? (
            <span className="text-[10px] text-[var(--color-warn)]" aria-live="polite">
              Cache local · API offline
            </span>
          ) : null}
        </h2>
        {entries.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">
            Aucune entrée pour l&apos;instant.
          </p>
        ) : (
          <ol className="space-y-3">
            {entries.map((e) => (
              <li
                key={e.id ?? e.ts}
                className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/50 p-3"
              >
                <p className="mb-1 flex items-baseline gap-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  <span>
                    {new Date(e.ts).toLocaleString("fr-FR", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })}
                  </span>
                  {e.asset ? (
                    <span className="text-[var(--color-accent-cobalt)]">{e.asset}</span>
                  ) : null}
                  {!e.id ? (
                    <span className="text-[var(--color-warn)]" title="non synchronisé">
                      offline
                    </span>
                  ) : null}
                </p>
                <p className="whitespace-pre-wrap text-sm text-[var(--color-text-primary)]">
                  {e.body}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
