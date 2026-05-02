import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Note: output: "standalone" omitted — only useful for Docker deploys.
  //   - Cloudflare Pages (Phase 0/1) builds Next.js natively via Pages Functions
  //   - On Win11 dev, "standalone" requires symlink perms (admin) which we lack.
  //     Enable later if/when we add a Docker-based deploy target.
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
