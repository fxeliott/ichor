// session-clock.ts — server-side helper to compute the current Ichor
// session window from real time. Replaces the hardcoded
// `NOW = "2026-05-04T07:42:00.000Z"` that froze /today on a single
// fixed moment (Phase A.9.1, ROADMAP REV4).
//
// The 4 daily windows align with the systemd briefing timers on Hetzner :
//   pre_londres   06:00-08:30 Paris  (Pre-Londres briefing tick at 06:00)
//   pre_ny        12:00-13:30 Paris  (Pre-NY briefing tick at 12:00)
//   ny_mid        16:30-18:00 Paris  (NY-mid context refresh tick at 17:00)
//   ny_close      21:00-22:30 Paris  (NY-close debrief tick at 22:00)
//
// Outside these 4 windows we return `idle` (markets quiet, no active session).
// Weekends always return `weekend` regardless of time.
//
// The "active window" is biased forward — we consider a session "active"
// from H-4h to H+1h around the briefing tick, which matches /today's
// display contract ("calendar filtered on H-4h → H+1h sessions").

export type SessionWindow =
  | "pre_londres"
  | "pre_ny"
  | "ny_mid"
  | "ny_close"
  | "idle"
  | "weekend";

interface WindowDef {
  id: Exclude<SessionWindow, "idle" | "weekend">;
  /** Start of the active display window in Europe/Paris (24h). */
  start: { h: number; m: number };
  /** End (exclusive) of the active display window in Europe/Paris. */
  end: { h: number; m: number };
}

const WINDOWS: WindowDef[] = [
  { id: "pre_londres", start: { h: 6, m: 0 }, end: { h: 8, m: 30 } },
  { id: "pre_ny", start: { h: 12, m: 0 }, end: { h: 13, m: 30 } },
  { id: "ny_mid", start: { h: 16, m: 30 }, end: { h: 18, m: 0 } },
  { id: "ny_close", start: { h: 21, m: 0 }, end: { h: 22, m: 30 } },
];

/**
 * Convert a timestamp to {h, m} in Europe/Paris using Intl. Returns
 * 0..23 for hours and 0..59 for minutes regardless of DST.
 */
function parisHM(d: Date): { h: number; m: number; weekday: number } {
  // `Intl.DateTimeFormat` with timeZone: "Europe/Paris" gives us the
  // correct local time even on a UTC server.
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hour12: false,
  }).formatToParts(d);

  const hh = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
  const mm = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  const wd = parts.find((p) => p.type === "weekday")?.value ?? "Mon";
  // Mon=1 ... Sun=7
  const weekdayMap: Record<string, number> = {
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
    Sun: 7,
  };
  return { h: hh, m: mm, weekday: weekdayMap[wd] ?? 1 };
}

/**
 * Compute the current session window. Defaults to `now()` but accepts
 * an explicit Date for testing or replay scenarios.
 */
export function getCurrentSession(now: Date = new Date()): SessionWindow {
  const { h, m, weekday } = parisHM(now);

  // Saturday / Sunday : markets effectively closed.
  if (weekday === 6 || weekday === 7) {
    return "weekend";
  }

  const minutes = h * 60 + m;
  for (const w of WINDOWS) {
    const start = w.start.h * 60 + w.start.m;
    const end = w.end.h * 60 + w.end.m;
    if (minutes >= start && minutes < end) {
      return w.id;
    }
  }
  return "idle";
}

/**
 * Human-readable label for a SessionWindow. Used for badges + nav.
 */
export function sessionLabel(s: SessionWindow): string {
  switch (s) {
    case "pre_londres":
      return "Pré-Londres";
    case "pre_ny":
      return "Pré-NY";
    case "ny_mid":
      return "NY mid";
    case "ny_close":
      return "NY close";
    case "weekend":
      return "Week-end";
    case "idle":
      return "Inter-session";
  }
}

/**
 * Returns true while a real trading session window is active (any of the
 * 4 daily windows). Used to gate "live" UI affordances.
 */
export function isLiveSession(s: SessionWindow): boolean {
  return s !== "idle" && s !== "weekend";
}
