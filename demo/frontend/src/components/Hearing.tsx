import { useEffect, useRef, useState, type ReactNode } from "react";
import { digitsOf, formatHts } from "../lib/hts";
import { speakerTokens, type AdvocateState, type RunState, type SpeakerState } from "../lib/runState";
import { adjudicatorReadable, advocateReadable, describeToolCall, statusFromPreview } from "../lib/text";
import { fmtInt, fmtSecs, Meter, RulingCite, StatusBadge, unit } from "./bits";

/** Run time in seconds, ticking between events while the hearing is live. */
export function useRunClock(run: RunState): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (run.status !== "running") return;
    const id = window.setInterval(() => setNow(performance.now()), 200);
    return () => window.clearInterval(id);
  }, [run.status]);
  if (run.status !== "running") return run.lastT;
  return run.lastT + Math.max(0, (now - run.lastWall) / 1000);
}

function useAutoScroll(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [dep]);
  return ref;
}

function CardStats({ elapsed, tokens, live }: { elapsed: number | null; tokens: number | null; live: boolean }) {
  return (
    <div className="flex items-center gap-3 font-mono text-[0.72rem] text-parchment-400">
      <span title="Elapsed time">
        <span className="sr-only">Elapsed </span>
        <span aria-hidden="true">⏱ </span>
        {fmtSecs(elapsed)}
        {live ? <span className="ml-1 text-brass-400">live</span> : null}
      </span>
      <span title="Tokens">
        {fmtInt(tokens)} <span className="text-parchment-500">tok</span>
      </span>
    </div>
  );
}

function AdvocateCard({ a, now, winnerDigits, running }: { a: AdvocateState; now: number; winnerDigits: string | null; running: boolean }) {
  const done = a.memo !== null;
  const scrollRef = useAutoScroll(a.text.length);
  const elapsed = a.ms !== null ? a.ms / 1000 : (a.endT ?? now) - a.startT;
  const prevailed = winnerDigits !== null && a.memo ? winnerDigits.startsWith(digitsOf(a.heading)) : null;
  return (
    <article
      data-testid="advocate-card"
      data-heading={a.heading}
      className={`panel animate-rise p-3 ${prevailed ? "ring-1 ring-brass-300/80 shadow-glow" : ""}`}
      aria-label={`Advocate for heading ${a.heading}`}
    >
      <header className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="kicker">Advocate for</div>
          <div className="code text-[1.25rem] font-semibold leading-tight text-brass-300">{formatHts(a.heading)}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {prevailed === true ? (
            <span className="badge border-brass-300 bg-brass-400 text-walnut-950">Prevailed</span>
          ) : prevailed === false ? (
            <span className="badge border-parchment-500 text-parchment-400">Did not prevail</span>
          ) : done ? (
            <span className="badge border-brass-600 text-brass-300">Rests</span>
          ) : (
            <span className="badge border-brass-500 text-brass-200">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brass-300" aria-hidden="true" />
              Arguing
            </span>
          )}
          <CardStats elapsed={elapsed} tokens={a.tokens} live={!done && running} />
        </div>
      </header>

      <div ref={scrollRef} className="scroll-thin max-h-32 overflow-y-auto pr-1 text-[0.88rem] leading-relaxed text-parchment-100">
        <p className={`whitespace-pre-line ${!done && running ? "caret-on" : ""}`}>
          {done && a.memo?.argument ? a.memo.argument : advocateReadable(a.text)}
        </p>
      </div>

      {a.memo ? (
        <div className="mt-3 space-y-2 border-t border-brass-800/80 pt-2 text-[0.82rem]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-parchment-400">Best line</span>
            <span className="code text-brass-200">{formatHts(a.memo.best_code)}</span>
          </div>
          <div>
            <div className="mb-1 text-parchment-400">Strength</div>
            <Meter value={unit(a.memo.strength)} label={`Argument strength for ${a.heading}`} tone={unit(a.memo.strength) < 0.35 ? "red" : "brass"} />
          </div>
          {a.memo.supporting_rulings.length > 0 ? (
            <div>
              <div className="text-parchment-400">Supporting rulings</div>
              <ul>
                {a.memo.supporting_rulings.map((r) => (
                  <RulingCite key={r.id} id={r.id} status={r.status} />
                ))}
              </ul>
            </div>
          ) : (
            <div className="text-parchment-500">No supporting rulings cited.</div>
          )}
          {a.memo.exclusions_against.length > 0 ? (
            <div>
              <div className="text-parchment-400">Points against</div>
              <ul className="list-disc space-y-0.5 pl-4 text-parchment-200 marker:text-verdict-red">
                {a.memo.exclusions_against.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function SpeakerCard({
  testid,
  kicker,
  title,
  sp,
  now,
  tokens,
  running,
  extra,
  emptyText,
}: {
  testid: string;
  kicker: string;
  title: string;
  sp: SpeakerState;
  now: number;
  tokens: number | null;
  running: boolean;
  extra?: ReactNode;
  emptyText: string;
}) {
  const scrollRef = useAutoScroll(sp.text.length);
  const speaking = running && sp.startT !== null && sp.endT === null;
  const elapsed = sp.startT === null ? null : (sp.endT ?? now) - sp.startT;
  return (
    <article data-testid={testid} className="panel animate-rise border-brass-500/70 p-3" aria-label={title}>
      <header className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="kicker">{kicker}</div>
          <div className="font-display text-[1.35rem] font-semibold leading-tight text-brass-200">{title}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {sp.endT !== null ? (
            <span className="badge border-brass-300 text-brass-200">Ruled</span>
          ) : speaking ? (
            <span className="badge border-brass-500 text-brass-200">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brass-300" aria-hidden="true" />
              Speaking
            </span>
          ) : (
            <span className="badge border-parchment-600 text-parchment-400">Waiting</span>
          )}
          <CardStats elapsed={elapsed} tokens={tokens} live={speaking} />
        </div>
      </header>
      <div ref={scrollRef} className="scroll-thin max-h-40 overflow-y-auto pr-1 text-[0.9rem] leading-relaxed">
        {sp.text ? (
          <p className={`whitespace-pre-line ${speaking ? "caret-on" : ""}`}>{adjudicatorReadable(sp.text)}</p>
        ) : (
          <p className="text-parchment-500">{emptyText}</p>
        )}
      </div>
      {extra}
    </article>
  );
}

function FactsCard({ run }: { run: RunState }) {
  if (!run.facts) return null;
  const rows: [string, string | undefined][] = [
    ["Material", run.facts.material],
    ["Function", run.facts.function],
    ["Form", run.facts.form],
    ["End use", run.facts.end_use],
  ];
  return (
    <section className="rounded border border-brass-800/70 bg-ink-900/60 p-3 animate-rise" aria-label="Facts on the record">
      <div className="kicker mb-1.5">Facts on the record</div>
      <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1 text-[0.85rem]">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-parchment-400">{k}</dt>
            <dd className="text-parchment-100">{v || <span className="text-parchment-500">Not stated</span>}</dd>
          </div>
        ))}
      </dl>
      {run.missingFacts.length > 0 ? (
        <div className="mt-2 text-[0.8rem] text-verdict-amber">
          <span className="font-semibold">Not in the record: </span>
          {run.missingFacts.join("; ")}
        </div>
      ) : null}
    </section>
  );
}

function ClerksLog({ run }: { run: RunState }) {
  const [open, setOpen] = useState(false);
  if (run.tools.length === 0) return null;
  const last = run.tools[run.tools.length - 1];
  return (
    <section className="rounded border border-brass-800/70 bg-ink-900/60 text-[0.8rem]" aria-label="Clerk's log of tool calls">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="kicker">Clerk's log · {run.tools.length} lookups</span>
        {!open && last ? (
          <span className="truncate font-mono text-parchment-300">
            {last.tool} <span className="text-parchment-500">{last.ms}ms</span>
          </span>
        ) : null}
        <span aria-hidden="true" className="text-brass-400">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open ? (
        <ol className="scroll-thin max-h-48 space-y-1.5 overflow-y-auto border-t border-brass-800/70 px-3 py-2">
          {run.tools.map((c) => (
            <li key={c.id} className="font-mono">
              <div className="flex justify-between gap-2">
                <span className="text-brass-300">
                  {c.tool}
                  <span className="text-parchment-500"> · {c.agent}</span>
                </span>
                <span className="text-parchment-500">
                  {fmtSecs(c.t)} · {c.ms}ms
                </span>
              </div>
              <div className="truncate text-parchment-400">{JSON.stringify(c.args)}</div>
              <div className="text-parchment-200">{c.result_preview}</div>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

function CounselCard({ run, now, running }: { run: RunState; now: number; running: boolean }) {
  const steps = run.tools;
  const scrollRef = useAutoScroll(steps.length + (run.ruling ? 1 : 0));
  const done = run.ruling !== null;
  const elapsed = run.runId ? (done ? (run.rulingT ?? now) : now) : null;
  const tokens = run.cost ? run.cost.input_tokens + run.cost.output_tokens + run.cost.cache_read_tokens + run.cost.cache_write_tokens : null;
  return (
    <article data-testid="counsel-card" className="panel animate-rise border-brass-500/70 p-3" aria-label="Counsel, the single agent">
      <header className="mb-2 flex items-start justify-between gap-2">
        <div>
          <div className="kicker">Single agent</div>
          <div className="font-display text-[1.35rem] font-semibold leading-tight text-brass-200">Counsel</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {done ? (
            <span className="badge border-brass-300 text-brass-200">Ruled</span>
          ) : running ? (
            <span className="badge border-brass-500 text-brass-200">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brass-300" aria-hidden="true" />
              Working
            </span>
          ) : (
            <span className="badge border-parchment-600 text-parchment-400">Waiting</span>
          )}
          <CardStats elapsed={elapsed} tokens={tokens} live={!done && running} />
        </div>
      </header>
      <div ref={scrollRef} className="scroll-thin max-h-56 overflow-y-auto pr-1 text-[0.86rem] leading-relaxed">
        {steps.length === 0 && !done ? <p className="text-parchment-500">Counsel is reading the file.</p> : null}
        <ol className="space-y-1">
          {steps.map((c, i) => {
            const st = c.tool === "ruling_status" || c.tool === "get_ruling" ? statusFromPreview(c.result_preview) : null;
            return (
              <li key={c.id} className="flex items-start gap-2 animate-rise" data-testid="counsel-step">
                <span className="code mt-[1px] w-5 shrink-0 text-right text-[0.72rem] text-brass-500">{i + 1}</span>
                <span className="text-parchment-100">
                  {describeToolCall(c.tool, c.args)}
                  {c.agent === "checker" ? <span className="ml-1 text-parchment-500">(final check)</span> : null}
                </span>
                {st ? <span className="ml-auto shrink-0"><StatusBadge status={st} /></span> : null}
              </li>
            );
          })}
        </ol>
        {run.ruling ? (
          <p className="mt-2 border-t border-brass-800/80 pt-2 text-parchment-100 animate-rise">
            Rules <span className="code text-brass-200">{run.ruling.abstain ? "no code (abstains)" : formatHts(run.ruling.hts10)}</span>
            {run.ruling.rationale ? <span className="mt-1 block line-clamp-3 text-parchment-300">{run.ruling.rationale}</span> : null}
          </p>
        ) : running && steps.length > 0 ? (
          <p className="caret-on mt-2 text-parchment-400">Weighing the evidence</p>
        ) : null}
      </div>
      {run.ruling ? (
        <div className="mt-2 flex items-center justify-between border-t border-brass-800/80 pt-2 text-[0.85rem]">
          <span className="text-parchment-400">Deciding rule</span>
          <span className="badge border-brass-300 bg-brass-400/15 text-brass-200" data-testid="deciding-gri">{run.ruling.deciding_gri || "Not stated"}</span>
        </div>
      ) : null}
    </article>
  );
}

export function Hearing({ run, onJumpToRuling, idle }: { run: RunState; onJumpToRuling: () => void; idle?: ReactNode }) {
  const now = useRunClock(run);
  const running = run.status === "running";
  const isSingle = run.arm === "single";
  const winner = run.ruling && !run.ruling.abstain ? digitsOf(run.ruling.hts10) : null;

  if (run.status === "idle") {
    return (
      idle ?? (
        <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-10 text-center text-parchment-400">
          <div className="font-display text-2xl text-parchment-200">The court is in recess.</div>
          <p className="max-w-xs text-sm">Pick an exhibit from the docket to open a hearing.</p>
        </div>
      )
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <FactsCard run={run} />
      {!isSingle ? <ClerksLog run={run} /> : null}

      {isSingle ? (
        <CounselCard run={run} now={now} running={running} />
      ) : (
        <>
          {run.advocateOrder.length === 0 && running ? (
            <div className="rounded border border-dashed border-brass-800 p-3 text-sm text-parchment-400">Advocates are preparing their briefs.</div>
          ) : null}
          <div className="grid gap-3">
            {run.advocateOrder.map((h) => {
              const a = run.advocates[h];
              return a ? <AdvocateCard key={h} a={a} now={now} winnerDigits={winner} running={running} /> : null;
            })}
          </div>
          {run.advocateOrder.length > 0 || run.adjudicator.text ? (
            <SpeakerCard
              testid="adjudicator-card"
              kicker="The bench"
              title="Adjudicator"
              sp={run.adjudicator}
              now={now}
              tokens={speakerTokens(run.adjudicator, run.cost)}
              running={running}
              emptyText="The adjudicator waits for every advocate to rest."
              extra={
                run.ruling ? (
                  <div className="mt-2 flex items-center justify-between border-t border-brass-800/80 pt-2 text-[0.85rem]">
                    <span className="text-parchment-400">Deciding rule</span>
                    <span className="badge border-brass-300 bg-brass-400/15 text-brass-200" data-testid="deciding-gri">
                      {run.ruling.deciding_gri || "Not stated"}
                    </span>
                  </div>
                ) : null
              }
            />
          ) : null}
        </>
      )}

      {run.ruling ? (
        <button
          type="button"
          onClick={onJumpToRuling}
          className="panel group flex items-center justify-between gap-3 border-brass-400 p-3 text-left shadow-glow animate-rise"
          aria-label="Go to the full ruling"
        >
          <div>
            <div className="kicker">Verdict</div>
            <div className="code text-[1.6rem] font-semibold text-brass-300">
              {run.ruling.abstain ? "Abstained" : formatHts(run.ruling.hts10)}
            </div>
          </div>
          <span className="text-sm text-parchment-300 group-hover:text-brass-200">Full ruling ↓</span>
        </button>
      ) : null}

      {run.errors.length > 0 ? (
        <div role="alert" className="rounded border border-verdict-red/60 bg-verdict-red/10 p-3 text-sm text-verdict-red">
          {run.errors.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
