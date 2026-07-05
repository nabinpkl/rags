import type { NextConfig } from "next";

// Static export (D13): the app ships as static files behind Caddy, no Node
// server in prod. `images.unoptimized` is required because the export target
// has no image-optimization server. No dynamic routes exist (§4c decision 2),
// so nothing needs `generateStaticParams`.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
