import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/**
 * Read access to the repo's tracked files for the /ask code agent.
 *
 * Two sources, one interface:
 * - In the container, REPO_SNAPSHOT_DIR points at a snapshot of the tracked
 *   tree baked into the image at build time (apps/web/Dockerfile), pinned to
 *   the deployed commit. Its `.manifest` lists every file.
 * - In `next dev`, we walk up to the live checkout and ask `git ls-files`.
 *
 * The manifest doubles as the access-control list: only paths in it can be
 * read or searched, so gitignored files (.env*, tfvars, logs) are unreachable
 * by construction.
 */

const BINARY_EXTENSIONS = new Set([
  "png", "jpg", "jpeg", "gif", "webp", "ico", "icns",
  "woff", "woff2", "ttf", "otf", "pdf", "zip", "gz",
]);

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_LINE_CHARS = 500;

type Repo = { root: string; manifest: string[] };

let cached: Repo | null = null;

function findCheckoutRoot(): string {
  let dir = process.cwd();
  while (true) {
    if (fs.existsSync(path.join(dir, ".git"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) throw new Error("REPO_SNAPSHOT_DIR is unset and no git checkout was found");
    dir = parent;
  }
}

function loadRepo(): Repo {
  if (cached) return cached;
  const snapshotDir = process.env.REPO_SNAPSHOT_DIR;
  if (snapshotDir) {
    const manifest = fs
      .readFileSync(path.join(snapshotDir, ".manifest"), "utf8")
      .split("\n")
      .filter(Boolean);
    cached = { root: snapshotDir, manifest };
  } else {
    const root = findCheckoutRoot();
    const manifest = execFileSync("git", ["ls-files"], { cwd: root, encoding: "utf8" })
      .split("\n")
      .filter(Boolean);
    cached = { root, manifest };
  }
  return cached;
}

function isBinary(relPath: string): boolean {
  const ext = path.extname(relPath).slice(1).toLowerCase();
  return BINARY_EXTENSIONS.has(ext);
}

function capLine(line: string): string {
  return line.length > MAX_LINE_CHARS ? `${line.slice(0, MAX_LINE_CHARS)}… [line truncated]` : line;
}

export function listTrackedFiles(): string[] {
  return loadRepo().manifest;
}

let cachedTree: string | null = null;

/** The file tree fed to the system prompt: every tracked path with a line count. */
export function fileTreeForPrompt(): string {
  if (cachedTree) return cachedTree;
  const repo = loadRepo();
  cachedTree = repo.manifest
    .map((rel) => {
      if (isBinary(rel)) return `${rel} (binary)`;
      try {
        const content = fs.readFileSync(path.join(repo.root, rel), "utf8");
        return `${rel} (${content.split("\n").length} lines)`;
      } catch {
        return rel;
      }
    })
    .join("\n");
  return cachedTree;
}

export type ReadResult =
  | { error: string }
  | { path: string; totalLines: number; startLine: number; endLine: number; content: string };

export function readTrackedFile(relPath: string, offset = 1, limit = 400): ReadResult {
  const repo = loadRepo();
  if (!repo.manifest.includes(relPath)) {
    return { error: `Not a tracked file: ${relPath}. Use exact paths from the file tree or search results.` };
  }
  if (isBinary(relPath)) return { error: `${relPath} is a binary file.` };

  const abs = path.join(repo.root, relPath);
  if (fs.statSync(abs).size > MAX_FILE_BYTES) return { error: `${relPath} is too large to read.` };

  const lines = fs.readFileSync(abs, "utf8").split("\n");
  const start = Math.max(1, offset);
  const end = Math.min(lines.length, start + Math.min(limit, 400) - 1);
  if (start > lines.length) {
    return { error: `${relPath} has only ${lines.length} lines (requested offset ${start}).` };
  }
  const content = lines
    .slice(start - 1, end)
    .map((line, i) => `${start + i}|${capLine(line)}`)
    .join("\n");
  return { path: relPath, totalLines: lines.length, startLine: start, endLine: end, content };
}

export type SearchResult =
  | { error: string }
  | { matches: string[]; matchCount: number; truncated: boolean };

const MAX_MATCHES = 60;

export function searchTrackedFiles(pattern: string, pathFilter?: string): SearchResult {
  let regex: RegExp;
  try {
    regex = new RegExp(pattern, "i");
  } catch (e) {
    return { error: `Invalid regex: ${e instanceof Error ? e.message : String(e)}` };
  }

  const repo = loadRepo();
  const files = pathFilter
    ? repo.manifest.filter((rel) => rel.includes(pathFilter))
    : repo.manifest;

  const matches: string[] = [];
  let matchCount = 0;
  for (const rel of files) {
    if (isBinary(rel)) continue;
    const abs = path.join(repo.root, rel);
    let content: string;
    try {
      if (fs.statSync(abs).size > MAX_FILE_BYTES) continue;
      content = fs.readFileSync(abs, "utf8");
    } catch {
      continue;
    }
    if (!regex.test(content)) continue;
    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (!regex.test(lines[i])) continue;
      matchCount++;
      if (matches.length < MAX_MATCHES) {
        matches.push(`${rel}:${i + 1}: ${capLine(lines[i].trim())}`);
      }
    }
  }
  return { matches, matchCount, truncated: matchCount > MAX_MATCHES };
}
