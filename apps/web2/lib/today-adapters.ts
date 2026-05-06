// Pure adapter functions for /today page.
//
// Extracted from app/today/page.tsx so they can be unit-tested without
// pulling in Next.js render machinery. All functions are deterministic
// transforms over typed API responses → UI-shaped Trigger[].

import type { Trigger } from "@/components/ui";
import type { CalendarUpcoming, EconomicEventListOut, TodaySnapshotOut } from "@/lib/api";

/** FRED-projected calendar → Trigger[]. Drops low-impact, slices to 8. */
export function adaptCalendarToTriggers(payload: CalendarUpcoming): Trigger[] {
  return payload.events
    .map((e, i): Trigger | null => {
      if (e.impact === "low") return null;
      const time = e.when_time_utc ?? "00:00";
      const [hh, mm] = time.split(":").map((s) => parseInt(s, 10));
      const iso = `${e.when}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00.000Z`;
      return {
        id: `cal-${i}`,
        label: `${e.region} · ${e.label}`,
        scheduledAt: iso,
        importance: e.impact === "high" ? "high" : "medium",
      };
    })
    .filter((t): t is Trigger => t !== null)
    .slice(0, 8);
}

/** /v1/today bundled calendar → Trigger[]. Drops low-impact, slices to 12. */
export function adaptTodayBundleToTriggers(payload: TodaySnapshotOut): Trigger[] {
  return payload.calendar_events
    .map((e, i): Trigger | null => {
      if (e.impact === "low") return null;
      const time = e.when_time_utc ?? "00:00";
      const [hh, mm] = time.split(":").map((s) => parseInt(s, 10));
      const iso = `${e.when}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00.000Z`;
      return {
        id: `td-${i}`,
        label: `${e.region} · ${e.label}`,
        scheduledAt: iso,
        importance: e.impact === "high" ? "high" : "medium",
      };
    })
    .filter((t): t is Trigger => t !== null)
    .slice(0, 12);
}

/** ForexFactory persisted events → Trigger[]. Skips low/holiday + null timestamps. */
export function adaptFFEventsToTriggers(payload: EconomicEventListOut): Trigger[] {
  return payload.events
    .map((e, i): Trigger | null => {
      if (e.impact === "low" || e.impact === "holiday") return null;
      if (!e.scheduled_at) return null;
      return {
        id: `ff-${e.id}-${i}`,
        label: `${e.currency} · ${e.title}`,
        scheduledAt: e.scheduled_at,
        importance: e.impact === "high" ? "high" : "medium",
      };
    })
    .filter((t): t is Trigger => t !== null);
}

/** Collapse duplicates by (label.lowercase, scheduledAt) and sort chronologically. */
export function dedupeAndSortTriggers(items: Trigger[]): Trigger[] {
  const seen = new Map<string, Trigger>();
  for (const t of items) {
    const key = `${t.label.toLowerCase()}|${t.scheduledAt}`;
    if (!seen.has(key)) seen.set(key, t);
  }
  return Array.from(seen.values()).sort(
    (a, b) => new Date(a.scheduledAt).getTime() - new Date(b.scheduledAt).getTime(),
  );
}
