// Agents answer in JSON (structured outputs), and replays stream that JSON in pieces.
// These helpers pull the human-readable parts out of a possibly incomplete JSON string.

function unescapeJson(s: string): string {
  return s
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, " ")
    .replace(/\\"/g, '"')
    .replace(/\\u([0-9a-fA-F]{4})/g, (_, h: string) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\\\/g, "\\");
}

/** The value of a string field, even when the closing quote has not arrived yet. */
export function partialField(raw: string, key: string): string | null {
  const m = new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)("?)`).exec(raw);
  if (!m || m[1] === undefined) return null;
  return unescapeJson(m[1].replace(/\\$/, ""));
}

/** Complete string items of an array field seen so far. */
export function partialArray(raw: string, key: string): string[] {
  const start = new RegExp(`"${key}"\\s*:\\s*\\[`).exec(raw);
  if (!start) return [];
  const rest = raw.slice(start.index + start[0].length);
  const out: string[] = [];
  const re = /\s*"((?:[^"\\]|\\.)*)"\s*(,|\])/y;
  let m: RegExpExecArray | null;
  while ((m = re.exec(rest))) {
    out.push(unescapeJson(m[1] ?? ""));
    if (m[2] === "]") break;
  }
  return out;
}

/** Splits prose that came before a JSON answer from the JSON itself. */
function splitProse(raw: string): { prose: string; json: string } {
  const i = raw.search(/\{\s*"/);
  if (i === -1) return { prose: raw, json: "" };
  return { prose: raw.slice(0, i).trim(), json: raw.slice(i) };
}

/** Readable advocate text: any prose, then the argument field of the memo as it streams. */
export function advocateReadable(raw: string): string {
  const { prose, json } = splitProse(raw);
  if (!json) return prose;
  const arg = partialField(json, "argument") ?? partialField(json, "reasoning");
  const parts = [prose, arg ?? "Drafting the memo…"].filter(Boolean);
  return parts.join("\n\n");
}

/** Readable adjudicator text: the GRI path as it forms, then the reasoning. */
export function adjudicatorReadable(raw: string): string {
  const { prose, json } = splitProse(raw);
  if (!json) return prose;
  const lines: string[] = [];
  if (prose) lines.push(prose);
  const code = partialField(json, "hts10");
  const gri = partialArray(json, "gri_path");
  const deciding = partialField(json, "deciding_gri");
  const why = partialField(json, "rationale");
  if (gri.length) lines.push(gri.map((g, i) => `${i + 1}. ${g}`).join("\n"));
  if (deciding) lines.push(`Deciding rule: ${deciding}.`);
  if (why) lines.push(why);
  if (code && !why) lines.push(`Leaning to ${code}.`);
  return lines.length ? lines.join("\n\n") : "Writing the ruling…";
}

/** A short, readable summary of one tool call for the counsel card. */
export function describeToolCall(tool: string, args: Record<string, unknown>): string {
  const a = (k: string) => (typeof args[k] === "string" || typeof args[k] === "number" ? String(args[k]) : "");
  switch (tool) {
    case "hts_search":
      return `Searches the tariff for "${a("text")}"`;
    case "hts_navigate":
      return `Opens ${a("code")} in the schedule`;
    case "get_notes":
      return `Reads the ${a("scope")} ${a("id")} notes`;
    case "get_gri":
      return "Reads the General Rules of Interpretation";
    case "cross_search":
      return `Searches CBP rulings for "${a("query")}"`;
    case "get_ruling":
      return `Reads ruling ${a("id")}`;
    case "ruling_status":
      return `Checks whether ruling ${a("id")} is still in force`;
    case "hts_revision_diff":
      return `Compares ${a("code")} with the ${a("rev_a")} schedule`;
    case "ask_expert":
      return "Asks a senior expert";
    default:
      return tool;
  }
}

/** Status of a ruling from a ruling_status or get_ruling result preview. */
export function statusFromPreview(preview: string): "in_force" | "modified" | "revoked" | "unknown" | null {
  const m = /"status"\s*:\s*"(in_force|modified|revoked|unknown)"/.exec(preview);
  return m ? (m[1] as "in_force" | "modified" | "revoked" | "unknown") : null;
}
