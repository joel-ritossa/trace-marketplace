// Display-side naming for traces and spans. Session imports name traces
// "<agent>: <first ask>" and turn spans "turn N: <ask>"; asks can start with
// client wrapper tags (`<artifact-view-context …>{json}`), which never make a
// readable title. The importer is being fixed; old rows keep the raw names.

export type Agent = "claude" | "codex" | "cursor";

const AGENT_PREFIX = /^(claude|codex|cursor):\s*/i;

/** Drops angle-bracket wrapper blocks and stray/truncated tags, plus a JSON
 *  payload a truncated wrapper leaves behind; collapses whitespace. */
export function stripWrappers(text: string): string {
  return text
    .replace(/<([a-z][\w-]*)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
    .replace(/<\/?[a-z][\w-]*\b[^>]*>?/gi, " ")
    .replace(/\{"[\s\S]*$/, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function agentOf(name: string, sourceFormat?: string | null): Agent | null {
  const prefix = AGENT_PREFIX.exec(name)?.[1]?.toLowerCase();
  if (prefix) return prefix as Agent;
  if (sourceFormat?.startsWith("anthropic")) return "claude";
  if (sourceFormat?.startsWith("codex")) return "codex";
  return null;
}

/** The trace name without the agent prefix or wrapper tags — the session's
 *  first ask for imports. Falls back to the raw name. */
export function cleanName(name: string): string {
  const cleaned = stripWrappers(name.replace(AGENT_PREFIX, ""));
  return cleaned || name;
}

/** What a human scans first: the analysis goal when there is one, else the
 *  cleaned name. */
export function traceTitle(name: string, goal?: string | null): string {
  return goal?.trim() || cleanName(name);
}

/** Span names, with the wrapper noise removed ("turn 3: <ctx …>{…" → "turn 3"). */
export function cleanSpanName(name: string): string {
  const cleaned = stripWrappers(name).replace(/:\s*$/, "");
  return cleaned || name;
}

// Harness wrappers in message text. Slash commands arrive as
// <command-message>/<command-name>/<command-args>; noise blocks drop whole;
// any other harness wrapper keeps its inner text.
const NOISE_BLOCK = /<(system-reminder|command-message|local-command-caveat)\b[^>]*>[\s\S]*?<\/\1>/gi;

/** Message text for display: "/name args" for slash commands, harness noise
 *  dropped, other wrapper tags unwrapped. */
export function cleanMessage(text: string): string {
  const name = /<command-name>([\s\S]*?)<\/command-name>/i.exec(text)?.[1]?.trim();
  let out = text;
  if (name) {
    const args = /<command-args>([\s\S]*?)<\/command-args>/i.exec(text)?.[1]?.trim() ?? "";
    out = out
      .replace(/<command-name>[\s\S]*?<\/command-name>/i, `${name}${args ? ` ${args}` : ""}`)
      .replace(/<command-args>[\s\S]*?<\/command-args>/i, "");
  }
  return out
    .replace(NOISE_BLOCK, "")
    // Harness tags are hyphenated/underscored; plain HTML in prose survives.
    .replace(/<\/?[a-z]+[-_][\w-]*(\s[^<>]*)?>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
