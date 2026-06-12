// Hardcoded label/prefix constants and plugin config resolution.
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import type { ClawMemAgentConfig, ClawMemPluginConfig, ClawMemResolvedRoute } from "./types.js";
import { normalizeAgentId } from "./utils.js";

export const SESSION_TITLE_PREFIX = "Session: ";
export const DEFAULT_LABELS: readonly string[] = [];
export const AGENT_LABEL_PREFIX = "agent:";

const MANAGED_PREFIXES = ["type:", "kind:", "session:", "topic:", "agent:"];
const LEGACY_MANAGED_PREFIXES = ["date:", "status:", "memory-status:"];

export function resolvePluginConfig(api: OpenClawPluginApi): ClawMemPluginConfig {
  const raw = (api.pluginConfig ?? {}) as Record<string, unknown>;
  const str = (v: unknown) => typeof v === "string" && v.trim() ? v.trim() : undefined;
  const num = (v: unknown, d: number) => typeof v === "number" && Number.isFinite(v) ? Math.floor(v) : d;
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  const baseUrl = (str(raw.baseUrl) ?? "https://git.clawmem.ai").replace(/\/+$/, "");
  const rawAgents = raw.agents && typeof raw.agents === "object" && !Array.isArray(raw.agents)
    ? (raw.agents as Record<string, unknown>)
    : {};
  const agents: Record<string, ClawMemAgentConfig> = {};
  for (const [rawAgentId, rawAgentConfig] of Object.entries(rawAgents)) {
    if (!rawAgentConfig || typeof rawAgentConfig !== "object" || Array.isArray(rawAgentConfig)) continue;
    const agentId = normalizeAgentId(rawAgentId);
    const agent = rawAgentConfig as Record<string, unknown>;
    agents[agentId] = {
      baseUrl: str(agent.baseUrl)?.replace(/\/+$/, ""),
      defaultRepo: normalizeRepoName(str(agent.defaultRepo)),
      token: str(agent.token),
      authScheme: agent.authScheme === "bearer" ? "bearer" : agent.authScheme === "token" ? "token" : undefined,
    };
  }
  return {
    baseUrl: baseUrl.endsWith("/api/v3") ? baseUrl : `${baseUrl}/api/v3`,
    authScheme: raw.authScheme === "bearer" ? "bearer" : "token",
    agents,
    memoryAutoRecallLimit: clamp(num(raw.memoryAutoRecallLimit, 3), 1, 20),
    memoryAutoRecallStrategy: raw.memoryAutoRecallStrategy === "single" || raw.memoryAutoRecallStrategy === "literal-repair"
      ? raw.memoryAutoRecallStrategy
      : "query-planner",
    memoryAutoRecallPlannerVariantLimit: clamp(num(raw.memoryAutoRecallPlannerVariantLimit, 6), 1, 6),
    apiRequestRetries: clamp(num(raw.apiRequestRetries, 3), 0, 8),
    summaryWaitTimeoutMs: clamp(num(raw.summaryWaitTimeoutMs, 120000), 1000, 600000),
    transcriptCommentBatchSize: clamp(num(raw.transcriptCommentBatchSize, 1), 1, 50),
    conversationSummaryMode: raw.conversationSummaryMode === "placeholder" ? "placeholder" : "llm",
  };
}

export function resolveAgentRoute(config: ClawMemPluginConfig, agentId?: string, repoOverride?: string): ClawMemResolvedRoute {
  const id = normalizeAgentId(agentId);
  const agent = config.agents[id] ?? {};
  const baseUrl = (agent.baseUrl ?? config.baseUrl).replace(/\/+$/, "");
  const defaultRepo = normalizeRepoName(agent.defaultRepo);
  const repo = normalizeRepoName(repoOverride) ?? defaultRepo;
  return {
    agentId: id,
    baseUrl: baseUrl.endsWith("/api/v3") ? baseUrl : `${baseUrl}/api/v3`,
    ...(defaultRepo ? { defaultRepo } : {}),
    ...(repo ? { repo } : {}),
    token: agent.token?.trim() || undefined,
    authScheme: agent.authScheme === "bearer" ? "bearer" : agent.authScheme === "token" ? "token" : config.authScheme,
    apiRequestRetries: config.apiRequestRetries,
  };
}

export function isAgentConfigured(route: ClawMemResolvedRoute): boolean {
  return Boolean(route.baseUrl && route.token);
}

export function hasDefaultRepo(route: ClawMemResolvedRoute): boolean {
  return Boolean(route.defaultRepo);
}

export function resolveLabelColor(label: string): string {
  if (label.startsWith("type:")) return label === "type:memory" ? "5319e7" : "1d76db";
  if (label.startsWith("kind:")) return "5319e7";
  if (label.startsWith("topic:")) return "fbca04";
  if (label.startsWith("session:")) return "bfdadc";
  if (label.startsWith("agent:")) return "1d76db";
  return "0e8a16";
}

export function labelDescription(label: string): string {
  for (const [pfx, d] of [["type:", "Issue type"], ["kind:", "Memory kind"], ["session:", "Session association"],
    ["topic:", "Topic"], ["agent:", "Agent"]] as const)
    if (label.startsWith(pfx)) return `${d} label managed by clawmem.`;
  return "Label managed by clawmem.";
}

export function isManagedLabel(label: string): boolean {
  return DEFAULT_LABELS.includes(label)
    || MANAGED_PREFIXES.some((p) => label.startsWith(p))
    || LEGACY_MANAGED_PREFIXES.some((p) => label.startsWith(p));
}

export function extractLabelNames(labels: Array<{ name?: string } | string> | undefined): string[] {
  if (!Array.isArray(labels)) return [];
  return labels.map((e) => (typeof e === "string" ? e : e?.name ?? "").trim()).filter(Boolean);
}

export function labelVal(labels: string[], prefix: string): string | undefined {
  const m = labels.find((l) => l.startsWith(prefix));
  return m ? m.slice(prefix.length).trim() || undefined : undefined;
}

function normalizeRepoName(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const trimmed = value.trim().replace(/^\/+|\/+$/g, "");
  return /^[^/\s]+\/[^/\s]+$/.test(trimmed) ? trimmed : undefined;
}
