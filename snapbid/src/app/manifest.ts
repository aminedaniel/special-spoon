import type { MetadataRoute } from "next";

/** Mobile-first PWA: contractors add SnapBid to the home screen on the truck. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SnapBid",
    short_name: "SnapBid",
    description: "Estimate to signed proposal in minutes.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#f6f7f9",
    theme_color: "#1d4ed8",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
