import type { Metadata, Viewport } from "next";
import { Instrument_Sans, STIX_Two_Text, Spline_Sans_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/app/providers";

// next/font self-hosts these at build time: the fonts are downloaded during
// `next build` and served from our own origin, so the deployed static export
// makes NO runtime request to a font CDN (§4b: "the app must not" use Google
// Fonts at runtime; the mockup's CDN <link> is reference-only).
const sans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument-sans",
  weight: ["400", "500", "600"],
});
const serif = STIX_Two_Text({
  subsets: ["latin"],
  variable: "--font-stix-two-text",
  weight: ["400", "600", "700"],
});
const mono = Spline_Sans_Mono({
  subsets: ["latin"],
  variable: "--font-spline-sans-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "askRAG — agentic RAG over arXiv CS papers",
  description: "An agent that searches, reads, and cites arXiv CS papers.",
};

// `viewportFit: "cover"` is what makes `env(safe-area-inset-*)` resolve to
// anything but 0 on a notched phone — the chat composer (#83) pads by it so
// the send button doesn't sit under the home indicator.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning` is required by next-themes and ONLY covers
    // this element's own attributes: its pre-paint script sets `class` and
    // `style` on <html> before React hydrates, so the server's markup
    // necessarily differs here. Nothing below inherits the suppression.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${serif.variable} ${mono.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
