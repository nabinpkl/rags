import type { NextConfig } from "next";

// Static export (D13): the app ships as static files behind Caddy, no Node
// server in prod. `images.unoptimized` is required because the export target
// has no image-optimization server. No dynamic routes exist (§4c decision 2),
// so nothing needs `generateStaticParams`.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  // `next dev` only serves /_next dev resources (HMR, the client bootstrap)
  // to the host it was started on. Development here happens on the box that
  // holds the corpus and is reached over the tailnet, so without this the dev
  // server returns HTML that never hydrates — the app renders and then
  // ignores every click. Dev-only: `next build` (the static export we deploy)
  // does not read it. The host is the developer's own, so it comes from the
  // environment: NEXT_DEV_ORIGINS, comma-separated.
  allowedDevOrigins: (process.env.NEXT_DEV_ORIGINS ?? "").split(",").filter(Boolean),
};

export default nextConfig;
