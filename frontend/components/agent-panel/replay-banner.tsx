import type { AgentMode, AgentStatus } from "@/stores/agent-session-store";

interface ReplayBannerProps {
  mode: AgentMode;
  status: AgentStatus;
}

/** "Live budget spent" mode switch (spec §4c). Two budget-exhausted shapes
 * reach here: REPLAY (server streams a recorded showcase run through the
 * identical wire shape — session MODE, `mode.kind`) and DENY/capped (HTTP
 * 429, no stream at all — turn lifecycle, `status.kind`) — both render a
 * banner so the panel always explains why an answer looks the way it does,
 * instead of the visitor guessing. These two are read from separate fields
 * on purpose (DECISIONS.md 2026-07-09 round 2): `status` churns with every
 * SSE event for the whole replayed answer, so a replay indicator living
 * there gets clobbered mid-stream; `mode` is set once, in onopen, and
 * `applyEvent` never touches it. */
export function ReplayBanner({ mode, status }: ReplayBannerProps) {
  if (mode.kind === "replay") {
    const message = "Live budget spent for now — you're watching a recorded session.";
    return (
      <div className="bg-amber-soft border-amber border-t px-3.5 py-2.5 text-xs leading-relaxed text-amber-ink">
        {message} {mode.reason}
      </div>
    );
  }

  if (status.kind === "capped") {
    return (
      <div className="bg-amber-soft border-amber border-t px-3.5 py-2.5 text-xs leading-relaxed text-amber-ink">
        Live budget spent and no recorded session is available right now. {status.reason}
      </div>
    );
  }

  return null;
}
