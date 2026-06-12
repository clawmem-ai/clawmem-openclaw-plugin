// Shared types for the clawmem plugin.
export type ClawMemAgentConfig = {
  baseUrl?: string;
  defaultRepo?: string;
  token?: string;
  authScheme?: "token" | "bearer";
};

export type ClawMemPluginConfig = {
  baseUrl: string;
  authScheme: "token" | "bearer";
  agents: Record<string, ClawMemAgentConfig>;
  memoryAutoRecallLimit: number;
  memoryAutoRecallStrategy: "single" | "literal-repair" | "query-planner";
  memoryAutoRecallPlannerVariantLimit: number;
  apiRequestRetries: number;
  summaryWaitTimeoutMs: number;
  transcriptCommentBatchSize: number;
  conversationSummaryMode: "llm" | "placeholder";
};

export type ClawMemResolvedRoute = {
  agentId: string;
  baseUrl: string;
  defaultRepo?: string;
  repo?: string;
  token?: string;
  authScheme: "token" | "bearer";
  apiRequestRetries: number;
};

export type BootstrapIdentityResponse = { token: string; repo_full_name: string };
export type AgentRegistrationResponse = BootstrapIdentityResponse & { login: string };
export type SessionTaskStatus = "idle" | "complete" | "error";
export type SessionSummaryState = {
  basedOnCursor: number;
  status: SessionTaskStatus;
  text?: string;
  title?: string;
  lastError?: string;
  updatedAt?: string;
};
export type SessionDerivedState = {
  summary: SessionSummaryState;
};
export type SessionMirrorState = {
  sessionId: string; sessionKey?: string; sessionFile?: string; agentId?: string; repo?: string;
  issueNumber?: number; issueTitle?: string; titleSource?: "placeholder" | "llm";
  lastMirroredCount: number; turnCount: number;
  lastMirrorError?: string; lastMirrorAttemptAt?: string;
  finalizedAt?: string; lastSummaryHash?: string;
  derived?: SessionDerivedState;
  createdAt?: string; updatedAt?: string;
};
export type PluginState = { version: 4; sessions: Record<string, SessionMirrorState>; migrations?: Record<string, string> };
export type NormalizedMessage = { role: string; text: string; toolName?: string; timestamp?: string; stopReason?: string };
export type TranscriptSnapshot = { sessionId?: string; messages: NormalizedMessage[] };
export type ParsedMemoryIssue = {
  issueNumber: number; title: string; memoryId: string; memoryHash?: string;
  date: string; detail: string;
  kind?: string; topics?: string[]; sourceRefs?: string[]; wikiAnchors?: string[]; status: "active" | "stale";
};
