"use client";

import { Suspense } from "react";
import { ChatPanel } from "@/components/agent-panel/chat-panel";
import { ExplorerPanel } from "@/components/explorer/explorer-panel";
import { PaperSplitView } from "@/components/viewer/paper-split-view";
import { AppBar } from "@/components/shell/app-bar";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { SiteFooter } from "@/components/site-footer";
import { useDriveUi } from "@/hooks/use-drive-ui";
import { useViewerUrlSync } from "@/hooks/use-viewer-url-sync";
import { useUiShellStore } from "@/stores/ui-shell-store";
import { useViewerStore } from "@/stores/viewer-store";

/** Explorer <-> viewer swap (#29): `viewer-store`'s `paper` (URL-synced,
 * `?paper=`) picks which region renders. This is the ONE place
 * `useViewerUrlSync()` is called — it must live on a component that never
 * unmounts across the swap, since `explorer-panel.tsx` and
 * `paper-split-view.tsx` mount/unmount as `paper` toggles. Owning the sync
 * on either of THOSE would mean a row click's `setPaper` unmounts the sync
 * owner in the same commit that was supposed to push the new `?paper=` URL,
 * dropping the push entirely — the same class of race #28's cross-tick
 * carry-over note (DECISIONS.md) warns about, one level up.
 *
 * `useDriveUi()` (#32) is mounted here for the same reason: it's the agent-
 * driven counterpart of a row click, so it needs the same never-unmounts
 * home to route `open_paper`/`goto_page` into the viewer and `set_filters`
 * back into the explorer (both via `viewer-store`'s `paper` field, which
 * this component already swaps on). */
function AppRegion() {
  useViewerUrlSync();
  useDriveUi();
  const paper = useViewerStore((state) => state.paper);
  return paper ? <PaperSplitView /> : <ExplorerPanel />;
}

// The single app shell (§4c decision 2: one page, no dynamic routes — a paper
// is a `?paper=<id>` search param, never a `/papers/[id]` route). `Suspense`
// is required around AppRegion because it (via use-viewer-url-sync.ts) calls
// `useSearchParams`, which Next's static export build requires to be
// wrapped in a boundary.
//
// Layout by width (#83): the agent panel docks as a column from `lg:` and is
// a right-hand sheet below it; the facet rail does the same at `md:` (inside
// explorer-panel.tsx, since filters belong to the corpus list). `AppBar`
// carries the handles for whatever is undocked and disappears at `lg:`.
//
// `h-dvh`, not `h-screen`: on mobile browsers `100vh` is the height with the
// URL bar RETRACTED, so a 100vh app shell puts its own footer under the
// browser chrome until you scroll. `dvh` tracks the actual viewport.
//
// `SiteFooter` (§6b/§6c) sits outside `<main>`, as a sibling in a column
// flex, not appended below a full-height block — that would land it below the
// fold. `<main>` takes `flex-1 min-h-0` so the footer's own height is
// accounted for in the layout instead of overflowing the viewport.
export default function Home() {
  const overlay = useUiShellStore((state) => state.overlay);
  const closeOverlay = useUiShellStore((state) => state.closeOverlay);

  return (
    <div className="flex h-dvh flex-col">
      <AppBar />
      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* `min-h-0` as well as `min-w-0`: a flex item's default `min-height:
            auto` refuses to shrink below its content, so the virtualized list
            grew the column past the viewport and the paper rows rendered on
            top of the footer. It only showed once the column stack got a
            second row (the app bar) to compete with. */}
        <div className="min-h-0 min-w-0 flex-1">
          <Suspense fallback={null}>
            <AppRegion />
          </Suspense>
        </div>
        <DrawerPanel
          dockAt="lg"
          side="right"
          label="Agent panel"
          open={overlay === "agent"}
          onClose={closeOverlay}
          className="w-full sm:w-[420px] lg:h-full lg:w-[420px]"
        >
          <ChatPanel />
        </DrawerPanel>
      </main>
      <SiteFooter />
    </div>
  );
}
