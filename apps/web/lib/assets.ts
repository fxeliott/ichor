/**
 * Static catalog of the 8 Phase 0 assets.
 *
 * Display names + decimal precision are kept here so URL-safe codes can map
 * to nice labels without round-tripping the API. The list itself is the
 * authoritative source for the /assets index and the [code] route validation.
 */

export interface AssetMeta {
  /** URL-safe code, also matches the API `asset` filter. */
  code: string;
  /** Display name (slash-separated for FX, dotted for indices). */
  display: string;
  /** Asset class — drives icon + grouping. */
  class: "fx_major" | "metal" | "index";
  /** Decimal places when rendering price. */
  precision: number;
}

export const ASSETS: readonly AssetMeta[] = [
  { code: "EUR_USD", display: "EUR/USD", class: "fx_major", precision: 4 },
  { code: "GBP_USD", display: "GBP/USD", class: "fx_major", precision: 4 },
  { code: "USD_JPY", display: "USD/JPY", class: "fx_major", precision: 2 },
  { code: "AUD_USD", display: "AUD/USD", class: "fx_major", precision: 4 },
  { code: "USD_CAD", display: "USD/CAD", class: "fx_major", precision: 4 },
  { code: "XAU_USD", display: "XAU/USD", class: "metal", precision: 2 },
  { code: "NAS100", display: "NAS100", class: "index", precision: 1 },
  { code: "SPX500", display: "SPX500", class: "index", precision: 2 },
] as const;

const BY_CODE: Map<string, AssetMeta> = new Map(ASSETS.map((a) => [a.code, a]));

export const findAsset = (code: string): AssetMeta | undefined =>
  BY_CODE.get(code);

export const isValidAssetCode = (code: string): boolean => BY_CODE.has(code);
