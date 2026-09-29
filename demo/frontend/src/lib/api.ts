import type {
  Arm,
  Config,
  Exhibit,
  HtsNodeResponse,
  MysteryReveal,
  ObjectionResult,
  Revisions,
  RunEvent,
  TimeMachineResult,
} from "./types";

export type EventSink = (ev: RunEvent) => void;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function readError(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object") {
      const rec = body as Record<string, unknown>;
      if (typeof rec.error === "string") return rec.error;
      if (typeof rec.detail === "string") return rec.detail;
      if (Array.isArray(rec.detail)) return "The court could not read that request.";
    }
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status})`;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(await readError(res), res.status);
  return (await res.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  if (!res.ok) throw new ApiError(await readError(res), res.status);
  return (await res.json()) as T;
}

/**
 * Reads a text/event-stream body and forwards each `data:` JSON payload.
 * fetch is used instead of EventSource because /api/classify is a POST.
 */
export async function consumeSse(res: Response, sink: EventSink, signal: AbortSignal): Promise<void> {
  if (!res.body) throw new Error("Stream has no body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;

  const flushMessage = (raw: string) => {
    const dataLines: string[] = [];
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length === 0) return;
    try {
      const ev = JSON.parse(dataLines.join("\n")) as RunEvent;
      if (ev.type === "done") sawDone = true;
      sink(ev);
    } catch {
      sink({ type: "error", message: "Could not read an event from the stream.", t: 0, run_id: "", agent: "client" });
    }
  };

  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const raw = buffer.slice(0, idx);
        const sepLen = buffer.slice(idx).startsWith("\r\n\r\n") ? 4 : 2;
        buffer = buffer.slice(idx + sepLen);
        flushMessage(raw);
      }
    }
    if (buffer.trim()) flushMessage(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!sawDone && !signal.aborted) sink({ type: "done" });
}

/** Replay speed from the page URL (?speed=4), used by tests and the video recorder. */
function replaySpeed(): number {
  const v = Number(new URLSearchParams(window.location.search).get("speed") ?? "1");
  return Number.isFinite(v) && v >= 0 ? v : 1;
}

export const api = {
  config: () => getJson<Config>("/api/config"),
  exhibits: () => getJson<Exhibit[]>("/api/exhibits"),
  revisions: () => getJson<Revisions>("/api/revisions"),
  htsNode: (code: string) => getJson<HtsNodeResponse>(`/api/hts/${encodeURIComponent(code || "root")}`),
  timeMachine: (code: string, revA: string, revB = "current") =>
    getJson<TimeMachineResult>(
      `/api/hts-diff?code=${encodeURIComponent(code)}&rev_a=${encodeURIComponent(revA)}&rev_b=${encodeURIComponent(revB)}`,
    ),
  reveal: (exhibitId: string) => getJson<MysteryReveal>(`/api/exhibits/${encodeURIComponent(exhibitId)}/reveal`),
  objection: (exhibitId: string, factChange: string, description: string) =>
    postJson<ObjectionResult>("/api/objection", { exhibit_id: exhibitId, fact_change: factChange, description }),
  describePhoto: (image: string) => postJson<{ description: string; session_spent_usd: number }>("/api/describe-photo", { image }),

  async replay(exhibitId: string, sink: EventSink, signal: AbortSignal): Promise<void> {
    const res = await fetch(`/api/replay/${encodeURIComponent(exhibitId)}?speed=${replaySpeed()}`, {
      headers: { Accept: "text/event-stream" },
      signal,
    });
    if (!res.ok) throw new ApiError(await readError(res), res.status);
    await consumeSse(res, sink, signal);
  },

  async classify(description: string, arm: Arm, sink: EventSink, signal: AbortSignal): Promise<void> {
    const res = await fetch("/api/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ description, arm }),
      credentials: "same-origin",
      signal,
    });
    if (!res.ok) throw new ApiError(await readError(res), res.status);
    await consumeSse(res, sink, signal);
  },
};

export type CourtApi = typeof api;
