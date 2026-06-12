import fs from "node:fs";
import path from "node:path";
import type { PluginState, SessionDerivedState, SessionMirrorState, SessionTaskStatus } from "./types.js";
import { normalizeAgentId, sessionScopeKey } from "./utils.js";

const EMPTY_STATE: PluginState = {
  version: 4,
  sessions: {},
};

export function resolveStatePath(stateDir: string): string {
  return path.join(stateDir, "clawmem", "state.json");
}

export async function loadState(filePath: string): Promise<PluginState> {
  try {
    const raw = await fs.promises.readFile(filePath, "utf8");
    return sanitizeState(JSON.parse(raw));
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === "ENOENT") {
      return structuredClone(EMPTY_STATE);
    }
    return structuredClone(EMPTY_STATE);
  }
}

export async function saveState(filePath: string, state: PluginState): Promise<void> {
  await fs.promises.mkdir(path.dirname(filePath), { recursive: true, mode: 0o700 });
  const next = JSON.stringify(state, null, 2) + "\n";
  const tmpPath = `${filePath}.tmp-${process.pid}-${Date.now()}`;
  await fs.promises.writeFile(tmpPath, next, { encoding: "utf8", mode: 0o600 });
  await fs.promises.rename(tmpPath, filePath);
}

function sanitizeState(value: unknown): PluginState {
  if (!value || typeof value !== "object") {
    return structuredClone(EMPTY_STATE);
  }
  const raw = value as Record<string, unknown>;
  if (raw.version !== EMPTY_STATE.version) {
    return structuredClone(EMPTY_STATE);
  }
  const sessions = raw.sessions && typeof raw.sessions === "object"
    ? (raw.sessions as Record<string, unknown>)
    : {};
  const migrations: Record<string, string> = {};
  if (raw.migrations && typeof raw.migrations === "object") {
    for (const [k, v] of Object.entries(raw.migrations as Record<string, unknown>)) {
      const s = readString(v);
      if (s) migrations[k] = s;
    }
  }
  const out: PluginState = {
    version: 4,
    sessions: {},
    ...(Object.keys(migrations).length > 0 ? { migrations } : {}),
  };
  for (const [storedKey, sessionValue] of Object.entries(sessions)) {
    if (!sessionValue || typeof sessionValue !== "object" || !storedKey.trim()) continue;
    const rawSession = sessionValue as Record<string, unknown>;
    const sessionId = readString(rawSession.sessionId) ?? storedKey.trim();
    if (!sessionId) continue;
    const agentId = normalizeAgentId(readString(rawSession.agentId));
    const lastMirroredCount = readNumber(rawSession.lastMirroredCount) ?? 0;
    const finalizedAt = readString(rawSession.finalizedAt);
    const derived = sanitizeDerivedState(rawSession, lastMirroredCount, finalizedAt);
    out.sessions[sessionScopeKey(sessionId, agentId)] = {
      sessionId,
      sessionKey: readString(rawSession.sessionKey),
      sessionFile: readString(rawSession.sessionFile),
      agentId,
      repo: readRepo(rawSession.repo),
      issueNumber: readNumber(rawSession.issueNumber),
      issueTitle: readString(rawSession.issueTitle),
      titleSource: readTitleSource(rawSession.titleSource),
      lastMirroredCount,
      turnCount: readNumber(rawSession.turnCount) ?? 0,
      lastMirrorError: readString(rawSession.lastMirrorError),
      lastMirrorAttemptAt: readString(rawSession.lastMirrorAttemptAt),
      finalizedAt,
      lastSummaryHash: readString(rawSession.lastSummaryHash),
      derived,
      createdAt: readString(rawSession.createdAt),
      updatedAt: readString(rawSession.updatedAt),
    };
  }
  return out;
}

function sanitizeDerivedState(
  rawSession: Record<string, unknown>,
  lastMirroredCount: number,
  finalizedAt?: string,
): SessionDerivedState {
  const rawDerived = asRecord(rawSession.derived);
  const rawSummary = asRecord(rawDerived?.summary);
  const summaryText = readString(rawSummary?.text);
  const summaryTitle = readString(rawSummary?.title);
  const status = readTaskStatus(
    rawSummary?.status,
    summaryText ? "complete" : "idle",
  );
  const summaryCursor = clampCursor(
    readNumber(rawSummary?.basedOnCursor),
    status === "complete" ? lastMirroredCount : 0,
    lastMirroredCount,
  );

  return {
    summary: {
      basedOnCursor: summaryCursor,
      status: finalizedAt && status === "idle" && lastMirroredCount > 0 ? "error" : status,
      ...(summaryText ? { text: summaryText } : {}),
      ...(summaryTitle ? { title: summaryTitle } : {}),
      ...(readString(rawSummary?.lastError) ? { lastError: readString(rawSummary?.lastError) } : {}),
      ...(readString(rawSummary?.updatedAt) ? { updatedAt: readString(rawSummary?.updatedAt) } : {}),
    },
  };
}

function readString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function readEnum<T extends string>(value: unknown, allowed: T[]): T | undefined {
  const s = readString(value);
  return s && (allowed as string[]).includes(s) ? (s as T) : undefined;
}

function readNumber(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Math.max(0, Math.floor(value));
}

function readRepo(value: unknown): string | undefined {
  const repo = readString(value);
  return repo && /^[^/\s]+\/[^/\s]+$/.test(repo) ? repo : undefined;
}

function readTaskStatus(value: unknown, defaultStatus: SessionTaskStatus): SessionTaskStatus {
  const status = readEnum(value, ["idle", "complete", "error"]);
  if (!status) return defaultStatus;
  return status;
}

function readTitleSource(value: unknown): "placeholder" | "llm" | undefined {
  return readEnum(value, ["placeholder", "llm"]);
}

function clampCursor(value: number | undefined, defaultValue: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return Math.min(max, Math.max(0, defaultValue));
  return Math.min(max, Math.max(0, Math.floor(value)));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}
