// Memory recall search helpers. Durable memory writes are skill-driven through GitHub-native operations.
import { extractLabelNames, labelVal } from "./config.js";
import type { GitHubIssueClient, WikiPageResponse, WikiSearchResultResponse } from "./github-client.js";
import type { ParsedMemoryIssue } from "./types.js";
import { parseFlatYaml } from "./yaml.js";
import { sanitizeRecallQueryInput } from "./recall-sanitize.js";

const MAX_BACKEND_QUERY_CHARS = 1500;
const MAX_WIKI_CONTEXT_PAGES = 3;
const MAX_WIKI_REF_MEMORY_FETCHES = 6;
const DEFAULT_LITERAL_REPAIR_SLOTS = 1;
const DEFAULT_PLANNER_VARIANT_LIMIT = 6;
const MIN_PLANNER_VARIANT_LIMIT = 1;
const MAX_PLANNER_VARIANT_LIMIT = 6;

const RECALL_INJECTED_BLOCKS = [
  /<clawmem-context>[\s\S]*?<\/clawmem-context>/gi,
  /<relevant-memories>[\s\S]*?<\/relevant-memories>/gi,
  /<memories>[\s\S]*?<\/memories>/gi,
];

const URL_RE = /https?:\/\/\S+/gi;
const LITERAL_QUESTION_RE = /\b(?:when|how\s+long|how\s+many|how\s+much|what\s+(?:date|day|month|year|time)|which\s+(?:day|month|year|date|one|item)|who\s+(?:is|was|were)|what\s+(?:is|was|were)\s+.+\s+(?:name|called|working on))\b/i;
const QUERY_STOPWORDS = new Set([
  "a", "about", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can",
  "could", "did", "do", "does", "for", "from", "had", "has", "have", "he", "her",
  "hers", "him", "his", "how", "if", "in", "into", "is", "it", "its", "many",
  "much", "of", "on", "or", "over", "she", "should", "that", "the", "their",
  "them", "then", "there", "these", "they", "this", "those", "to", "was", "were",
  "what", "when", "where", "which", "who", "whom", "why", "will", "with", "would",
  "your",
]);
const GENERIC_QUERY_TERMS = new Set([
  "ago", "alive", "called", "considered", "current", "date", "day", "exact",
  "first", "going", "group", "last", "likely", "long", "longer", "month",
  "motivational", "name", "names", "next", "old", "planned", "planning", "plans",
  "previous", "range", "recent", "recently", "still", "stunning", "time", "times",
  "today", "tomorrow", "want", "year", "years", "yesterday",
]);
const UNSTABLE_QUERY_ACTION_TERMS = new Set([
  "add", "added", "adding", "ask", "asked", "asking", "began", "begin",
  "beginning", "bring", "brought", "bought", "buy", "buying", "came", "capture",
  "captured", "capturing", "consider", "considered", "considering", "create",
  "created", "creating", "dating", "decide", "decided", "deciding", "did", "does",
  "doing", "done", "find", "finding", "found", "gave", "get", "gets", "getting",
  "give", "given", "giving", "go", "goes", "going", "gone", "got", "had", "have",
  "having", "help", "helped", "helping", "keep", "kept", "know", "learn",
  "learned", "learning", "like", "liked", "made", "make", "making", "meet", "met",
  "need", "needed", "plan", "planned", "planning", "promote", "promoted",
  "promoting", "receive", "received", "receiving", "recommend", "recommended",
  "recommending", "remember", "remembered", "run", "running", "said", "saw", "see",
  "seeing", "seen", "sign", "signed", "signing", "show", "showed", "showing",
  "start", "started", "starting", "take", "taken", "takes", "taking", "think",
  "thinking", "told", "took", "try", "trying", "use", "used", "using", "want",
  "wanted", "watch", "watched", "went", "work", "worked", "working", "write",
  "writes", "writing", "wrote",
]);
const ORDINAL_QUERY_TERMS = new Set([
  "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
  "ninth", "tenth", "last", "latest", "next", "previous",
]);
const DATE_ANCHOR_TERMS = new Set([
  "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
  "january", "february", "march", "april", "may", "june", "july", "august",
  "september", "october", "november", "december", "spring", "summer", "fall",
  "autumn", "winter", "morning", "afternoon", "evening", "night", "week",
  "weekend", "month", "year", "birthday", "anniversary",
]);
const QUERY_TOKEN_ALIASES = new Map([
  ["clothes", "clothing"],
  ["dancing", "dance"],
  ["photography", "photo"],
  ["photoshoot", "photo"],
]);
const WEAK_CORE_QUERY_TERMS = new Set([
  "activity", "book", "day", "event", "favorite", "friend", "item", "memory",
  "month", "mountain", "name", "person", "photo", "picture", "thing", "time",
  "week", "year",
]);

type MemoryStoreOptions = {
  recallStrategy?: "single" | "literal-repair" | "query-planner";
  literalRepairSlots?: number;
  plannerVariantLimit?: number;
};

export type WikiContextPage = {
  slug: string;
  title: string;
  body: string;
  excerpt?: string;
  snippet?: string;
  score?: number;
  issueRefs: string[];
};
export type RecallBundle = {
  memories: ParsedMemoryIssue[];
  wikiContexts: WikiContextPage[];
};

type SearchIssue = {
  number: number;
  title?: string;
  body?: string;
  state?: string;
  labels?: Array<{ name?: string } | string>;
  debug?: { search_path?: string; lexical_rank?: number };
};
type RecallQueryVariant = { name: string; text: string; priority: number };
type PlannedSearchRun = { variant: RecallQueryVariant; batch: SearchIssue[]; error?: unknown };
type PlannedCandidate = {
  memory: ParsedMemoryIssue;
  issueNumber: number;
  bestRank: number;
  bestPriority: number;
};
type WikiAnchoredMemory = {
  memory: ParsedMemoryIssue;
  anchorRank: number;
  wikiAnchors: string[];
};
type RecallCandidate = {
  memory: ParsedMemoryIssue;
  issueNumber: number;
  primaryRank?: number;
  anchorRank?: number;
  wikiAnchors: string[];
};

export class MemoryStore {
  constructor(private readonly client: GitHubIssueClient, private readonly options: MemoryStoreOptions = {}) {}

  async search(query: string, limit: number): Promise<ParsedMemoryIssue[]> {
    const q = normalizeSearch(query);
    if (!q) return [];
    return this.searchViaBackend(query, limit);
  }

  async searchWithContext(query: string, limit: number): Promise<RecallBundle> {
    const q = normalizeSearch(query);
    if (!q) return { memories: [], wikiContexts: [] };

    const repo = this.client.repo();
    if (!repo) throw new Error("ClawMem memory recall requires a configured repo.");
    const primaryLimit = Math.min(20, Math.max(limit, limit + MAX_WIKI_REF_MEMORY_FETCHES));
    const primary = await this.searchViaBackend(query, primaryLimit);
    const wikiContexts = await this.searchWikiContexts(query, repo);
    if (wikiContexts.length === 0) return { memories: primary.slice(0, limit), wikiContexts };

    const anchored = await this.loadWikiReferencedMemories(wikiContexts, repo);
    return {
      memories: rankRecallCandidates(primary, anchored, limit),
      wikiContexts,
    };
  }

  private async searchViaBackend(query: string, limit: number): Promise<ParsedMemoryIssue[]> {
    const repo = this.client.repo();
    if (!repo) throw new Error("ClawMem memory recall requires a configured repo.");
    if (this.options.recallStrategy === "query-planner") return this.searchWithQueryPlanner(query, repo, limit);
    const qualified = buildMemorySearchQuery(query, repo);
    const batch = await this.client.searchIssues(qualified, { perPage: Math.min(100, Math.max(limit * 3, 20)) });
    const full = batch
      .map((issue) => this.parseIssue(issue))
      .filter((memory): memory is ParsedMemoryIssue => memory !== null && memory.status === "active")
      .slice(0, limit);
    if (!this.shouldUseLiteralRepair(query, limit)) return full;
    return this.searchWithLiteralRepair(query, repo, full, limit);
  }

  private async searchWithQueryPlanner(query: string, repo: string, limit: number): Promise<ParsedMemoryIssue[]> {
    const variantLimit = normalizePlannerVariantLimit(this.options.plannerVariantLimit);
    const variants = buildQueryPlannerVariants(query, variantLimit);
    if (variants.length === 0) return [];
    const perPage = Math.min(100, Math.max(limit * 3, 20));
    const byIssue = new Map<number, PlannedCandidate>();

    const runs = await Promise.all(variants.map(async (variant): Promise<PlannedSearchRun> => {
      try {
        const searchQuery = buildMemorySearchQuery(variant.text, repo);
        const batch = await this.client.searchIssues(searchQuery, {
          perPage,
          debug: variant.name !== "full",
        });
        return { variant, batch: batch as SearchIssue[] };
      } catch (error) {
        return { variant, batch: [], error };
      }
    }));
    if (runs.length > 0 && runs.every((run) => run.error)) throw runs[0]?.error;

    for (const { variant, batch } of runs) {
      for (const [index, issue] of (batch as SearchIssue[]).entries()) {
        if (variant.name !== "full" && !hasLexicalSignal(issue)) continue;
        const memory = this.parseIssue(issue);
        if (!memory || memory.status !== "active") continue;
        const rank = index + 1;
        const existing = byIssue.get(memory.issueNumber);
        if (!existing) {
          byIssue.set(memory.issueNumber, {
            memory,
            issueNumber: memory.issueNumber,
            bestRank: rank,
            bestPriority: variant.priority,
          });
          continue;
        }
        if (rank < existing.bestRank || (rank === existing.bestRank && variant.priority < existing.bestPriority)) {
          existing.bestRank = rank;
          existing.bestPriority = variant.priority;
        }
      }
    }

    return [...byIssue.values()]
      .sort((a, b) => (
        a.bestRank - b.bestRank
        || a.bestPriority - b.bestPriority
        || b.issueNumber - a.issueNumber
      ))
      .slice(0, limit)
      .map((candidate) => candidate.memory);
  }

  private async searchWithLiteralRepair(query: string, repo: string, full: ParsedMemoryIssue[], limit: number): Promise<ParsedMemoryIssue[]> {
    const reserveLimit = Math.min(Math.max(this.options.literalRepairSlots ?? DEFAULT_LITERAL_REPAIR_SLOTS, 0), Math.max(limit - 1, 0));
    if (reserveLimit <= 0) return full.slice(0, limit);

    const selected: ParsedMemoryIssue[] = [];
    const seen = new Set<number>();
    const add = (memory: ParsedMemoryIssue | null): boolean => {
      if (!memory || memory.status !== "active" || seen.has(memory.issueNumber)) return false;
      selected.push(memory);
      seen.add(memory.issueNumber);
      return true;
    };

    for (const memory of full.slice(0, Math.max(0, limit - reserveLimit))) add(memory);

    let reserved = 0;
    try {
      for (const repairText of buildLiteralRepairSearchTexts(query)) {
        if (reserved >= reserveLimit) break;
        const repairQuery = buildMemorySearchQuery(repairText, repo);
        const batch = await this.client.searchIssues(repairQuery, {
          perPage: Math.min(100, Math.max(limit * 3, 20)),
          debug: true,
        });
        for (const issue of batch as SearchIssue[]) {
          if (reserved >= reserveLimit) break;
          if (!hasLexicalSignal(issue)) continue;
          if (add(this.parseIssue(issue))) reserved += 1;
        }
      }
    } catch {
      return full.slice(0, limit);
    }

    for (const memory of full) {
      if (selected.length >= limit) break;
      add(memory);
    }
    return selected.slice(0, limit);
  }

  private shouldUseLiteralRepair(query: string, limit: number): boolean {
    return this.options.recallStrategy === "literal-repair"
      && limit > 1
      && LITERAL_QUESTION_RE.test(query);
  }

  private async searchWikiContexts(query: string, _repo: string): Promise<WikiContextPage[]> {
    try {
      const searchText = buildRecallSearchText(query);
      if (!searchText) return [];
      const results = await this.client.searchWikiPages(searchText, { limit: MAX_WIKI_CONTEXT_PAGES });
      const pages = await Promise.all(results.slice(0, MAX_WIKI_CONTEXT_PAGES).map(async (result): Promise<WikiContextPage | null> => {
        const slug = readWikiSlug(result);
        if (!slug) return null;
        const page = await this.client.getWikiPage(slug);
        return wikiContextFromPage(page, result, searchText);
      }));
      return pages.filter((page): page is WikiContextPage => page !== null);
    } catch {
      return [];
    }
  }

  private async loadWikiReferencedMemories(contexts: WikiContextPage[], repo: string): Promise<WikiAnchoredMemory[]> {
    const refs: Array<{ issueNumber: number; anchorRank: number; slug: string }> = [];
    const seen = new Set<number>();
    let rank = 0;
    for (const context of contexts) {
      for (const issueNumber of localIssueNumbers(context.issueRefs, repo)) {
        if (seen.has(issueNumber)) continue;
        seen.add(issueNumber);
        rank += 1;
        refs.push({ issueNumber, anchorRank: rank, slug: context.slug });
        if (refs.length >= MAX_WIKI_REF_MEMORY_FETCHES) break;
      }
      if (refs.length >= MAX_WIKI_REF_MEMORY_FETCHES) break;
    }

    const anchored = await Promise.all(refs.map(async (ref): Promise<WikiAnchoredMemory | null> => {
      try {
        const memory = this.parseIssue(await this.client.getIssue(ref.issueNumber));
        if (!memory || memory.status !== "active") return null;
        return {
          memory,
          anchorRank: ref.anchorRank,
          wikiAnchors: [ref.slug],
        };
      } catch {
        // Wiki references are booster signals. A missing or non-memory issue
        // should not interrupt direct memory recall.
        return null;
      }
    }));
    return anchored.filter((memory): memory is WikiAnchoredMemory => memory !== null);
  }

  private parseIssue(issue: SearchIssue): ParsedMemoryIssue | null {
    const labels = extractLabelNames(issue.labels);
    if (!labels.includes("type:memory")) return null;
    const kind = labelVal(labels, "kind:");
    const topics = labels.filter((l) => l.startsWith("topic:")).map((l) => l.slice(6).trim()).filter(Boolean);
    const rawBody = (issue.body ?? "").trim();
    const parsed = parseStoredMemoryBody(rawBody);
    const detail = parsed.detail?.trim() || rawBody;
    const sourceRefs = extractSourceRefs(rawBody);
    const status = issue.state === "closed" ? "stale" : "active";
    if (!detail) return null;
    return {
      issueNumber: issue.number,
      title: issue.title?.trim() || "",
      memoryId: parsed.meta.memory_id?.trim() || String(issue.number),
      memoryHash: parsed.meta.memory_hash?.trim() || undefined,
      date: parsed.meta.valid_from?.trim() || parsed.meta.date?.trim() || "1970-01-01",
      detail,
      ...(kind ? { kind } : {}),
      ...(topics.length > 0 ? { topics } : {}),
      ...(sourceRefs.length > 0 ? { sourceRefs } : {}),
      status,
    };
  }
}

function parseStoredMemoryBody(rawBody: string): { detail: string; meta: Record<string, string> } {
  const trimmed = rawBody.trim();
  if (!trimmed) return { detail: "", meta: {} };

  const hiddenMeta = /(?:^|\n)<!--\s*clawmem(?:-meta)?\s*\n([\s\S]*?)\n-->\s*$/.exec(trimmed);
  const visible = hiddenMeta ? trimmed.slice(0, hiddenMeta.index).trim() : trimmed;
  const meta = hiddenMeta ? parseFlatYaml(hiddenMeta[1] ?? "") : {};
  const detail = extractMarkdownMemoryDetail(visible) || meta.detail?.trim() || visible;
  return { detail, meta };
}

function extractMarkdownMemoryDetail(markdown: string): string {
  const match = /^## Memory\s*\n+([\s\S]*?)(?=\n## |\s*$)/m.exec(markdown.trim());
  return match?.[1]?.trim() ?? "";
}

function extractSourceRefs(markdown: string): string[] {
  const match = /^## Relations\s*\n+([\s\S]*?)(?=\n## |\s*$)/m.exec(markdown.trim());
  if (!match?.[1]) return [];
  const refs = new Set<string>();
  for (const line of match[1].split(/\r?\n/)) {
    if (!/\bsource\b/i.test(line)) continue;
    for (const ref of line.match(/(?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)?#\d+/g) ?? []) refs.add(ref);
  }
  return [...refs];
}

function rankRecallCandidates(primary: ParsedMemoryIssue[], anchored: WikiAnchoredMemory[], limit: number): ParsedMemoryIssue[] {
  const byIssue = new Map<number, RecallCandidate>();
  for (const [index, memory] of primary.entries()) {
    byIssue.set(memory.issueNumber, {
      memory,
      issueNumber: memory.issueNumber,
      primaryRank: index + 1,
      wikiAnchors: memory.wikiAnchors ?? [],
    });
  }
  for (const item of anchored) {
    const existing = byIssue.get(item.memory.issueNumber);
    if (!existing) {
      byIssue.set(item.memory.issueNumber, {
        memory: item.memory,
        issueNumber: item.memory.issueNumber,
        anchorRank: item.anchorRank,
        wikiAnchors: item.wikiAnchors,
      });
      continue;
    }
    existing.anchorRank = existing.anchorRank === undefined ? item.anchorRank : Math.min(existing.anchorRank, item.anchorRank);
    existing.wikiAnchors = uniqueTokens([...existing.wikiAnchors, ...item.wikiAnchors]);
  }

  return [...byIssue.values()]
    .sort((a, b) => recallCandidateScore(b) - recallCandidateScore(a) || a.issueNumber - b.issueNumber)
    .slice(0, limit)
    .map((candidate) => ({
      ...candidate.memory,
      ...(candidate.wikiAnchors.length > 0 ? { wikiAnchors: candidate.wikiAnchors } : {}),
    }));
}

function recallCandidateScore(candidate: RecallCandidate): number {
  const primary = candidate.primaryRank !== undefined ? 1000 - candidate.primaryRank * 10 : 0;
  const anchor = candidate.anchorRank !== undefined ? 985 - candidate.anchorRank * 5 : 0;
  const bonus = candidate.primaryRank !== undefined && candidate.anchorRank !== undefined ? 20 : 0;
  return Math.max(primary, anchor) + bonus;
}

function readWikiSlug(result: WikiSearchResultResponse): string {
  return typeof result.slug === "string" ? result.slug.trim() : "";
}

function wikiContextFromPage(page: WikiPageResponse, result: WikiSearchResultResponse, query: string): WikiContextPage | null {
  const slug = typeof page.slug === "string" && page.slug.trim() ? page.slug.trim() : readWikiSlug(result);
  if (!slug) return null;
  const body = typeof page.body === "string" ? page.body.trim() : "";
  const snippet = typeof result.snippet === "string" && result.snippet.trim() ? result.snippet.trim() : undefined;
  if (!body && !snippet) return null;
  const title = typeof page.title === "string" && page.title.trim()
    ? page.title.trim()
    : typeof result.title === "string" && result.title.trim()
      ? result.title.trim()
      : slug;
  const score = typeof result.score === "number" && Number.isFinite(result.score) ? result.score : undefined;
  const fullText = body || snippet || "";
  const issueRefs = extractIssueRefs(fullText, query);
  return {
    slug,
    title,
    body: fullText,
    excerpt: wikiContextExcerpt(fullText, query, issueRefs),
    ...(snippet ? { snippet } : {}),
    ...(score !== undefined ? { score } : {}),
    issueRefs,
  };
}

function extractIssueRefs(markdown: string, query = ""): string[] {
  const masked = maskIssueReferenceIgnoredMarkdown(markdown);
  const scored = new Map<string, { score: number; order: number }>();
  const queryTokens = wikiRefQueryTokens(query);
  let order = 0;
  for (const line of masked.split(/\r?\n/)) {
    const refs = line.match(/(?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)?#\d+\b/g) ?? [];
    if (refs.length === 0) continue;
    const score = wikiRefLineScore(line, queryTokens);
    for (const ref of refs) {
      const existing = scored.get(ref);
      if (!existing) {
        scored.set(ref, { score, order });
        order += 1;
        continue;
      }
      if (score > existing.score) existing.score = score;
    }
  }
  return [...scored.entries()]
    .sort((a, b) => b[1].score - a[1].score || a[1].order - b[1].order)
    .map(([ref]) => ref);
}

function wikiRefQueryTokens(query: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of normalizedQueryTokens(query)) {
    const key = stabilizeQueryToken(item.normalized, false).toLowerCase();
    if (seen.has(key) || shouldDropCompactToken(key)) continue;
    if (key.length < 3 && !/^\d+$/.test(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out.slice(0, 8);
}

function wikiRefLineScore(line: string, queryTokens: string[]): number {
  if (queryTokens.length === 0) return 0;
  const lower = line.toLowerCase();
  let score = 0;
  for (const token of queryTokens) {
    if (lower.includes(token)) score += 1;
  }
  return score;
}

function wikiContextExcerpt(markdown: string, query: string, refs: string[], maxChars = 1600): string {
  const text = markdown.replace(/\r/g, "\n").trim();
  if (!text) return "";
  const queryTokens = wikiRefQueryTokens(query);
  const refSet = new Set(refs.slice(0, 10));
  const scored: Array<{ score: number; index: number; line: string }> = [];
  for (const [index, line] of text.split(/\n/).entries()) {
    const stripped = line.replace(/\s+/g, " ").trim();
    if (!stripped) continue;
    const lineRefs = stripped.match(/(?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)?#\d+\b/g) ?? [];
    const refScore = lineRefs.some((ref) => refSet.has(ref)) ? 8 : 0;
    const tokenScore = wikiRefLineScore(stripped, queryTokens);
    const headingScore = stripped.startsWith("#") ? 1 : 0;
    const score = refScore + tokenScore + headingScore;
    if (score <= 0) continue;
    scored.push({ score, index, line: stripped });
  }
  if (scored.length === 0) return compactWikiText(text, maxChars);
  scored.sort((a, b) => b.score - a.score || a.index - b.index);
  const selected = scored.slice(0, 8).sort((a, b) => a.index - b.index).map((item) => item.line).join("\n");
  return compactWikiText(selected, maxChars);
}

function compactWikiText(text: string, maxChars: number): string {
  const compact = text.trim();
  if (compact.length <= maxChars) return compact;
  return `${compact.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

function localIssueNumbers(refs: string[], repo: string): number[] {
  const out: number[] = [];
  const seen = new Set<number>();
  const repoKey = repo.toLowerCase();
  for (const ref of refs) {
    const local = /^#(\d+)$/.exec(ref);
    const cross = /^([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)#(\d+)$/.exec(ref);
    const rawNumber = local?.[1] ?? (cross?.[1]?.toLowerCase() === repoKey ? cross?.[2] : undefined);
    const issueNumber = rawNumber ? Number(rawNumber) : 0;
    if (!Number.isInteger(issueNumber) || issueNumber <= 0 || seen.has(issueNumber)) continue;
    seen.add(issueNumber);
    out.push(issueNumber);
  }
  return out;
}

function maskIssueReferenceIgnoredMarkdown(body: string): string {
  return body
    .replace(/<!--[\s\S]*?-->/g, (match) => " ".repeat(match.length))
    .replace(/```[\s\S]*?```/g, (match) => " ".repeat(match.length))
    .replace(/`[^`\n]*`/g, (match) => " ".repeat(match.length));
}

function normalizeSearch(v: string): string {
  return v.normalize("NFKC").toLowerCase().replace(/\s+/g, " ").trim();
}

function buildMemorySearchQuery(query: string, repo: string): string {
  const parts = [buildRecallSearchText(query), `repo:${repo}`, "is:issue", "state:open", 'label:"type:memory"'].filter(Boolean);
  return parts.join(" ");
}

function buildRecallSearchText(rawQuery: string): string {
  const cleaned = sanitizeRecallQueryInput(stripRecallArtifacts(rawQuery));
  return truncateRecallQuery(cleaned, MAX_BACKEND_QUERY_CHARS);
}

function buildLiteralRepairSearchTexts(rawQuery: string): string[] {
  const variants = buildQueryPlannerVariants(rawQuery, 5)
    .filter((variant) => variant.name !== "full")
    .map((variant) => variant.text);
  const seen = new Set<string>();
  return variants.filter((value) => {
    const key = value.toLowerCase();
    if (!value || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function buildQueryPlannerVariants(rawQuery: string, variantLimit: number): RecallQueryVariant[] {
  const cleaned = buildRecallSearchText(rawQuery);
  const variants: RecallQueryVariant[] = [];
  const seen = new Set<string>();

  const add = (name: string, text: string, priority: number): void => {
    const normalized = text.replace(/\s+/g, " ").trim();
    const key = normalized.toLowerCase();
    if (!normalized || seen.has(key)) return;
    seen.add(key);
    variants.push({ name, text: normalized, priority });
  };

  add("full", cleaned, 0);
  add("compact", compactRecallSearchText(cleaned, 4), 1);
  add("core", coreRecallSearchText(cleaned, 4), 2);
  add("surface", surfaceRecallSearchText(cleaned, 4), 3);
  if (LITERAL_QUESTION_RE.test(cleaned)) add("literal", literalRecallSearchText(cleaned, 6), 4);
  add("entity", entityRecallSearchText(cleaned, 5), 5);
  return variantLimit > 0 ? variants.slice(0, variantLimit) : variants;
}

function normalizePlannerVariantLimit(value: number | undefined): number {
  const raw = typeof value === "number" && Number.isFinite(value) ? Math.floor(value) : DEFAULT_PLANNER_VARIANT_LIMIT;
  return Math.min(MAX_PLANNER_VARIANT_LIMIT, Math.max(MIN_PLANNER_VARIANT_LIMIT, raw));
}

function normalizedQueryTokens(text: string): Array<{ token: string; normalized: string }> {
  const rawTokens = text.match(/[A-Za-z0-9][A-Za-z0-9'_-]*/g) ?? [];
  return rawTokens.map((token) => ({
    token,
    normalized: token.replace(/^['_\-.]+|['_\-.]+$/g, "").replace(/'s$/i, "").replace(/^['_\-.]+|['_\-.]+$/g, ""),
  })).filter((item) => item.normalized.length > 0);
}

function compactRecallSearchText(text: string, limit: number): string {
  const scored: Array<{ score: number; index: number; token: string }> = [];
  const seen = new Set<string>();
  for (const [index, item] of normalizedQueryTokens(text).entries()) {
    const normalized = stabilizeQueryToken(item.normalized, true);
    const key = normalized.toLowerCase();
    if (seen.has(key) || shouldDropCompactToken(key)) continue;
    if (key.length < 3 && !/^\d+$/.test(key)) continue;
    seen.add(key);
    let score = 0;
    if (/^\d{2,4}$/.test(key)) score += 6;
    if (/^[A-Z]/.test(item.token)) score += 5;
    if (ORDINAL_QUERY_TERMS.has(key)) score += 5;
    if (key.length >= 6) score += 2;
    scored.push({ score, index, token: normalized });
  }
  return scored
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, limit)
    .sort((a, b) => a.index - b.index)
    .map((item) => item.token)
    .join(" ");
}

function surfaceRecallSearchText(text: string, limit: number): string {
  return filteredQueryTokens(text, limit, { singularize: false }).join(" ");
}

function coreRecallSearchText(text: string, limit: number): string {
  const surface = filteredQueryTokens(text, limit, { singularize: false });
  const entities = entityRecallTokens(text, 2);
  const entityKeys = new Set(entities.map((token) => token.toLowerCase()));
  const nonEntities = surface.filter((token) => !entityKeys.has(token.toLowerCase()));
  const preferred = nonEntities.filter((token) => !WEAK_CORE_QUERY_TERMS.has(token.toLowerCase()));
  const tail = preferred.length > 0 ? preferred.slice(-2) : nonEntities.slice(-1);
  return uniqueTokens([...entities, ...tail]).slice(0, limit).join(" ");
}

function entityRecallSearchText(text: string, limit: number): string {
  return entityRecallTokens(text, limit).join(" ");
}

function literalRecallSearchText(text: string, limit: number): string {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of normalizedQueryTokens(text)) {
    const normalized = stabilizeQueryToken(item.normalized, true);
    const key = normalized.toLowerCase();
    if (QUERY_STOPWORDS.has(key)) continue;
    let keep = (
      !GENERIC_QUERY_TERMS.has(key)
      || DATE_ANCHOR_TERMS.has(key)
      || ["name", "called", "first", "last", "current"].includes(key)
      || /^\d{1,4}$/.test(key)
      || /^[A-Z]/.test(item.token)
    );
    if (UNSTABLE_QUERY_ACTION_TERMS.has(key) && !/^[A-Z]/.test(item.token)) keep = false;
    if (!keep || seen.has(key)) continue;
    if (key.length < 3 && !/^\d+$/.test(key)) continue;
    seen.add(key);
    out.push(normalized);
    if (out.length >= limit) break;
  }
  return out.join(" ");
}

function filteredQueryTokens(text: string, limit: number, options: { singularize: boolean }): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of normalizedQueryTokens(text)) {
    const normalized = stabilizeQueryToken(item.normalized, options.singularize);
    const key = normalized.toLowerCase();
    if (seen.has(key) || shouldDropCompactToken(key)) continue;
    if (key.length < 3 && !/^\d+$/.test(key)) continue;
    seen.add(key);
    out.push(normalized);
    if (out.length >= limit) break;
  }
  return out;
}

function entityRecallTokens(text: string, limit: number): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const item of normalizedQueryTokens(text)) {
    const normalized = stabilizeQueryToken(item.normalized, false);
    const key = normalized.toLowerCase();
    if (seen.has(key) || QUERY_STOPWORDS.has(key)) continue;
    if (/^[A-Z]/.test(item.token) || /^\d{2,4}$/.test(key)) {
      seen.add(key);
      out.push(normalized);
      if (out.length >= limit) break;
    }
  }
  return out;
}

function shouldDropCompactToken(key: string): boolean {
  return QUERY_STOPWORDS.has(key) || GENERIC_QUERY_TERMS.has(key) || UNSTABLE_QUERY_ACTION_TERMS.has(key);
}

function stabilizeQueryToken(token: string, singularize: boolean): string {
  if (/^[A-Z]/.test(token)) return token;
  const key = token.toLowerCase();
  const alias = QUERY_TOKEN_ALIASES.get(key);
  if (alias) return alias;
  if (!singularize) return token;
  if (key.length > 4 && key.endsWith("ies")) return `${token.slice(0, -3)}y`;
  if (key.length > 4 && /(sses|ches|shes|xes|zes)$/.test(key)) return token.slice(0, -2);
  if (key.length > 4 && key.endsWith("s") && !/(ss|us)$/.test(key)) return token.slice(0, -1);
  return token;
}

function uniqueTokens(tokens: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of tokens) {
    const key = token.toLowerCase();
    if (!token || seen.has(key)) continue;
    seen.add(key);
    out.push(token);
  }
  return out;
}

function hasLexicalSignal(issue: SearchIssue): boolean {
  const debug = issue.debug;
  if (!debug) return false;
  const path = debug.search_path ?? "";
  return (debug.lexical_rank ?? 0) > 0 || path === "hybrid" || path === "lexical_only";
}

function stripRecallArtifacts(rawQuery: string): string {
  let text = rawQuery.replace(/\r/g, "\n").replace(URL_RE, " ");
  for (const block of RECALL_INJECTED_BLOCKS) text = text.replace(block, " ");
  return text;
}

function truncateRecallQuery(text: string, maxLen: number): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (!compact) return "";
  return compact.length <= maxLen ? compact : compact.slice(0, maxLen).trimEnd();
}
