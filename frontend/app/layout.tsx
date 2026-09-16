import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible_Next, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import { Providers } from "@/app/providers";

// next/font self-hosts these at build time: the fonts are downloaded during
// `next build` and served from our own origin, so the deployed static export
// makes NO runtime request to a font CDN (§4b: "the app must not" use Google
// Fonts at runtime; the mockup's CDN <link> is reference-only).
// Chosen for stroke weight at small sizes: the catalog is read at 12-15px,
// where the previous narrow sans and hairline serif read as thin (see
// DECISIONS.md 2026-09-16). Variable axes, so any weight the UI asks for is
// real rather than synthesised.
const sans = Atkinson_Hyperlegible_Next({
  subsets: ["latin"],
  variable: "--font-sans-face",
});
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif-face",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
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
