"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

/** Light / dark / system, as an icon button opening a small menu (#85).
 *
 * Mounted in the site footer — the one element that survives the
 * explorer↔viewer swap AND every breakpoint, so the control needs no second
 * instance in the app bar.
 *
 * "System" is a real third state, not a default that collapses into one of
 * the other two: picking it means "keep following the OS", so a user who
 * flips their laptop to night mode at dusk follows along. next-themes stores
 * the CHOICE; `resolvedTheme` is what that choice currently renders as. */
const OPTIONS = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
] as const;

// "Has the client taken over yet?" — as an external-store read rather than
// setState-in-an-effect, which cascades an extra render and is a lint error
// here. Prerender answers false, hydration answers true, in one commit.
const NEVER_CHANGES = () => () => {};
const onClient = () => true;
const onServer = () => false;

export function ThemeMenu() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  // Until the client takes over, the stored choice is unknown: the static
  // export's prerendered HTML has no way to know it. Rendering a guess would
  // flip the icon on hydration, so the button shows a neutral icon until then.
  const mounted = useSyncExternalStore(NEVER_CHANGES, onClient, onServer);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const active = OPTIONS.find((option) => option.value === theme) ?? OPTIONS[2];
  // The button shows the CHOICE, not the resolution: on "system" that is the
  // monitor glyph, which is what tells you the theme is following the OS
  // rather than pinned.
  const ButtonIcon = mounted ? active.Icon : Monitor;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={
          mounted
            ? `Theme: ${active.label}${theme === "system" && resolvedTheme ? ` (${resolvedTheme})` : ""}`
            : "Theme"
        }
        className="border-line text-muted hover:text-ink hover:border-ink/40 flex h-7 w-7 items-center justify-center rounded border"
      >
        <ButtonIcon aria-hidden="true" className="h-3.5 w-3.5" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Theme"
          // Opens UPWARD: this lives in the footer, so a downward menu would
          // render past the bottom of the viewport.
          className="border-line bg-panel absolute right-0 bottom-9 z-50 min-w-[9rem] rounded border py-1 shadow-lg"
        >
          {OPTIONS.map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              role="menuitemradio"
              aria-checked={theme === value}
              onClick={() => {
                setTheme(value);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12px]",
                theme === value ? "text-teal-ink font-semibold" : "text-ink hover:bg-paper",
              )}
            >
              <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
