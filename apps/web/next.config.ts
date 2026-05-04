import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  // Proxy API + WebSocket to the local FastAPI on Hetzner. This lets
  // client-side fetches use same-origin /v1/... paths instead of
  // hitting NEXT_PUBLIC_API_URL=127.0.0.1:8000 (which is only reachable
  // from the server during SSR — not from the user's browser via the
  // public tunnel).
  async rewrites() {
    const apiOrigin =
      process.env["ICHOR_API_PROXY_TARGET"] ?? "http://127.0.0.1:8000";
    return [
      { source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` },
      { source: "/healthz", destination: `${apiOrigin}/healthz` },
      { source: "/healthz/:path*", destination: `${apiOrigin}/healthz/:path*` },
    ];
  },
};

export default nextConfig;
