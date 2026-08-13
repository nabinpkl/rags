"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState } from "react";

// The TanStack Query client owns all server state (§4b/frontend rules: server
// state never mirrored into zustand). Created once per browser session via
// useState so it survives re-renders but isn't shared across requests — which
// matters under SSR; harmless in a static export, kept for correctness.
//
// `ThemeProvider` (#85) writes `.dark` onto <html> and persists the CHOICE
// (light/dark/system) to localStorage. It belongs above everything because
// the class it sets is what every design token in globals.css resolves
// against. `disableTransitionOnChange` suppresses transitions for the swap
// itself — without it, every themed border and background animates at once
// and the flip reads as a slow smear rather than a switch.
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}
