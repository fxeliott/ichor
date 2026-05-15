/**
 * Priority asset registry — shared between the client AssetSwitcher and
 * the server /briefing/[asset] route.
 *
 * MUST be a plain (non-"use client") module : a Server Component that
 * imports a const from a "use client" module receives a client-reference
 * proxy, not the real array (`.includes` is undefined → 500). This module
 * has no React/client deps so both boundaries import it cleanly.
 *
 * r65 — Eliot's vision (verbatim) : "5 actifs eurusd gbpusd xauusd sp500
 * et nasdaq". USD_CAD remains backend-side (ADR-083 D1) but is
 * deliberately out-of-scope for this premium briefing surface.
 */

export interface PriorityAsset {
  code: string;
  label: string;
  pair: string;
}

export const PRIORITY_ASSETS: PriorityAsset[] = [
  { code: "EUR_USD", label: "Euro / Dollar", pair: "EUR/USD" },
  { code: "GBP_USD", label: "Livre / Dollar", pair: "GBP/USD" },
  { code: "XAU_USD", label: "Or / Dollar", pair: "XAU/USD" },
  { code: "SPX500_USD", label: "S&P 500", pair: "SPX 500" },
  { code: "NAS100_USD", label: "Nasdaq 100", pair: "NAS 100" },
];

export const PRIORITY_ASSET_CODES: string[] = PRIORITY_ASSETS.map((a) => a.code);
