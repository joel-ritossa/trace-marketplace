import { ToolLoopAgent, tool, stepCountIs, type InferAgentUIMessage } from "ai";
import { openai } from "@ai-sdk/openai";
import { z } from "zod";
import { fileTreeForPrompt, readTrackedFile, searchTrackedFiles } from "./repo";

/**
 * The /ask code agent: read-only Q&A over this repo's tracked files, so the
 * team can interrogate the codebase from inside the product. Search/read
 * results are hard-capped in repo.ts, which keeps the context bounded without
 * a separate compaction pass.
 */

const SYSTEM_PROMPT = `You are the code guide for Trace Marketplace — a platform for contributing, discovering, downloading, and evaluating AI-agent trace data. You answer questions about this repository for the team reviewing the product.

You have read-only access to the repo's tracked files via two tools:
- search: regex search across all tracked files (optionally filtered by path substring)
- read_file: read a tracked file, optionally a specific line range

How to work:
1. Use the file tree below to orient yourself; search to locate relevant code; read files to confirm before answering.
2. Ground every claim in code you actually read. Cite paths (and line numbers where useful) like \`services/api/app/analysis/judge.py:42\`.
3. Key places: docs/spec/ is the normative spec, report/ is the evaluator-facing write-up, docs/explainers/ covers system behaviors, services/api is the FastAPI backend + worker, apps/web is the Next.js frontend.
4. Minimize round-trips: read_file accepts up to 8 files per call — read every file you plan to inspect in one batch. Independent tool calls can also be issued in parallel within a step.
5. Be concise and direct. If the code contradicts the docs, say so and trust the code.
6. If you cannot find an answer in the repo, say that plainly — never invent code or behavior.

Repository file tree (tracked files):
`;

function buildTools() {
  return {
    search: tool({
      description:
        "Regex search across all tracked files in the repository. Returns matching lines as path:line: text.",
      inputSchema: z.object({
        pattern: z.string().describe("Regular expression to search for (case-insensitive)"),
        path_filter: z
          .string()
          .optional()
          .describe("Only search files whose path contains this substring, e.g. 'services/api'"),
      }),
      execute: async ({ pattern, path_filter }) => searchTrackedFiles(pattern, path_filter),
    }),
    read_file: tool({
      description:
        "Read one or more tracked files by exact repo-relative path. Returns numbered lines. Batch related files into a single call. Use offset/limit for large files (max 400 lines per file).",
      inputSchema: z.object({
        files: z
          .array(
            z.object({
              path: z.string().describe("Repo-relative path, e.g. 'services/api/app/main.py'"),
              offset: z.number().int().min(1).optional().describe("1-based line to start from"),
              limit: z.number().int().min(1).max(400).optional().describe("Number of lines to read"),
            }),
          )
          .min(1)
          .max(8),
      }),
      execute: async ({ files }) =>
        files.map(({ path, offset, limit }) => readTrackedFile(path, offset, limit)),
    }),
  };
}

export function createAskAgent() {
  return new ToolLoopAgent({
    model: openai(process.env.ASK_AGENT_MODEL ?? "gpt-5-mini"),
    instructions: SYSTEM_PROMPT + fileTreeForPrompt(),
    tools: buildTools(),
    stopWhen: stepCountIs(16),
    // Tool calls within a step run via Promise.all in the SDK; this asks the
    // model to actually emit them together.
    providerOptions: { openai: { parallelToolCalls: true } },
  });
}

export type AskAgentUIMessage = InferAgentUIMessage<ReturnType<typeof createAskAgent>>;
