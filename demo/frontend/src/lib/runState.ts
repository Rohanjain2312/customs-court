import { digitsOf } from "./hts";
import type {
  AdvocateMemo,
  Arm,
  Classification,
  CostInfo,
  Facts,
  NodeState,
  RunEvent,
} from "./types";

export interface ToolCallEntry {
  id: number;
  t: number;
  agent: string;
  tool: string;
  args: Record<string, unknown>;
  result_preview: string;
  ms: number;
}

export interface AdvocateState {
  heading: string;
  text: string;
  startT: number;
  endT: number | null;
  memo: AdvocateMemo | null;
  tokens: number | null;
  ms: number | null;
}

export interface SpeakerState {
  text: string;
  startT: number | null;
  endT: number | null;
  /** Cumulative run tokens when this speaker started, used to estimate its own tokens. */
  tokensAtStart: number | null;
}

export interface FocusEntry {
  state: NodeState;
  reason: string;
  /** Digits of the code, used as the key for tree matching. */
  digits: string;
  code: string;
}

export type RunStatus = "idle" | "running" | "done" | "error" | "cancelled";

export interface RunState {
  /** Increments on every reset so views can key off a new hearing. */
  epoch: number;
  status: RunStatus;
  runId: string | null;
  description: string | null;
  arm: Arm | null;
  models: Record<string, string>;
  facts: Facts | null;
  missingFacts: string[];
  tools: ToolCallEntry[];
  advocates: Record<string, AdvocateState>;
  advocateOrder: string[];
  adjudicator: SpeakerState;
  counsel: SpeakerState;
  ruling: Classification | null;
  rulingT: number | null;
  cost: CostInfo | null;
  focus: Record<string, FocusEntry>;
  /** Most recent tree focus, with a sequence number so the tree can follow it. */
  lastFocus: { code: string; seq: number } | null;
  errors: string[];
  lastT: number;
  /** performance.now() when lastT was received; drives the live clock. */
  lastWall: number;
}

const emptySpeaker = (): SpeakerState => ({ text: "", startT: null, endT: null, tokensAtStart: null });

export function initialRunState(epoch = 0, carried: Record<string, FocusEntry> = {}): RunState {
  return {
    epoch,
    status: "idle",
    runId: null,
    description: null,
    arm: null,
    models: {},
    facts: null,
    missingFacts: [],
    tools: [],
    advocates: {},
    advocateOrder: [],
    adjudicator: emptySpeaker(),
    counsel: emptySpeaker(),
    ruling: null,
    rulingT: null,
    cost: null,
    focus: carried,
    lastFocus: null,
    errors: [],
    lastT: 0,
    lastWall: 0,
  };
}

export type RunAction =
  | { type: "reset"; status: RunStatus; carried?: Record<string, FocusEntry>; description?: string; arm?: Arm }
  | { type: "event"; ev: RunEvent; wall: number }
  | { type: "fail"; message: string }
  | { type: "cancel" };

// Higher rank wins when two events touch the same node.
const RANK: Record<NodeState, number> = { visited: 1, candidate: 2, rejected: 3, overruled: 4, chosen: 5 };

function setFocus(
  focus: Record<string, FocusEntry>,
  code: string,
  state: NodeState,
  reason: string,
  force = false,
): Record<string, FocusEntry> {
  const d = digitsOf(code);
  if (!d) return focus;
  const prev = focus[d];
  if (prev && !force) {
    // A later "rejected" or "chosen" always overrides a softer state.
    // "visited" never downgrades a stronger state.
    if (state === "visited" && RANK[prev.state] > RANK.visited) return focus;
    if (prev.state === "chosen" && state !== "chosen" && state !== "rejected") return focus;
    // The old ruling stays marked as overruled; a rejection in the rehearing only adds its reason.
    if (prev.state === "overruled" && state !== "chosen") {
      if (state !== "rejected" || !reason) return focus;
      return { ...focus, [d]: { ...prev, reason: `Overruled after an objection. ${reason}` } };
    }
  }
  return { ...focus, [d]: { state, reason: reason || prev?.reason || "", digits: d, code } };
}

export function totalTokens(c: CostInfo | null): number | null {
  return c ? c.input_tokens + c.output_tokens + c.cache_read_tokens + c.cache_write_tokens : null;
}

export function runReducer(s: RunState, a: RunAction): RunState {
  switch (a.type) {
    case "reset": {
      const next = initialRunState(s.epoch + 1, a.carried ?? {});
      next.status = a.status;
      next.description = a.description ?? null;
      next.arm = a.arm ?? null;
      next.lastWall = performance.now();
      return next;
    }
    case "fail":
      return { ...s, status: "error", errors: [...s.errors, a.message] };
    case "cancel":
      return s.status === "running" ? { ...s, status: "cancelled" } : s;
    case "event":
      return applyEvent(s, a.ev, a.wall);
  }
}

function applyEvent(s0: RunState, ev: RunEvent, wall: number): RunState {
  const t = typeof ev.t === "number" ? ev.t : s0.lastT;
  const s: RunState = { ...s0, lastT: Math.max(s0.lastT, t), lastWall: wall };
  switch (ev.type) {
    case "run_start":
      return {
        ...s,
        status: "running",
        runId: ev.run_id,
        description: ev.description,
        arm: ev.arm === "D" || ev.agent === "orchestrator" ? "multi" : "single",
        models: ev.models ?? {},
      };
    case "fact_extracted":
      return { ...s, facts: ev.facts, missingFacts: ev.missing_facts ?? [] };
    case "tool_call":
      return {
        ...s,
        tools: [
          ...s.tools,
          {
            id: s.tools.length,
            t,
            agent: ev.agent,
            tool: ev.tool,
            args: ev.args ?? {},
            result_preview: ev.result_preview ?? "",
            ms: ev.ms ?? 0,
          },
        ],
      };
    case "tree_focus": {
      const seq = (s.lastFocus?.seq ?? 0) + 1;
      return {
        ...s,
        focus: setFocus(s.focus, ev.code, ev.state, ev.reason ?? ""),
        lastFocus: { code: ev.code, seq },
      };
    }
    case "advocate_chunk": {
      const prev = s.advocates[ev.heading];
      const adv: AdvocateState = prev
        ? { ...prev, text: prev.text + ev.text }
        : { heading: ev.heading, text: ev.text, startT: t, endT: null, memo: null, tokens: null, ms: null };
      return {
        ...s,
        advocates: { ...s.advocates, [ev.heading]: adv },
        advocateOrder: prev ? s.advocateOrder : [...s.advocateOrder, ev.heading],
      };
    }
    case "advocate_done": {
      const prev = s.advocates[ev.heading];
      const adv: AdvocateState = {
        heading: ev.heading,
        text: prev?.text || ev.memo?.argument || "",
        startT: prev?.startT ?? t,
        endT: t,
        memo: ev.memo,
        tokens: ev.tokens,
        ms: ev.ms,
      };
      return {
        ...s,
        advocates: { ...s.advocates, [ev.heading]: adv },
        advocateOrder: prev ? s.advocateOrder : [...s.advocateOrder, ev.heading],
      };
    }
    case "adjudicator_chunk": {
      // Single-agent runs may stream their reasoning through this event; show it on the Counsel card.
      const key = s.arm === "single" ? "counsel" : "adjudicator";
      const prev = s[key];
      return {
        ...s,
        [key]: {
          ...prev,
          text: prev.text + ev.text,
          startT: prev.startT ?? t,
          tokensAtStart: prev.tokensAtStart ?? totalTokens(s.cost),
        },
      };
    }
    case "ruling": {
      const c = ev.classification;
      let focus = s.focus;
      if (c && !c.abstain && c.hts10) {
        focus = setFocus(focus, c.hts10, "chosen", "Final ruling", true);
      }
      for (const alt of c?.rejected_alternatives ?? []) {
        if (!focus[digitsOf(alt.code)] || focus[digitsOf(alt.code)]?.state !== "chosen") {
          focus = setFocus(focus, alt.code, "rejected", alt.reason);
        }
      }
      const key = s.arm === "single" ? "counsel" : "adjudicator";
      return {
        ...s,
        ruling: c,
        rulingT: t,
        focus,
        [key]: { ...s[key], endT: t, startT: s[key].startT ?? (key === "counsel" ? 0 : t) },
        lastFocus: c && !c.abstain ? { code: c.hts10, seq: (s.lastFocus?.seq ?? 0) + 1 } : s.lastFocus,
      };
    }
    case "cost_update": {
      const { usd, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, calls, cache_hit_rate } = ev;
      return {
        ...s,
        cost: { usd, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, calls, cache_hit_rate },
      };
    }
    case "error":
      return { ...s, errors: [...s.errors, ev.message] };
    case "done":
      return { ...s, status: s.status === "error" ? "error" : "done" };
  }
}

/** Tokens a speaker used, estimated from the cumulative cost counter. */
export function speakerTokens(sp: SpeakerState, cost: CostInfo | null): number | null {
  if (!cost || sp.tokensAtStart === null) return null;
  const now = totalTokens(cost) ?? 0;
  return Math.max(0, now - sp.tokensAtStart);
}

/** Codes chosen in this run, turned into "overruled" marks for the next run. */
export function carryOverruled(s: RunState): Record<string, FocusEntry> {
  const out: Record<string, FocusEntry> = {};
  for (const [k, v] of Object.entries(s.focus)) {
    if (v.state === "chosen" || v.state === "overruled") {
      out[k] = { ...v, state: "overruled", reason: "Overruled after an objection" };
    }
  }
  return out;
}
