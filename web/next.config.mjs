/** @type {import('next').NextConfig} */
const nextConfig = {
  // Compiles to plain static files in ./out, which the FastAPI app serves from
  // the root. No Node runtime is needed on the crawler VM.
  output: 'export',

  // Emits out/live/index.html and links to /live/, which static file serving
  // resolves without a rewrite rule.
  trailingSlash: true,

  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
