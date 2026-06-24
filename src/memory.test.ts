import { MemoryStore } from "./memory.js";

type IssueRecord = { number: number; title?: string; body?: string; state?: "open" | "closed"; labels?: Array<{ name?: string } | string> };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function markdownMemory(overrides: {
  issueNumber?: number;
  title?: string;
  detail?: string;
  kind?: string;
  topics?: string[];
  sourceRefs?: string[];
  state?: "open" | "closed";
} = {}): IssueRecord {
  const refs = overrides.sourceRefs ?? [];
  return {
    number: overrides.issueNumber ?? 1,
    title: overrides.title ?? "Memory: Example",
    body: [
      "## Memory",
      "",
      overrides.detail ?? "Example durable detail.",
      "",
      ...(refs.length > 0 ? ["## Relations", "", ...refs.map((ref) => `- source: ${ref}`), ""] : []),
      "<!-- clawmem",
      "schema_version: clawmem/v2",
      "valid_from: 2026-03-23",
      "valid_to:",
      "-->",
    ].join("\n"),
    state: overrides.state ?? "open",
    labels: [
      "type:memory",
      ...(overrides.kind ? [`kind:${overrides.kind}`] : []),
      ...((overrides.topics ?? []).map((topic) => `topic:${topic}`)),
    ],
  };
}

async function testBackendSearchBuildsSingleCleanedQuery(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never);
  await store.search([
    "<clawmem-context>",
    "- [11] Previous memory that should be stripped",
    "</clawmem-context>",
    "Conversation info (untrusted metadata):",
    "```json",
    '{"channel":"slack"}',
    "```",
    "",
    "[message_id: abc-123]",
    "",
    "[Slack 2026-04-03 09:30]: Please help debug the Redis rate limiting path.",
    "See https://example.com/debug for more context.",
    "throw new TimeoutError('lua script timeout')",
    "[System: auto-translated]",
  ].join("\n"), 5);

  assert(queries.length === 1, "expected a single backend search query");
  assert(queries[0]?.includes("repo:owner/main-memory"), "expected the backend query to stay scoped to the repo");
  assert(queries[0]?.includes('label:"type:memory"'), "expected the backend query to filter memory issues");
  assert((queries[0] ?? "").length <= 1610, "expected the backend search query to stay within the configured cap plus qualifiers");
  assert(queries[0]?.toLowerCase().includes("redis"), "expected the backend query to retain key terms");
  assert(!queries[0]?.includes("<clawmem-context>"), "expected injected clawmem context to be stripped");
  assert(!queries[0]?.includes("https://example.com/debug"), "expected URLs to be stripped from backend recall");
  assert(!queries[0]?.includes("Conversation info (untrusted metadata):"), "expected inbound metadata blocks to be stripped");
  assert(!queries[0]?.includes("[message_id:"), "expected message id hints to be stripped");
  assert(!queries[0]?.includes("[Slack 2026-04-03 09:30]"), "expected envelope prefixes to be stripped");
  assert(!queries[0]?.includes("[System: auto-translated]"), "expected trailing system hints to be stripped");
}

async function testBackendSearchPreferredForRecall(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      return [markdownMemory({
        issueNumber: 2,
        title: "Memory: semantic winner",
        detail: "Use Lua scripts to keep Redis rate limiting atomic.",
        kind: "lesson",
        topics: ["redis"],
        sourceRefs: ["#123"],
      })];
    },
  };
  const store = new MemoryStore(client as never);
  const found = await store.search("redis rate limiting", 1);

  assert(queries.length === 1, "expected backend search to be called once");
  assert(queries[0]?.includes("repo:owner/main-memory"), "expected backend query to scope to the current repo");
  assert(queries[0]?.includes('label:"type:memory"'), "expected backend query to filter memory issues");
  assert(found.length === 1 && found[0]?.issueNumber === 2, "expected backend search results to be preferred");
  assert(found[0]?.detail === "Use Lua scripts to keep Redis rate limiting atomic.", "expected Markdown memory detail to be parsed");
  assert(found[0]?.kind === "lesson", "expected kind label to be parsed");
  assert(JSON.stringify(found[0]?.topics) === JSON.stringify(["redis"]), "expected topic labels to be parsed");
  assert(JSON.stringify(found[0]?.sourceRefs) === JSON.stringify(["#123"]), "expected source refs to be parsed from Relations");
}

async function testLiteralRepairCanReserveLexicalSlot(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string, params?: { debug?: boolean }) => {
      queries.push(query);
      if (params?.debug) {
        return [
          markdownMemory({
            issueNumber: 99,
            title: "Memory: Caroline support group date",
            detail: "Caroline went to the LGBTQ support group on 2023-05-07.",
          }) as IssueRecord & { debug: { search_path: string; lexical_rank: number } },
        ].map((issue) => ({ ...issue, debug: { search_path: "hybrid", lexical_rank: 1 } }));
      }
      return [
        markdownMemory({ issueNumber: 1, title: "Memory: first", detail: "First semantic memory." }),
        markdownMemory({ issueNumber: 2, title: "Memory: second", detail: "Second semantic memory." }),
        markdownMemory({ issueNumber: 3, title: "Memory: third", detail: "Third semantic memory." }),
      ];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "literal-repair" });
  const found = await store.search("When did Caroline go to the LGBTQ support group?", 3);

  assert(queries.length === 2, "expected full query plus one compact repair query");
  assert(found.map((memory) => memory.issueNumber).join(",") === "1,2,99", "expected lexical repair memory to occupy the reserved tail slot");
}

async function testLiteralRepairIgnoresSemanticOnlyRepairHits(): Promise<void> {
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (_query: string, params?: { debug?: boolean }) => {
      if (params?.debug) {
        return [
          {
            ...markdownMemory({ issueNumber: 99, detail: "Semantic-only repair hit should not be inserted." }),
            debug: { search_path: "semantic_only", lexical_rank: 0 },
          },
        ];
      }
      return [
        markdownMemory({ issueNumber: 1, detail: "First semantic memory." }),
        markdownMemory({ issueNumber: 2, detail: "Second semantic memory." }),
        markdownMemory({ issueNumber: 3, detail: "Third semantic memory." }),
      ];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "literal-repair" });
  const found = await store.search("When did Caroline go to the LGBTQ support group?", 3);

  assert(found.map((memory) => memory.issueNumber).join(",") === "1,2,3", "expected semantic-only repair hits to leave full recall unchanged");
}

async function testQueryPlannerUsesStableCompactVariants(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      if (query.includes("James cooking class")) {
        return [{
          ...markdownMemory({
            issueNumber: 44,
            title: "Memory: James cooking class",
            detail: "James signed up for a cooking class because he wanted to learn something new.",
          }),
          debug: { search_path: "lexical_only", lexical_rank: 1 },
        }];
      }
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "query-planner" });
  const found = await store.search("Why did James sign up for a cooking class?", 3);

  assert(found[0]?.issueNumber === 44, "expected query planner to recall the compact lexical memory");
  assert(queries.some((query) => query.includes("James cooking class")), "expected compact query to keep James intact");
  assert(!queries.some((query) => query.includes("Jam cooking class")), "expected query planner not to singularize proper names");
}

async function testQueryPlannerNormalizesKnownLexicalPitfalls(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "query-planner" });

  await store.search("Why did John's teammates sign the basketball they gave him?", 3);
  await store.search("How did Gina promote her clothes store?", 3);
  await store.search("Where did Tim take the Smoky Mountains photo?", 3);

  assert(queries.some((query) => query.includes("John teammate basketball")), "expected teammates to normalize to teammate, not a broken stem");
  assert(!queries.some((query) => /\bteammat\b/.test(query)), "expected teammates not to become teammat");
  assert(queries.some((query) => query.includes("Gina clothing store")), "expected clothes to normalize to clothing");
  assert(!queries.some((query) => /\bGina cloth store\b/.test(query)), "expected clothes not to become cloth");
  assert(queries.some((query) => query.includes("Tim Smoky Mountains photo")), "expected surface query to preserve proper plural Mountains");
}

async function testQueryPlannerCoreVariantCanBeatBroadEntityVariant(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      if (query.includes("Sam kayaking")) {
        return [{
          ...markdownMemory({
            issueNumber: 85,
            title: "Memory: Sam kayaking",
            detail: "Sam and his friend decided to try kayaking on 2023-10-14.",
          }),
          debug: { search_path: "lexical_only", lexical_rank: 1 },
        }];
      }
      if (query.includes("Sam repo:")) {
        return [{
          ...markdownMemory({
            issueNumber: 5,
            title: "Memory: Sam broad profile",
            detail: "Sam had many unrelated activities.",
          }),
          debug: { search_path: "lexical_only", lexical_rank: 1 },
        }];
      }
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "query-planner", plannerVariantLimit: 6 });
  const found = await store.search("When did Sam and his friend decide to try kayaking?", 2);

  assert(queries.some((query) => query.includes("Sam kayaking")), "expected core query to drop weak friend term");
  assert(found.map((memory) => memory.issueNumber).join(",") === "85,5", "expected core lexical hit to rank before broad entity variant");
}

async function testQueryPlannerVariantLimitThreeSkipsBroadEntityVariants(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "query-planner", plannerVariantLimit: 3 });
  await store.search("When did Sam and his friend decide to try kayaking?", 2);

  assert(queries.length === 3, "expected planner variant limit 3 to run only full, compact, and core variants");
  assert(!queries.some((query) => query.includes("Sam repo:")), "expected planner variant limit 3 not to run the broad entity-only variant");
}

async function testQueryPlannerVariantLimitCanBeLowered(): Promise<void> {
  const queries: string[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async (query: string) => {
      queries.push(query);
      return [] as IssueRecord[];
    },
  };
  const store = new MemoryStore(client as never, { recallStrategy: "query-planner", plannerVariantLimit: 2 });
  await store.search("Why did James sign up for a cooking class?", 3);

  assert(queries.length === 2, "expected explicit planner variant limit to cap search fanout");
  assert(queries.some((query) => query.includes("James sign up")), "expected full query to run");
  assert(queries.some((query) => query.includes("James cooking class")), "expected compact query to run");
}

async function testBackendSearchReturnsEmptyWithoutLexicalFallback(): Promise<void> {
  const client = {
    repo: () => "owner/main-memory",
    listIssues: async () => { throw new Error("recall should not scan issues locally"); },
    searchIssues: async () => [] as IssueRecord[],
  };
  const store = new MemoryStore(client as never);
  const found = await store.search("redis rate limiting", 5);

  assert(found.length === 0, "expected backend-only recall to return no results when the backend finds nothing");
}

async function testClosedIssuesAreFilteredFromRecall(): Promise<void> {
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async () => [
      markdownMemory({ issueNumber: 8, detail: "Closed memories should not be recalled.", state: "closed" }),
      markdownMemory({ issueNumber: 9, detail: "Open memories should be recalled.", state: "open" }),
    ],
  };
  const store = new MemoryStore(client as never);
  const found = await store.search("memories", 5);

  assert(found.length === 1, "expected closed memory issues to be filtered out");
  assert(found[0]?.issueNumber === 9, "expected open memory issue to remain");
}

async function testWikiContextBoostsReferencedMemoryIssues(): Promise<void> {
  const viewed: number[] = [];
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async () => [
      markdownMemory({ issueNumber: 1, title: "Memory: primary one", detail: "Primary memory one." }),
      markdownMemory({ issueNumber: 2, title: "Memory: primary two", detail: "Primary memory two." }),
      markdownMemory({ issueNumber: 3, title: "Memory: primary three", detail: "Primary memory three." }),
    ],
    searchWikiPages: async () => [{
      slug: "projects/clawmem",
      score: 10,
      snippet: "Architecture context refs: #99",
    }],
    getWikiPage: async () => ({
      slug: "projects/clawmem",
      body: [
        "---",
        "type: ClawMem Knowledge Page",
        "title: Project: ClawMem",
        "description: Current ClawMem architecture context.",
        "resource: owner/main-memory#55",
        "tags: [project, clawmem]",
        "timestamp: 2026-06-24T00:00:00Z",
        "---",
        "",
        "# Context",
        "",
        "- Wiki is compiled knowledge, not memory ground truth. refs: #99",
        "- Conversation refs stay provenance. refs: #77",
        "```",
        "#66 should not count from code.",
        "```",
      ].join("\n"),
    }),
    getIssue: async (n: number) => {
      viewed.push(n);
      if (n === 99) {
        return markdownMemory({
          issueNumber: 99,
          title: "Memory: wiki architecture",
          detail: "ClawMem wiki pages are compiled knowledge and issue memories are source of truth.",
          kind: "decision",
        });
      }
      return {
        number: n,
        title: "Conversation source",
        body: "Raw transcript provenance.",
        state: "open",
        labels: ["type:conversation"],
      };
    },
  };
  const store = new MemoryStore(client as never);
  const bundle = await store.searchWithContext("clawmem architecture wiki", 3);

  assert(bundle.wikiContexts.length === 1, "expected relevant wiki context to be returned");
  assert(bundle.wikiContexts[0]?.title === "Project: ClawMem", "expected OKF frontmatter title to be used");
  assert(JSON.stringify(bundle.wikiContexts[0]?.issueRefs) === JSON.stringify(["#99", "#77"]), "expected wiki refs to ignore frontmatter and code blocks");
  assert(viewed.includes(99), "expected referenced memory issue to be inspected");
  assert(viewed.includes(77), "expected referenced conversation issue to be inspected and filtered out");
  assert(bundle.memories.map((memory) => memory.issueNumber).join(",") === "1,2,99", "expected wiki-referenced memory to enter the limited recall set");
  assert(JSON.stringify(bundle.memories.find((memory) => memory.issueNumber === 99)?.wikiAnchors) === JSON.stringify(["projects/clawmem"]), "expected wiki anchor slug to be preserved on the memory");
}

async function testWikiContextFailureDoesNotBlockMemoryRecall(): Promise<void> {
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async () => [
      markdownMemory({ issueNumber: 5, detail: "Primary recall should survive wiki failures." }),
    ],
    searchWikiPages: async () => { throw new Error("wiki unavailable"); },
  };
  const store = new MemoryStore(client as never);
  const bundle = await store.searchWithContext("primary recall", 3);

  assert(bundle.memories.length === 1 && bundle.memories[0]?.issueNumber === 5, "expected primary memory recall to survive wiki failure");
  assert(bundle.wikiContexts.length === 0, "expected failed wiki recall to be omitted");
}

async function testBackendSearchPropagatesErrors(): Promise<void> {
  const client = {
    repo: () => "owner/main-memory",
    searchIssues: async () => { throw new Error("search unavailable"); },
  };
  const store = new MemoryStore(client as never);
  let message = "";
  try {
    await store.search("redis rate limiting", 5);
  } catch (error) {
    message = String(error);
  }

  assert(message.includes("search unavailable"), "expected backend failures to propagate instead of falling back locally");
}

await testBackendSearchBuildsSingleCleanedQuery();
await testBackendSearchPreferredForRecall();
await testLiteralRepairCanReserveLexicalSlot();
await testLiteralRepairIgnoresSemanticOnlyRepairHits();
await testQueryPlannerUsesStableCompactVariants();
await testQueryPlannerNormalizesKnownLexicalPitfalls();
await testQueryPlannerCoreVariantCanBeatBroadEntityVariant();
await testQueryPlannerVariantLimitThreeSkipsBroadEntityVariants();
await testQueryPlannerVariantLimitCanBeLowered();
await testBackendSearchReturnsEmptyWithoutLexicalFallback();
await testClosedIssuesAreFilteredFromRecall();
await testWikiContextBoostsReferencedMemoryIssues();
await testWikiContextFailureDoesNotBlockMemoryRecall();
await testBackendSearchPropagatesErrors();

console.log("memory tests passed");
