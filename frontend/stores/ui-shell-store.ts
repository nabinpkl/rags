// Which shell overlay is open on a narrow viewport (#83). Deliberately NOT
// URL-synced: D-2 makes the URL the source of truth for what you are LOOKING
// AT (a paper, a page, filters) — an open drawer is not a place, it is a
// gesture in progress, and putting it in the URL would make the back button
// close a drawer instead of returning to the corpus.
//
// One enum, not two booleans: "filters open" and "agent open" are mutually
// exclusive by design (both are full-height overlays on the same screen), and
// a state machine cannot represent the both-open state that boolean soup can
// (.claude/rules/python-backend.md states the rule; it is a house preference,
// not a language one).
import { create } from "zustand";

export type ShellOverlay = "none" | "filters" | "agent";

interface UiShellState {
  overlay: ShellOverlay;
  openFilters: () => void;
  openAgent: () => void;
  toggleAgent: () => void;
  closeOverlay: () => void;
}

export const useUiShellStore = create<UiShellState>((set) => ({
  overlay: "none",
  openFilters: () => set({ overlay: "filters" }),
  openAgent: () => set({ overlay: "agent" }),
  toggleAgent: () => set((state) => ({ overlay: state.overlay === "agent" ? "none" : "agent" })),
  closeOverlay: () => set({ overlay: "none" }),
}));
