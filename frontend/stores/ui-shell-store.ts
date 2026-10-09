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
//
// `agentColumn` is the other half: whether the agent is shown as a docked
// column on a wide viewport. It is its own field because the two states have
// different owners of "close". The sheet closes itself after the agent
// drives the screen (use-drive-ui.ts), since it covers what was driven; a
// column covers nothing, and closing it there would shut the panel on every
// agent action. hooks/use-agent-panel.ts picks which of the two a control
// means at the current width.
import { create } from "zustand";

export type ShellOverlay = "none" | "filters" | "agent";

interface UiShellState {
  overlay: ShellOverlay;
  /** Closed until asked for: the agent is on demand, not a fixed column. */
  agentColumn: boolean;
  setAgentColumn: (open: boolean) => void;
  openFilters: () => void;
  openAgent: () => void;
  toggleAgent: () => void;
  closeOverlay: () => void;
}

export const useUiShellStore = create<UiShellState>((set) => ({
  overlay: "none",
  agentColumn: false,
  setAgentColumn: (open) => set({ agentColumn: open }),
  openFilters: () => set({ overlay: "filters" }),
  openAgent: () => set({ overlay: "agent" }),
  toggleAgent: () => set((state) => ({ overlay: state.overlay === "agent" ? "none" : "agent" })),
  closeOverlay: () => set({ overlay: "none" }),
}));
