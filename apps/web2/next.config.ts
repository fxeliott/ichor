import type { NextConfig } from "next";

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
  // Phase 2: keep the workspace alias resolution conservative. Storybook + MSW
  // can extend this later (cf SPEC_V2_HARDENING.md §4).
  experimental: {
    typedEnv: true,
  },
  // ESLint runs separately in CI (`pnpm lint` at the workspace root via the
  // flat config in `eslint.config.mjs`). Disabling it during `next build`
  // avoids running it twice with diverging configurations.
  eslint: {
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
