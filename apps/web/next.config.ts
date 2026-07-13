import type { NextConfig } from "next";

/** Must stay aligned with overview Seed upload copy and Web shell contract tests. */
const SOURCE_UPLOAD_BODY_LIMIT = "64mb";

const nextConfig: NextConfig = {
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  experimental: {
    // Seed upload posts the full source file through a Server Action.
    serverActions: {
      bodySizeLimit: SOURCE_UPLOAD_BODY_LIMIT,
    },
    // Middleware may clone the request body; keep it at the same ceiling.
    middlewareClientMaxBodySize: SOURCE_UPLOAD_BODY_LIMIT,
  },
  reactStrictMode: true,
};

export default nextConfig;
