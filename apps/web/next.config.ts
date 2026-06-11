import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // pnpm workspace: pin the root so Turbopack doesn't mis-infer it and then
  // fail to resolve the next package (crashes `next dev`).
  turbopack: {
    root: path.join(__dirname, "../.."),
  },
};

export default nextConfig;
