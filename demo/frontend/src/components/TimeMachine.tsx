import { useEffect, useRef, useState } from "react";
import type { CourtApi } from "../lib/api";
import { digitsOf, formatHts } from "../lib/hts";
import type { Revisions, TimeMachineChange, TimeMachineNode, TimeMachineResult } from "../lib/types";
import { SectionHead } from "./bits";

const CHANGE: Record<TimeMachineChange, { label: string; cls: string; icon: string; say: string }> = {
  unchanged: { label: "Unchanged", cls: "border-verdict-green/70 text-verdict-green", icon: "=", say: "Same line, same wording, same rates." },
  added: { label: "New since then", cls: "border-brass-300 text-brass-200", icon: "+", say: "This line did not exist in the older edition." },
  removed: { label: "Gone today", cls: "border-verdict-red/70 text-verdict-red", icon: "−", say: "This line existed then but not today. A ruling that cites it is stale." },
  description_changed: { label: "Wording changed", cls: "border-verdict-amber/70 text-verdict-amber", icon: "✎", say: "Same number, different text." },
  rate_changed: { label: "Rate changed", cls: "border-verdict-amber/70 text-verdict-amber", icon: "%", say: "Same line, different duty rate." },
  not_found: { label: "Not in either edition", cls: "border-verdict-gray/60 text-verdict-gray", icon: "?", say: "Try a shorter code or another year." },
};

function NodeCol({ title, node, other, testid }: { title: string; node: TimeMachineNode | null; other: TimeMachineNode | null; testid: string }) {
  const diff = (k: keyof TimeMachineNode) =>
    node && other && node[k] !== other[k] ? "rounded bg-verdict-amber/15 px-1 ring-1 ring-verdict-amber/40" : "";
  return (
    <div className="min-w-0 rounded border border-brass-800 bg-ink-900/60 p-2.5" data-testid={testid}>
      <div className="kicker mb-1">{title}</div>
      {node ? (
        <dl className="space-y-1 text-[0.82rem]">
          <dd className="code text-lg text-brass-200">{formatHts(node.code)}</dd>
          <dd className={`text-parchment-100 ${diff("description")}`}>{node.description}</dd>
          {node.path ? <dd className="line-clamp-3 text-[0.75rem] leading-snug text-parchment-500">{node.path}</dd> : null}
          <div className="flex gap-3 pt-1">
            <div>
              <dt className="text-[0.68rem] uppercase tracking-wider text-parchment-500">General</dt>
              <dd className={`code text-parchment-100 ${diff("general_rate")}`}>{node.general_rate || (digitsOf(node.code).length === 10 ? "on 8-digit line" : "--")}</dd>
            </div>
            <div>
              <dt className="text-[0.68rem] uppercase tracking-wider text-parchment-500">Column 2</dt>
              <dd className={`code text-parchment-100 ${diff("other_rate")}`}>{node.other_rate || (digitsOf(node.code).length === 10 ? "on 8-digit line" : "--")}</dd>
            </div>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-parchment-500">No such line in this edition.</p>
      )}
    </div>
  );
}

export interface TimeTarget {
  code: string;
  rev?: string;
  seq: number;
}

function resolveRev(revs: Revisions | null, want: string | undefined): string | null {
  if (!revs) return null;
  const older = revs.revisions.filter((r) => r.name !== revs.current);
  if (want) {
    const hit = older.find((r) => r.name === want) ?? older.find((r) => r.name.startsWith(want));
    if (hit) return hit.name;
  }
  return older[0]?.name ?? null;
}

export function TimeMachine({ api, target, pickedCode }: { api: CourtApi; target: TimeTarget | null; pickedCode: string | null }) {
  const [revs, setRevs] = useState<Revisions | null>(null);
  const [code, setCode] = useState("");
  const [rev, setRev] = useState<string | null>(null);
  const [result, setResult] = useState<TimeMachineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reqId = useRef(0);

  useEffect(() => {
    api
      .revisions()
      .then((r) => {
        setRevs(r);
        setRev((cur) => cur ?? resolveRev(r, "2018"));
      })
      .catch(() => setError("The schedule editions could not be loaded."));
  }, [api]);

  const run = async (c: string, r: string | null) => {
    if (digitsOf(c).length < 4 || !r) return;
    const id = ++reqId.current;
    setBusy(true);
    setError(null);
    try {
      const res = await api.timeMachine(c, r);
      if (id === reqId.current) setResult(res);
    } catch (e) {
      if (id === reqId.current) setError(e instanceof Error ? e.message : "The time machine failed.");
    } finally {
      if (id === reqId.current) setBusy(false);
    }
  };

  // A new ruling or a time-machine exhibit sets the code (and maybe the year).
  useEffect(() => {
    if (!target || !revs) return;
    const r = target.rev ? resolveRev(revs, target.rev) : rev ?? resolveRev(revs, "2018");
    setCode(formatHts(target.code));
    setRev(r);
    void run(target.code, r);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.seq, revs]);

  const ch = result ? CHANGE[result.change] ?? CHANGE.not_found : null;
  const older = revs ? revs.revisions.filter((r) => r.name !== revs.current) : [];
  const revLabel = (name: string) => {
    const r = revs?.revisions.find((x) => x.name === name);
    return r ? `${r.year} · ${name.replace(/^\d{4}/, "").replace(/([a-z])([A-Z])/g, "$1 $2") || "Basic"}` : name;
  };

  return (
    <section className="panel flex flex-col p-4" aria-labelledby="tm-title" data-testid="timemachine">
      <SectionHead kicker="V · Precedent" title="Time Machine" id="tm-title" />
      <p className="mb-3 text-[0.85rem] text-parchment-300">
        Old rulings cite old codes. Pick an edition of the schedule and compare one line with today{revs ? ` (${revs.current})` : ""}.
      </p>
      <form
        className="grid grid-cols-[1fr_auto_auto] items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(code, rev);
        }}
      >
        <div>
          <label htmlFor="tm-code" className="kicker mb-1 block">
            Code
          </label>
          <input
            id="tm-code"
            data-testid="timemachine-code"
            className="field code"
            value={code}
            placeholder="3918.10.10.00"
            onChange={(e) => setCode(e.target.value.replace(/[^\d.]/g, ""))}
          />
        </div>
        <div>
          <label htmlFor="tm-year" className="kicker mb-1 block">
            Edition
          </label>
          <select
            id="tm-year"
            data-testid="timemachine-year"
            className="field code w-auto pr-8"
            value={rev ?? ""}
            onChange={(e) => {
              setRev(e.target.value);
              void run(code, e.target.value);
            }}
          >
            {older.map((r) => (
              <option key={r.name} value={r.name}>
                {revLabel(r.name)}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" data-testid="timemachine-go" className="btn-ghost h-[2.6rem]" disabled={busy || digitsOf(code).length < 4}>
          {busy ? "…" : "Go"}
        </button>
      </form>
      {pickedCode && digitsOf(pickedCode).length >= 4 && digitsOf(pickedCode) !== digitsOf(code) ? (
        <button
          type="button"
          className="mt-1 self-start text-xs text-parchment-400 underline hover:text-brass-200"
          onClick={() => {
            setCode(formatHts(pickedCode));
            void run(pickedCode, rev);
          }}
        >
          Use the tree selection: <span className="code">{formatHts(pickedCode)}</span>
        </button>
      ) : null}

      <div data-testid="timemachine-result" className="mt-3" aria-live="polite" data-change={result?.change ?? ""}>
        {error ? (
          <p role="alert" className="text-sm text-verdict-red">
            {error}
          </p>
        ) : !result ? (
          <p className="text-sm text-parchment-500">A ruling fills the code in. You can also type one, or click a line on the tree.</p>
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              {ch ? (
                <span className={`badge ${ch.cls}`} data-testid="timemachine-change">
                  <span aria-hidden="true">{ch.icon}</span>
                  {ch.label}
                </span>
              ) : null}
              <span className="text-xs text-parchment-400">
                {result.rev_a} <span aria-hidden="true">→</span> {result.rev_b}
              </span>
            </div>
            {ch ? <p className="text-[0.82rem] text-parchment-300">{ch.say}</p> : null}
            <div className="grid grid-cols-2 gap-2">
              <NodeCol title={`Then · ${revLabel(result.rev_a)}`} node={result.node_a} other={result.node_b} testid="tm-then" />
              <NodeCol title={`Today · ${result.rev_b}`} node={result.node_b} other={result.node_a} testid="tm-now" />
            </div>
            {result.details.length ? (
              <div>
                <div className="kicker mb-1">{result.change === "removed" ? "Where the goods went" : "Details"}</div>
                <ul className="scroll-thin max-h-32 list-disc space-y-0.5 overflow-y-auto pl-4 text-[0.78rem] text-parchment-200 marker:text-brass-500">
                  {result.details.map((d) => (
                    <li key={d}>{d.replace(/^now under (\d+): (\S+) .*> /, "$2 · ")}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}
