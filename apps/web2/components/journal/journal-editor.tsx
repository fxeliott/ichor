"use client";

/**
 * JournalEditor — minimal drafts-in-localStorage editor (Phase B.5d v1).
 *
 * Reads `?asset=X_Y` to pre-fill the asset tag. Persists draft text +
 * tag set under `ichor.journal.draft`. Save (Enter or button) appends to
 * `ichor.journal.entries` (cap 30).
 *
 * No backend yet — Phase B.5d v2 will replace `appendEntry` with a
 * POST /v1/journal call and surface conflict resolution.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

interface JournalEntry {
  ts: string; // ISO
  asset: string | null;
  body: string;
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
    /* quota exceeded — silent for now, will surface via toast in v2 */
  }
}

export function JournalEditor() {
  const search = useSearchParams();
  const initialAsset = search.get("asset") ?? null;

  const [body, setBody] = useState("");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const draft = readJSON<{ body: string }>(DRAFT_KEY, { body: "" });
    setBody(draft.body);
    setEntries(readJSON<JournalEntry[]>(ENTRIES_KEY, []));
    setHydrated(true);
  }, []);

  // Auto-persist draft on body change (debounced via React batching).
  useEffect(() => {
    if (!hydrated) return;
    writeJSON(DRAFT_KEY, { body });
  }, [body, hydrated]);

  function save() {
    const trimmed = body.trim();
    if (!trimmed) return;
    const entry: JournalEntry = {
      ts: new Date().toISOString(),
      asset: initialAsset,
      body: trimmed,
    };
    const next = [entry, ...entries].slice(0, MAX_ENTRIES);
    writeJSON(ENTRIES_KEY, next);
    setEntries(next);
    setBody("");
    writeJSON(DRAFT_KEY, { body: "" });
    setSavedAt(entry.ts);
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
            Tag pré-rempli : <span className="text-[var(--color-text-primary)]">{initialAsset}</span>
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
            disabled={!body.trim()}
            className="rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] px-4 py-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-primary)] transition-colors hover:border-[var(--color-bull)] hover:text-[var(--color-bull)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Sauvegarder
          </button>
          <button
            type="button"
            onClick={clearDraft}
            disabled={!body}
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
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Dernières entrées · {entries.length}/{MAX_ENTRIES}
        </h2>
        {entries.length === 0 ? (
          <p className="text-sm text-[var(--color-text-secondary)]">Aucune entrée pour l&apos;instant.</p>
        ) : (
          <ol className="space-y-3">
            {entries.map((e) => (
              <li
                key={e.ts}
                className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-elevated)]/50 p-3"
              >
                <p className="mb-1 flex items-baseline gap-3 font-mono text-[10px] uppercase tracking-widest text-[var(--color-text-muted)]">
                  <span>{new Date(e.ts).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</span>
                  {e.asset ? (
                    <span className="text-[var(--color-accent-cobalt)]">{e.asset}</span>
                  ) : null}
                </p>
                <p className="whitespace-pre-wrap text-sm text-[var(--color-text-primary)]">{e.body}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
