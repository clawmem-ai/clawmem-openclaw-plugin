export function getOpenClawAgentIdFromEnv(): string | undefined {
  const value = process.env.OPENCLAW_AGENT_ID;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
