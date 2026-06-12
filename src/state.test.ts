import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { loadState } from "./state.js";

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

async function withTempStateFile(payload: unknown, fn: (filePath: string) => Promise<void>): Promise<void> {
  const dir = await fs.promises.mkdtemp(path.join(os.tmpdir(), "clawmem-state-"));
  const filePath = path.join(dir, "state.json");
  try {
    await fs.promises.writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
    await fn(filePath);
  } finally {
    await fs.promises.rm(dir, { recursive: true, force: true });
  }
}

async function testIgnoresNonCurrentStateVersion(): Promise<void> {
  await withTempStateFile({
    version: 3,
    sessions: {
      "main:s-1": {
        sessionId: "s-1",
        agentId: "main",
        issueNumber: 10,
        lastMirroredCount: 6,
        turnCount: 6,
      },
    },
  }, async (filePath) => {
    const state = await loadState(filePath);
    assert(state.version === 4, "expected loader to return current empty state");
    assert(Object.keys(state.sessions).length === 0, "expected non-current state versions to be ignored");
  });
}

async function testInvalidTaskStatesUseCurrentFallback(): Promise<void> {
  await withTempStateFile({
    version: 4,
    sessions: {
      "main:s-2": {
        sessionId: "s-2",
        agentId: "main",
        lastMirroredCount: 3,
        turnCount: 3,
        derived: {
          summary: { basedOnCursor: 0, status: "running" },
        },
      },
    },
  }, async (filePath) => {
    const state = await loadState(filePath);
    const session = state.sessions["main:s-2"];
    assert(session?.derived?.summary.status === "idle", "expected invalid summary task states to use the current default");
  });
}

async function testPreservesCachedFinalArtifacts(): Promise<void> {
  await withTempStateFile({
    version: 4,
    sessions: {
      "main:s-3": {
        sessionId: "s-3",
        agentId: "main",
        lastMirroredCount: 5,
        turnCount: 5,
        derived: {
          summary: {
            basedOnCursor: 5,
            status: "idle",
            text: "Recovered summary",
            title: "Recovered title",
          },
          memory: {
            capturedCursor: 0,
            status: "error",
            candidates: [
              {
                candidateId: "cand-1",
                detail: "Store this durable fact.",
                kind: "lesson",
                topics: ["redis"],
              },
            ],
          },
        },
      },
    },
  }, async (filePath) => {
    const state = await loadState(filePath);
    const session = state.sessions["main:s-3"];
    assert(session?.derived?.summary.title === "Recovered title", "expected cached finalize title to survive state load");
    assert(!("memory" in (session?.derived ?? {})), "expected cached memory candidates to be dropped because retention is skill-driven");
  });
}

async function testPreservesSessionRepo(): Promise<void> {
  await withTempStateFile({
    version: 4,
    sessions: {
      "main:s-4": {
        sessionId: "s-4",
        agentId: "main",
        repo: "team/project-memory",
        lastMirroredCount: 1,
        turnCount: 1,
      },
    },
  }, async (filePath) => {
    const state = await loadState(filePath);
    const session = state.sessions["main:s-4"];
    assert(session?.repo === "team/project-memory", "expected session repo routing to survive state load");
  });
}

async function testPreservesMirrorError(): Promise<void> {
  await withTempStateFile({
    version: 4,
    sessions: {
      "main:s-5": {
        sessionId: "s-5",
        agentId: "main",
        lastMirroredCount: 3,
        turnCount: 3,
        lastMirrorError: "fetch failed",
        lastMirrorAttemptAt: "2026-05-07T10:00:00.000Z",
      },
    },
  }, async (filePath) => {
    const state = await loadState(filePath);
    const session = state.sessions["main:s-5"];
    assert(session?.lastMirrorError === "fetch failed", "expected mirror errors to survive state load");
    assert(session?.lastMirrorAttemptAt === "2026-05-07T10:00:00.000Z", "expected mirror attempt timestamp to survive state load");
  });
}

await testIgnoresNonCurrentStateVersion();
await testInvalidTaskStatesUseCurrentFallback();
await testPreservesCachedFinalArtifacts();
await testPreservesSessionRepo();
await testPreservesMirrorError();

console.log("state tests passed");
