import { hasDefaultRepo, isAgentConfigured, resolveAgentRoute, resolvePluginConfig } from "./config.js";
import type { ClawMemPluginConfig } from "./types.js";
import { buildAgentBootstrapRegistration, DEFAULT_BOOTSTRAP_REPO_NAME } from "./utils.js";

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function baseConfig(): ClawMemPluginConfig {
  return {
    baseUrl: "https://git.clawmem.ai/api/v3",
    authScheme: "token",
    token: "top-token",
    defaultRepo: "global/default-memory",
    repo: "global/legacy-memory",
    agents: {
      main: {
        token: "agent-token",
        defaultRepo: "main/private-memory",
      },
      legacy: {
        token: "legacy-token",
        repo: "legacy/old-memory",
      },
      identityOnly: {
        token: "identity-token",
      },
    },
    memoryAutoRecallLimit: 3,
    memoryAutoRecallStrategy: "single",
    memoryAutoRecallPlannerVariantLimit: 6,
    apiRequestRetries: 3,
    summaryWaitTimeoutMs: 120000,
    transcriptCommentBatchSize: 1,
    conversationSummaryMode: "llm",
  };
}

function testDefaultRepoResolution(): void {
  const route = resolveAgentRoute(baseConfig(), "main");
  assert(route.defaultRepo === "main/private-memory", "expected per-agent defaultRepo to be preferred");
  assert(route.repo === "main/private-memory", "expected selected repo to default to defaultRepo");
  assert(route.token === "agent-token", "expected per-agent token to be preferred");
  assert(route.apiRequestRetries === 3, "expected route to carry API retry policy");
}

function testRepoOverride(): void {
  const route = resolveAgentRoute(baseConfig(), "main", "org/shared-memory");
  assert(route.defaultRepo === "main/private-memory", "expected defaultRepo to remain unchanged");
  assert(route.repo === "org/shared-memory", "expected explicit repo override to win");
}

function testLegacyRepoFallback(): void {
  const route = resolveAgentRoute(baseConfig(), "legacy");
  assert(route.defaultRepo === "legacy/old-memory", "expected legacy repo to act as defaultRepo fallback");
  assert(route.repo === "legacy/old-memory", "expected selected repo to use the legacy repo fallback");
}

function testIdentityOnlyStillConfigured(): void {
  const config = baseConfig();
  delete config.defaultRepo;
  delete config.repo;
  const route = resolveAgentRoute(config, "identityOnly");
  assert(isAgentConfigured(route) === true, "expected an identity with baseUrl and token to count as configured");
  assert(hasDefaultRepo(route) === false, "expected no default repo when only credentials are present");
}

function testBootstrapRegistrationUsesStableDefaults(): void {
  const registration = buildAgentBootstrapRegistration("Main_Coder");
  assert(registration.prefixLogin === "main-coder", "expected agent bootstrap login prefix to match backend format");
  assert(registration.defaultRepoName === DEFAULT_BOOTSTRAP_REPO_NAME, "expected bootstrap repo name to use the stable default");
}

function testBootstrapRegistrationTrimsLongPrefixes(): void {
  const registration = buildAgentBootstrapRegistration("___THIS_IS_A_SUPER_LONG_AGENT_ID_THAT_SHOULD_BE_TRIMMED___");
  assert(/^[a-z0-9][a-z0-9-]*$/.test(registration.prefixLogin), "expected bootstrap login prefix to satisfy backend validation");
  assert(registration.prefixLogin.length <= 32, "expected bootstrap login prefix to fit backend max length");
}

function testAutoRecallStrategyDefaultsToQueryPlanner(): void {
  const config = resolvePluginConfig({ pluginConfig: {} } as never);
  assert(config.memoryAutoRecallStrategy === "query-planner", "expected query-planner to be the default auto-recall strategy");
}

function testAutoRecallStrategyPreservesLegacyValues(): void {
  const single = resolvePluginConfig({ pluginConfig: { memoryAutoRecallStrategy: "single" } } as never);
  const repair = resolvePluginConfig({ pluginConfig: { memoryAutoRecallStrategy: "literal-repair" } } as never);
  assert(single.memoryAutoRecallStrategy === "single", "expected explicit single strategy to be preserved");
  assert(repair.memoryAutoRecallStrategy === "literal-repair", "expected explicit literal-repair strategy to be preserved");
}

function testAutoRecallPlannerVariantLimitDefaultsAndClamps(): void {
  const defaults = resolvePluginConfig({ pluginConfig: {} } as never);
  const low = resolvePluginConfig({ pluginConfig: { memoryAutoRecallPlannerVariantLimit: 0 } } as never);
  const high = resolvePluginConfig({ pluginConfig: { memoryAutoRecallPlannerVariantLimit: 99 } } as never);
  assert(defaults.memoryAutoRecallPlannerVariantLimit === 6, "expected planner variant limit to default to 6");
  assert(low.memoryAutoRecallPlannerVariantLimit === 1, "expected planner variant limit to clamp low values");
  assert(high.memoryAutoRecallPlannerVariantLimit === 6, "expected planner variant limit to clamp high values");
}

testDefaultRepoResolution();
testRepoOverride();
testLegacyRepoFallback();
testIdentityOnlyStillConfigured();
testBootstrapRegistrationUsesStableDefaults();
testBootstrapRegistrationTrimsLongPrefixes();
testAutoRecallStrategyDefaultsToQueryPlanner();
testAutoRecallStrategyPreservesLegacyValues();
testAutoRecallPlannerVariantLimitDefaultsAndClamps();

console.log("config tests passed");
