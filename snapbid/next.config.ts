import type { NextConfig } from "next";

const config: NextConfig = {
  experimental: {
    // Proposal PDFs are generated with pdf-lib in a Node runtime route.
    serverActions: { bodySizeLimit: "4mb" },
  },
};

export default config;
