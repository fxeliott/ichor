import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiGet, isLive } from "@/lib/api";

describe("isLive type-guard", () => {
  it("returns false for null", () => {
    expect(isLive(null)).toBe(false);
  });

  it("returns true for an object", () => {
    expect(isLive({ foo: "bar" })).toBe(true);
  });

  it("returns true for empty object", () => {
    expect(isLive({})).toBe(true);
  });

  it("returns true for arrays (non-null)", () => {
    expect(isLive([])).toBe(true);
    expect(isLive([1, 2, 3])).toBe(true);
  });

  it("returns true for primitives (non-null)", () => {
    expect(isLive(0)).toBe(true);
    expect(isLive("")).toBe(true);
    expect(isLive(false)).toBe(true);
  });

  it("narrows the type when used as a guard", () => {
    const data: { items: number[] } | null = { items: [1, 2] };
    if (isLive(data)) {
      // After the guard, `data.items` is typed as number[].
      expect(data.items.length).toBe(2);
    } else {
      throw new Error("guard should have narrowed");
    }
  });
});

// ─────────────────────────── apiGet (mocked fetch) ───────────────────────

describe("apiGet", () => {
  const realFetch = globalThis.fetch;

  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = realFetch;
  });

  it("returns parsed JSON on 2xx", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ ok: true, n: 7 }), { status: 200 }),
    ) as unknown as typeof fetch;

    const data = await apiGet<{ ok: boolean; n: number }>("/v1/test", {
      baseUrl: "http://test",
    });
    expect(data).toEqual({ ok: true, n: 7 });
  });

  it("returns null on non-2xx", async () => {
    globalThis.fetch = vi.fn(
      async () => new Response("server boom", { status: 503 }),
    ) as unknown as typeof fetch;

    const data = await apiGet("/v1/test", { baseUrl: "http://test" });
    expect(data).toBeNull();
  });

  it("returns null on network failure", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("ECONNREFUSED");
    }) as unknown as typeof fetch;

    const data = await apiGet("/v1/test", { baseUrl: "http://test" });
    expect(data).toBeNull();
  });

  it("returns null on JSON parse failure", async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response("not json{", { status: 200, headers: { "Content-Type": "text/plain" } }),
    ) as unknown as typeof fetch;

    const data = await apiGet("/v1/test", { baseUrl: "http://test" });
    expect(data).toBeNull();
  });

  it("respects an absolute path argument over base URL", async () => {
    const spy = vi.fn(
      async (url: string) => new Response(JSON.stringify({ url }), { status: 200 }),
    ) as unknown as typeof fetch;
    globalThis.fetch = spy;

    await apiGet("https://other/api", { baseUrl: "http://test" });
    // The spy should have been called with the absolute URL, not concatenated.
    expect((spy as unknown as { mock: { calls: unknown[][] } }).mock.calls[0]?.[0]).toBe(
      "https://other/api",
    );
  });

  it("uses cache:no-store by default", async () => {
    const spy = vi.fn(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    ) as unknown as typeof fetch;
    globalThis.fetch = spy;

    await apiGet("/v1/test", { baseUrl: "http://test" });
    const init = (spy as unknown as { mock: { calls: unknown[][] } }).mock.calls[0]?.[1] as
      | { cache?: string; next?: { revalidate?: number } }
      | undefined;
    expect(init?.cache).toBe("no-store");
    expect(init?.next).toBeUndefined();
  });

  it("uses next.revalidate when revalidate is provided", async () => {
    const spy = vi.fn(
      async () => new Response(JSON.stringify({ ok: true }), { status: 200 }),
    ) as unknown as typeof fetch;
    globalThis.fetch = spy;

    await apiGet("/v1/test", { baseUrl: "http://test", revalidate: 60 });
    const init = (spy as unknown as { mock: { calls: unknown[][] } }).mock.calls[0]?.[1] as
      | { cache?: string; next?: { revalidate?: number } }
      | undefined;
    expect(init?.cache).toBeUndefined();
    expect(init?.next?.revalidate).toBe(60);
  });
});
