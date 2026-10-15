/** @type {import('next').NextConfig} */
const nextConfig = {
  // Compiles to plain static files in ./out, which the FastAPI app serves.
  // No Node runtime is needed on the crawler VM.
  output: 'export',

  // The API already owns /triage, /schedules, /crawlers, /spiders and /server at
  // the root, and those routes match before any static mount. Serving the
  // dashboard under /ui keeps the two apart, so a bare /triage stays the API
  // endpoint and /ui/triage/ is the page. FastAPI redirects / to the dashboard.
  basePath: '/ui',

  // Emits out/live/index.html and links to /ui/live/, which static file serving
  // resolves without a rewrite rule.
  trailingSlash: true,

  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
