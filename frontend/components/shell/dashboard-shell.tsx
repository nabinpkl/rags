"use client";

import { Menu } from "lucide-react";
import { type ReactNode, type Ref, useState } from "react";

import { DrawerPanel } from "@/components/shell/drawer-panel";
import { ShellSidebar, type ShellView } from "@/components/shell/shell-sidebar";
import { SiteFooter } from "@/components/site-footer";

/** The frame the dashboard views (Citations, Trends) render into: the shared
 * rail, a bar naming what is on screen, and a scrolling canvas.
 *
 * Same rail width and breakpoint as the catalog's, so a reader moving between
 * views sees the column stay put rather than resize under the pointer.
 */
export function DashboardShell({
  current,
  trail,
  canvasRef,
  children,
}: {
  current: ShellView;
  /** Breadcrumb items after "askRAG", each an `<li>`. */
  trail: ReactNode;
  canvasRef?: Ref<HTMLElement>;
  children: ReactNode;
}) {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="bg-paper text-ink flex h-dvh flex-col">
      <div className="flex min-h-0 flex-1">
        <DrawerPanel
          dockAt="md"
          side="left"
          label="Navigation"
          open={navOpen}
          onClose={() => setNavOpen(false)}
          className="bg-panel border-line w-[min(320px,86vw)] shrink-0 border-r md:w-[264px]"
        >
          <ShellSidebar current={current} />
        </DrawerPanel>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <header className="bg-panel border-line flex h-[57px] shrink-0 items-center gap-3 border-b px-4">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              className="border-line text-ink hover:bg-panel-hover -ml-1 flex size-9 shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none md:hidden"
            >
              <Menu className="size-4" aria-hidden />
            </button>

            <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
              <ol className="flex min-w-0 items-center gap-2 font-mono text-[11.5px]">
                <li className="text-muted hidden sm:block">askRAG</li>
                <li aria-hidden className="text-line hidden sm:block">
                  /
                </li>
                {trail}
              </ol>
            </nav>
          </header>

          {/* `relative` is load-bearing, not decoration: `sr-only` is
              `position: absolute`, so a screen-reader summary anywhere on the
              canvas takes the INITIAL containing block as its own unless
              something here is positioned — and an abspos box outside the
              scroller's containing block is not clipped by it. Two chart
              summaries were enough to give the document 580px of phantom
              scroll, which the browser then used on every scroll-to-top,
              taking the top bar and the rail out of view with it. */}
          <main ref={canvasRef} className="relative min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-4 py-5 sm:px-6 sm:py-6">
              {children}
            </div>
          </main>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}
