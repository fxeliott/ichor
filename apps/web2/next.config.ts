import type { NextConfig } from "next";

/**
 * Phase B (ROADMAP frontend infra) — adds security headers, CSP, and
 * documents the PPR upgrade path. The previous Phase 2 baseline only
 * declared rewrites + typedRoutes; security headers were missing.
 *
 * CSP strategy (2026):
 *   - `default-src 'self'` is the floor.
 *   - Scripts allow 'self' + 'unsafe-inline' for now — Next.js 15.5
 *     emits inline RSC payload bootstrap that is hard to nonce without
 *     middleware. Tighten to 'strict-dynamic' + nonces in Phase B.5
 *     once we hoist a request-scoped nonce via middleware.ts.
 *   - `connect-src` allows the Cloudflare Pages origin + the
 *     claude-runner tunnel for same-origin /v1/* fetches and the WS
 *     proxy (`wss:` opens both port 443 + Cloudflare).
 *
 * PPR (Next.js 15.5 incremental — historically canary-only):
 *   `experimental.ppr: 'incremental'` is **commented** because the
 *   stable 15.5.x branch errors with CanaryOnlyError on this flag
 *   (cf https://github.com/vercel/next.js/issues/71587). The path
 *   forward is the Next 16 `cacheComponents` config — slated for the
 *   web2 upgrade after Phase B lands.
 *
 * Permissions-Policy / Referrer-Policy / X-Content-Type-Options
 * round out the OWASP A05 (Security Misconfiguration) baseline.
 */

const SECURITY_HEADERS = [
  // Force HTTPS for 1 year incl. subdomains. The Cloudflare Pages CDN
  // already serves HTTPS-only; this is defense-in-depth in case a future
  // route reverts to a permissive proxy config.
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  // No content-type sniffing — XSS hardening on user-uploaded media,
  // even though Ichor doesn't accept user uploads today.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Prevent clickjacking — Ichor surfaces are never iframed.
  { key: "X-Frame-Options", value: "DENY" },
  // Strict referrer policy — leaks no path/query to third parties.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Permissions-Policy — Ichor uses none of these surfaces today.
  // Tightened by listing all common browser features as denied.
  {
    key: "Permissions-Policy",
    value: [
      "camera=()",
      "microphone=()",
      "geolocation=()",
      "payment=()",
      "usb=()",
      "fullscreen=(self)",
    ].join(", "),
  },
  // Content-Security-Policy — see header docstring above.
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // 'unsafe-inline' is interim — see Phase B.5 nonce migration.
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      // Allow XHR/WebSocket to same-origin only (rewrites send /v1/* to
      // the API, /healthz to the API). wss: covers the WebSocket proxy.
      "connect-src 'self' wss:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,

  // Proxy API + WebSocket to the local FastAPI on Hetzner. Lets client-side
  // fetches use same-origin /v1/... paths instead of hitting an explicit
  // NEXT_PUBLIC_API_URL (which is only reachable from server during SSR — not
  // from the user's browser via the public tunnel).
  async rewrites() {
    const apiOrigin = process.env["ICHOR_API_PROXY_TARGET"] ?? "http://127.0.0.1:8000";
    return [
      { source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` },
      { source: "/healthz", destination: `${apiOrigin}/healthz` },
      { source: "/healthz/:path*", destination: `${apiOrigin}/healthz/:path*` },
    ];
  },

  // OWASP A05 — security headers applied to every route.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },

  // Phase 2: keep the workspace alias resolution conservative. Storybook + MSW
  // can extend this later (cf SPEC_V2_HARDENING.md §4).
  experimental: {
    typedEnv: true,
    // PPR — see file docstring. Re-enable after Next 16 cacheComponents migration.
    // ppr: "incremental",
  },

  // ESLint runs separately in CI (`pnpm lint` at the workspace root via the
  // flat config in `eslint.config.mjs`). Disabling it during `next build`
  // avoids running it twice with diverging configurations.
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
