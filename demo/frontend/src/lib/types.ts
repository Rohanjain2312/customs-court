// Types mirroring the backend contract in demo/backend/app.py (prefix /api).

export type Arm = "single" | "multi";

export interface Config {
  mode: "replay" | "live";
  live: boolean;
  live_reason: string;
  photo: boolean;
  session_cap_usd: number;
  session_spent_usd: number;
  max_gap_s: number;
  timing_note: string;
}

export interface RecordedCost {
  usd: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  tokens: number;
  calls: number;
  cache_hit_rate: number;
  tool_calls: number;
  api_latency_s: number | null;
  wall_s: number | null;
  events: number;
}

export interface Exhibit {
  exhibit_id: string;
  title: string;
  description: string;
  blurb: string;
  kind: "exhibit" | "objection" | "timemachine";
  mystery: boolean;
  sealed?: boolean;
  agent: Arm;
  arm: string;
  models: Record<string, string>;
  pair: string;
  order: number;
  objection_of: string | null;
  fact_change: string;
  timemachine: { code: string; rev_a: string; rev_b?: string } | null;
  placeholder: boolean;
  placeholder_note: string;
  note: string;
  gold_code?: string;
  ruling_id?: string;
  reference_excerpt?: string;
  outcome?: { pred: string; exact_10?: boolean | null; exact_6?: boolean | null };
  recorded: RecordedCost;
  source: { run_id: string; item_id: string; dataset: string };
  arms?: Partial<Record<Arm, string>>;
  objections: string[];
}

export type RulingStatus = "in_force" | "modified" | "revoked" | "unknown";

export interface CitedRuling {
  id: string;
  status: RulingStatus;
}

export interface Facts {
  material?: string;
  function?: string;
  form?: string;
  end_use?: string;
  [k: string]: string | undefined;
}

export interface AdvocateMemo {
  heading: string;
  best_code: string;
  argument: string;
  supporting_rulings: CitedRuling[];
  exclusions_against: string[];
  strength: number;
}

export interface Classification {
  hts10: string;
  facts: Facts;
  gri_path: string[];
  deciding_gri: string;
  cited_rulings: CitedRuling[];
  rejected_alternatives: { code: string; reason: string }[];
  missing_facts: string[];
  confidence: number;
  abstain: boolean;
  rationale: string;
}

export type FocusState = "visited" | "candidate" | "rejected" | "chosen";
export type NodeState = FocusState | "overruled";

export interface CostInfo {
  usd: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  calls: number;
  cache_hit_rate: number;
}

interface EventBase {
  t: number;
  t_orig?: number;
  run_id: string;
  agent: string;
}

export type RunEvent =
  | (EventBase & { type: "run_start"; description: string; arm: string; models: Record<string, string> })
  | (EventBase & { type: "fact_extracted"; facts: Facts; missing_facts: string[] })
  | (EventBase & {
      type: "tool_call";
      tool: string;
      args: Record<string, unknown>;
      result_preview: string;
      ms: number;
    })
  | (EventBase & { type: "tree_focus"; code: string; state: FocusState; reason: string })
  | (EventBase & { type: "advocate_chunk"; heading: string; text: string })
  | (EventBase & {
      type: "advocate_done";
      heading: string;
      memo: AdvocateMemo;
      tokens: number;
      ms: number;
    })
  | (EventBase & { type: "adjudicator_chunk"; text: string })
  | (EventBase & { type: "ruling"; classification: Classification })
  | (EventBase & ({ type: "cost_update" } & CostInfo))
  | (EventBase & { type: "error"; message: string })
  | {
      type: "done";
      t?: number;
      run_id?: string;
      agent?: string;
      live?: boolean;
      usd?: number;
      session_spent_usd?: number;
      session_cap_usd?: number;
    };

export type RunEventType = RunEvent["type"];

export interface HtsChild {
  code: string;
  description: string;
  is_leaf: boolean;
  level: string;
  range?: [number, number];
}

export interface HtsNodeResponse {
  code: string;
  description: string;
  level: string;
  parent: { code: string; description: string } | null;
  children: HtsChild[];
}

export interface TimeMachineNode {
  code: string;
  description: string;
  path: string;
  general_rate: string;
  other_rate: string;
}

export type TimeMachineChange =
  | "unchanged"
  | "added"
  | "removed"
  | "description_changed"
  | "rate_changed"
  | "not_found";

export interface TimeMachineResult {
  code: string;
  rev_a: string;
  rev_b: string;
  change: TimeMachineChange;
  node_a: TimeMachineNode | null;
  node_b: TimeMachineNode | null;
  details: string[];
  available_revisions: string[];
}

export interface Revisions {
  current: string;
  revisions: { name: string; year: number }[];
}

export interface MysteryReveal {
  exhibit_id: string;
  gold_code: string;
  ruling_id: string;
  ruling_date: string;
  reference_excerpt: string;
  dataset: string;
}

export type ObjectionResult =
  | { mode: "replay"; exhibit_id: string; fact_change: string; placeholder: boolean }
  | { mode: "live"; fact_change: string; description: string };
