import type { AgentStatus } from "@/stores/agent-session-store";

interface ReplayBannerProps {
  status: AgentStatus;
}

/** "Live budget spent" mode switch (spec §4c). Two budget-exhausted shapes
 * reach here: REPLAY (server streams a recorded showcase run through the
 * identical wire shape) and DENY/capped (HTTP 429, no stream at all) — both
 * render a banner so the panel always explains why an answer looks the way
 * it does, instead of the visitor guessing. */
export function ReplayBanner({ status }: ReplayBannerProps) {
  if (status.kind !== "replay" && status.kind !== "capped") return null;

  const message =
    status.kind === "replay"
      ? "Live budget spent for now — you're watching a recorded session."
      : "Live budget spent and no recorded session is available right now.";

  return (
    <div className="bg-amber-soft border-amber border-t px-3.5 py-2.5 text-xs leading-relaxed text-[#6b4a10]">
      {message} {status.reason}
    </div>
  );
}
