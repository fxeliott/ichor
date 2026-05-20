/**
 * r132 — NY 13-16h Paris window status (Mission centrale axis 3 closure).
 *
 * Pure-fn tests on `getNyWindowStatus` covering the 4 discriminated-
 * union states + DST edge + weekend semantics. All dates are
 * UTC ISO-8601 ; `parisHM` (via `Intl.DateTimeFormat` Europe/Paris)
 * handles the DST offset year-round so tests are deterministic on
 * any host timezone.
 */

import { describe, expect, it } from "vitest";

import { getNyWindowStatus, NY_WINDOW_END_PARIS_H, NY_WINDOW_START_PARIS_H } from "@/lib/nyWindow";

describe("getNyWindowStatus — Mission centrale axis 3 NY 13-16h Paris", () => {
  it("returns 'pre' before 13:00 Paris on a weekday", () => {
    // 2026-05-20 = mercredi, Paris-time 11:00 (CEST = UTC+2, so 09:00 UTC)
    const wedAt11Paris = new Date("2026-05-20T09:00:00Z");
    const s = getNyWindowStatus(wedAt11Paris);
    expect(s.kind).toBe("pre");
    expect(s.h).toBe(2); // 13:00 - 11:00 = 2h
    expect(s.m).toBe(0);
    expect(s.label).toBe("Pré-NY · T−2h00 avant 13h Paris");
  });

  it("returns 'pre' with non-zero minutes for off-hour countdown", () => {
    // 2026-05-20 mercredi, Paris-time 12:35 (10:35 UTC)
    const wedAt1235Paris = new Date("2026-05-20T10:35:00Z");
    const s = getNyWindowStatus(wedAt1235Paris);
    expect(s.kind).toBe("pre");
    expect(s.h).toBe(0);
    expect(s.m).toBe(25);
    expect(s.label).toBe("Pré-NY · T−0h25 avant 13h Paris");
  });

  it("returns 'active' exactly at 13:00 Paris on a weekday", () => {
    // 2026-05-20 mercredi, Paris-time 13:00 (11:00 UTC summer)
    const wedAt1300Paris = new Date("2026-05-20T11:00:00Z");
    const s = getNyWindowStatus(wedAt1300Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
    expect(s.label).toBe("Fenêtre NY active · 0h00 écoulées sur 3h");
  });

  it("returns 'active' mid-window (15:42 Paris = +2h42 elapsed)", () => {
    // 2026-05-20 mercredi, Paris-time 15:42 (13:42 UTC)
    const wedAt1542Paris = new Date("2026-05-20T13:42:00Z");
    const s = getNyWindowStatus(wedAt1542Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(2);
    expect(s.m).toBe(42);
    expect(s.label).toBe("Fenêtre NY active · 2h42 écoulées sur 3h");
  });

  it("returns 'post' at 16:00 Paris (window-end boundary, exclusive)", () => {
    // 2026-05-20 mercredi, Paris-time 16:00 (14:00 UTC)
    const wedAt1600Paris = new Date("2026-05-20T14:00:00Z");
    const s = getNyWindowStatus(wedAt1600Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
    expect(s.label).toBe("Post-NY · clos depuis 0h00");
  });

  it("returns 'post' later in the day (21:15 Paris)", () => {
    // 2026-05-20 mercredi, Paris-time 21:15 (19:15 UTC)
    const wedAt2115Paris = new Date("2026-05-20T19:15:00Z");
    const s = getNyWindowStatus(wedAt2115Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(5);
    expect(s.m).toBe(15);
    expect(s.label).toBe("Post-NY · clos depuis 5h15");
  });

  it("returns 'weekend' on Saturday regardless of time", () => {
    // 2026-05-23 samedi, Paris-time 14:30 (12:30 UTC summer)
    const satAt1430Paris = new Date("2026-05-23T12:30:00Z");
    const s = getNyWindowStatus(satAt1430Paris);
    expect(s.kind).toBe("weekend");
    expect(s.label).toBe("Week-end · pas de NY aujourd'hui");
  });

  it("returns 'weekend' on Sunday regardless of time", () => {
    // 2026-05-24 dimanche, Paris-time 13:42 (11:42 UTC summer)
    const sunAt1342Paris = new Date("2026-05-24T11:42:00Z");
    const s = getNyWindowStatus(sunAt1342Paris);
    expect(s.kind).toBe("weekend");
    expect(s.label).toBe("Week-end · pas de NY aujourd'hui");
  });

  it("handles winter DST correctly (CET = UTC+1, NOT UTC+2)", () => {
    // 2026-01-14 mercredi winter, Paris-time 13:00 (12:00 UTC winter)
    const winterWedAt1300Paris = new Date("2026-01-14T12:00:00Z");
    const s = getNyWindowStatus(winterWedAt1300Paris);
    expect(s.kind).toBe("active");
    expect(s.h).toBe(0);
    expect(s.m).toBe(0);
  });

  it("handles winter DST correctly for the post-NY case", () => {
    // 2026-01-14 mercredi winter, Paris-time 17:30 (16:30 UTC winter)
    const winterWedAt1730Paris = new Date("2026-01-14T16:30:00Z");
    const s = getNyWindowStatus(winterWedAt1730Paris);
    expect(s.kind).toBe("post");
    expect(s.h).toBe(1);
    expect(s.m).toBe(30);
  });

  it("constants are aligned with Eliot's NY 13-16h Paris cible", () => {
    expect(NY_WINDOW_START_PARIS_H).toBe(13);
    expect(NY_WINDOW_END_PARIS_H).toBe(16);
  });
});
