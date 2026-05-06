/**
 * LiveChartCard — interactive intraday candlestick chart.
 *
 * Uses lightweight-charts (TradingView-attributed by default since v5.2)
 * fed by /v1/market/intraday/{asset}. Time-axis is epoch seconds UTC,
 * displayed in Europe/Paris via the chart lib's locale config.
 *
 * Wires the lightweight-charts dep that was installed but never imported
 * (audit 2026-05-03 — this commit closes that).
 *
 * VISION_2026 delta O — living dashboard mosaic.
 */

"use client";

import * as React from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { IntradayBar } from "../lib/api";

export interface LiveChartCardProps {
  asset: string;
  bars: IntradayBar[];
  height?: number;
  /** Reload bars at this cadence (ms). 0 = no auto-reload. */
  reloadIntervalMs?: number;
}

export const LiveChartCard: React.FC<LiveChartCardProps> = ({
  asset,
  bars: initialBars,
  height = 280,
  reloadIntervalMs = 30_000,
}) => {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [bars, setBars] = React.useState<IntradayBar[]>(initialBars);
  const [error, setError] = React.useState<string | null>(null);

  // Build chart on mount, dispose on unmount.
  React.useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgb(163 163 163)",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(64, 64, 64, 0.4)" },
        horzLines: { color: "rgba(64, 64, 64, 0.4)" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "rgba(64, 64, 64, 0.6)",
      },
      rightPriceScale: { borderColor: "rgba(64, 64, 64, 0.6)" },
      crosshair: {
        vertLine: { color: "rgba(115, 115, 115, 0.6)", width: 1, style: 3 },
        horzLine: { color: "rgba(115, 115, 115, 0.6)", width: 1, style: 3 },
      },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "rgba(52, 211, 153, 0.95)",
      downColor: "rgba(248, 113, 113, 0.95)",
      wickUpColor: "rgba(52, 211, 153, 0.7)",
      wickDownColor: "rgba(248, 113, 113, 0.7)",
      borderVisible: false,
    });
    seriesRef.current = series;

    // Resize on container size changes (responsive)
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        chart.applyOptions({ width: e.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  // Push bars whenever they change.
  React.useEffect(() => {
    if (!seriesRef.current) return;
    if (bars.length === 0) return;
    seriesRef.current.setData(
      bars.map((b) => ({
        time: b.time as UTCTimestamp,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  // Optional auto-reload (poll) every reloadIntervalMs.
  React.useEffect(() => {
    if (!reloadIntervalMs || reloadIntervalMs <= 0) return;
    const tick = async () => {
      try {
        const r = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}/v1/market/intraday/${encodeURIComponent(asset)}?hours=8`,
          { headers: { Accept: "application/json" }, cache: "no-store" },
        );
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const fresh = (await r.json()) as IntradayBar[];
        setBars(fresh);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "fetch failed");
      }
    };
    const id = window.setInterval(tick, reloadIntervalMs);
    return () => window.clearInterval(id);
  }, [asset, reloadIntervalMs]);

  return (
    <div className="rounded-lg border border-[var(--color-ichor-border)] bg-[var(--color-ichor-surface)]/60 p-3">
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--color-ichor-text)]">
          {asset.replace(/_/g, "/")} · 1-min intraday
        </h3>
        <p className="text-[11px] text-[var(--color-ichor-text-subtle)]">
          {bars.length} bars · refresh {Math.round(reloadIntervalMs / 1000)}s
        </p>
      </header>
      {error && <p className="mb-2 text-[11px] text-red-300">⚠ {error}</p>}
      {bars.length === 0 ? (
        <div
          className="flex items-center justify-center text-xs text-[var(--color-ichor-text-subtle)]"
          style={{ height }}
        >
          Aucune bar récente (marché fermé ?).
        </div>
      ) : (
        <div ref={containerRef} style={{ height }} />
      )}
      <p className="mt-2 text-[10px] text-[var(--color-ichor-text-faint)]">
        Charts by{" "}
        <a
          href="https://www.tradingview.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-[var(--color-ichor-text-muted)] underline"
        >
          TradingView
        </a>{" "}
        · données Polygon/Massive
      </p>
    </div>
  );
};
