/** Whether this build shows the agent. Baked at build time from
 * NEXT_PUBLIC_AGENT_ENABLED, which deploy/compose.yml feeds from the same
 * ASKRAG_AGENT_ENABLED that gates POST /api/chat on the server, so the two
 * halves move together. Off unless set to "true": the server's refusal is
 * the guarantee, this only keeps a dead control off the page.
 *
 * A function, not a constant, so a test can stub the variable per case;
 * Next inlines `process.env.NEXT_PUBLIC_*` wherever it is read. */
export function agentEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AGENT_ENABLED === "true";
}
