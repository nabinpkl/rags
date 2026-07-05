"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

// The TanStack Query client owns all server state (§4b/frontend rules: server
// state never mirrored into zustand). Created once per browser session via
// useState so it survives re-renders but isn't shared across requests — which
// matters under SSR; harmless in a static export, kept for correctness.
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
