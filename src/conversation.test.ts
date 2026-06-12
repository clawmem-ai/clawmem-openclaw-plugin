// Tests for conversation title derivation logic.
import { ConversationMirror, batchTranscriptComments, buildFinalizeArtifactsPrompt, deriveInitialTitle } from "./conversation.js";
import type { NormalizedMessage, SessionMirrorState } from "./types.js";

function msg(role: string, text: string): NormalizedMessage {
  return { role, text };
}

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

const tests: Array<{ name: string; messages: NormalizedMessage[]; sessionId: string; expected: string }> = [
  {
    name: "returns placeholder regardless of user message content",
    messages: [msg("user", "How do I configure Redis rate limiting?")],
    sessionId: "abc123",
    expected: "Session: abc123",
  },
  {
    name: "returns placeholder for long messages",
    messages: [msg("user", "I need help with configuring the distributed rate limiting system for our production Redis cluster")],
    sessionId: "abc123",
    expected: "Session: abc123",
  },
  {
    name: "returns placeholder for messages with markdown",
    messages: [msg("user", "## How do I **configure** `Redis` rate limiting?")],
    sessionId: "abc123",
    expected: "Session: abc123",
  },
  {
    name: "returns placeholder for short messages",
    messages: [msg("user", "hi")],
    sessionId: "abc-def-123",
    expected: "Session: abc-def-123",
  },
  {
    name: "returns placeholder when no user messages",
    messages: [msg("assistant", "Hello!")],
    sessionId: "xyz-789",
    expected: "Session: xyz-789",
  },
  {
    name: "returns placeholder for empty messages",
    messages: [],
    sessionId: "empty-sess",
    expected: "Session: empty-sess",
  },
  {
    name: "returns placeholder with session ID for any input",
    messages: [msg("assistant", "Welcome!"), msg("user", "Fix the login bug please")],
    sessionId: "abc",
    expected: "Session: abc",
  },
];

let passed = 0;
let failed = 0;

async function testLoadSnapshotPrefersFallbackMessages(): Promise<void> {
  const mirror = new ConversationMirror(
    {} as never,
    { logger: { warn() {}, info() {} } } as never,
    {} as never,
  );
  const session: SessionMirrorState = {
    sessionId: "sync-session",
    sessionFile: "/tmp/does-not-need-to-exist.jsonl",
    lastMirroredCount: 0,
    turnCount: 0,
  };
  const snapshot = await mirror.loadSnapshot(session, [{ role: "user", text: "Use the in-request transcript." }]);
  assert(snapshot.messages.length === 1, "expected loadSnapshot to return in-request messages");
  assert(snapshot.messages[0]?.text === "Use the in-request transcript.", "expected loadSnapshot to prefer in-request messages over transcript files");
}

function testBuildFinalizeArtifactsPromptOnlySummarizesConversation(): void {
  const prompt = buildFinalizeArtifactsPrompt({
    sessionId: "finalize-session",
    messages: [
      msg("user", "请记住我们现在统一用 Redis 做限流。"),
      msg("assistant", "好的，我会按这个约定处理。"),
    ],
  });

  assert(prompt.includes('Return valid JSON only in the form {"summary":"...","title":"..."}.'), "expected summary/title-only JSON contract");
  assert(prompt.includes("Do not extract durable memories."), "expected finalization to avoid memory extraction");
  assert(!prompt.includes('"candidates"'), "expected no candidate JSON schema in the finalize prompt");
  assert(!prompt.includes("kind:"), "expected no memory label schema in the finalize prompt");
}

function testBatchTranscriptCommentsDefaultsToSingleMessageComments(): void {
  const batches = batchTranscriptComments(
    Array.from({ length: 3 }, (_, index) => msg(index % 2 === 0 ? "user" : "assistant", `message ${index + 1}`)),
  );

  assert(batches.length === 3, "expected default transcript comments to keep one message per comment");
  assert(batches.every((batch) => batch.count === 1), "expected each default comment to count one mirrored message");
  assert(batches.every((batch) => !batch.body.includes("---")), "expected no separator for single-message comments");
}

function testBatchTranscriptCommentsCombinesOnlyWhenOptedIn(): void {
  const batches = batchTranscriptComments(
    Array.from({ length: 25 }, (_, index) => msg(index % 2 === 0 ? "user" : "assistant", `message ${index + 1}`)),
    undefined,
    20,
  );

  assert(batches.length === 2, "expected explicit batching to combine up to 20 messages per comment");
  assert(batches[0]?.count === 20, "expected first batch to count 20 mirrored messages");
  assert(batches[1]?.count === 5, "expected second batch to count remaining messages");
  assert(batches[0]?.body.includes("---"), "expected combined comment to separate messages");
}

function testBatchTranscriptCommentsSplitsOversizeMessage(): void {
  const batches = batchTranscriptComments([msg("user", "x".repeat(500))], 220, 20);
  const totalCount = batches.reduce((sum, batch) => sum + batch.count, 0);
  const markers = batches.flatMap((batch) => [...batch.body.matchAll(/^marker: (.+)$/gm)].map((match) => match[1]));

  assert(batches.length > 1, "expected oversized message to split into multiple comments");
  assert(totalCount === 1, "expected split oversized message to count as one mirrored message");
  assert(batches.every((batch) => batch.body.length <= 220), "expected split comments to respect maxChars");
  assert(batches[0]?.body.includes("part: 1/"), "expected split comments to include part metadata");
  assert(new Set(markers).size === markers.length, "expected split comments to use unique retry markers");
}

async function main(): Promise<void> {
  for (const t of tests) {
    const got = deriveInitialTitle(t.messages, t.sessionId);
    const ok = got === t.expected;
    if (!ok) {
      console.error(`FAIL: ${t.name}\n  got:      ${JSON.stringify(got)}\n  expected: ${JSON.stringify(t.expected)}`);
      failed++;
    } else {
      console.log(`PASS: ${t.name}`);
      passed++;
    }
  }
  await testLoadSnapshotPrefersFallbackMessages();
  console.log("PASS: loadSnapshot prefers in-request messages");
  testBuildFinalizeArtifactsPromptOnlySummarizesConversation();
  console.log("PASS: buildFinalizeArtifactsPrompt only summarizes conversation");
  testBatchTranscriptCommentsDefaultsToSingleMessageComments();
  console.log("PASS: batchTranscriptComments defaults to single-message comments");
  testBatchTranscriptCommentsCombinesOnlyWhenOptedIn();
  console.log("PASS: batchTranscriptComments combines only when opted in");
  testBatchTranscriptCommentsSplitsOversizeMessage();
  console.log("PASS: batchTranscriptComments splits oversized messages");

  console.log(`\n${passed + 5} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
}

await main();
