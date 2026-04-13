import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Serve static data from public/data in dev; in prod point DATA_ROOT at S3
  env: {
    DATA_ROOT: process.env.DATA_ROOT ?? "",
  },
};

export default nextConfig;
