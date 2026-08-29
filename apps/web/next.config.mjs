import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: false,
  },
  // Pin the workspace root explicitly so Next.js doesn't get confused by
  // any stray lockfile elsewhere in the monorepo (services/, packages/, etc.
  // will each get their own tooling later).
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
