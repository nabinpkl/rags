import { afterEach, describe, expect, it, vi } from "vitest";

import { agentEnabled } from "@/lib/agent-flag";

afterEach(() => vi.unstubAllEnvs());

describe("agentEnabled", () => {
  it("is on only for the literal string true", () => {
    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "true");
    expect(agentEnabled()).toBe(true);
  });

  it("is off when unset or set to anything else", () => {
    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "");
    expect(agentEnabled()).toBe(false);
    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "1");
    expect(agentEnabled()).toBe(false);
  });
});
