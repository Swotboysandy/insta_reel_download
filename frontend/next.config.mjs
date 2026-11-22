/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a plain static site into out/ so the Flask backend can serve the UI
  // itself. One process, one port, no `next dev` to start separately.
  output: "export",
  experimental: { cpus: 1, webpackMemoryOptimizations: true },
  images: { unoptimized: true },
  // Silences the "inferred workspace root" warning caused by the parent
  // CODING/package-lock.json.
  outputFileTracingRoot: import.meta.dirname,
};

export default nextConfig;
