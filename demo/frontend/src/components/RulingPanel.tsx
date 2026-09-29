import { useState, type FormEvent } from "react";
import { digitsMatched, formatHts, levelName } from "../lib/hts";
import type { RunState } from "../lib/runState";
import { Meter, RulingCite, SectionHead, unit } from "./bits";

interface Props {
  run: RunState;
  live: boolean;
  /** The fact change of the recorded objection for this exhibit (replay mode). */
  recordedFact: string | null;
  objectionNote: string | null;
  overruledCode: string | null;
  reference: { code: string; label: string } | null;
  onObjection: (factChange: string) => Promise<string | null>;
}

export function RulingPanel({ run, live, recordedFact, objectionNote, overruledCode, reference, onObjection }: Props) {
  const canObject = live || !!recordedFact;
  const [open, setOpen] = useState(false);
  const [fact, setFact] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const c = run.ruling;
  const running = run.status === "running";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const text = (live ? fact : recordedFact ?? "").trim();
    if (!text) {
      setErr("State the one fact you want to change.");
      return;
    }
    setBusy(true);
    setErr(null);
    const problem = await onObjection(text);
    setBusy(false);
    if (problem) setErr(problem);
    else {
      setOpen(false);
      setFact("");
    }
  };

  return (
    <section data-testid="ruling-panel" className="panel p-4" aria-labelledby="ruling-title">
      <SectionHead
        kicker="III · Judgment"
        title="The Ruling"
        id="ruling-title"
        right={
          c && !running ? (
            <button
              type="button"
              data-testid="objection-button"
              className="btn-ghost border-verdict-red/60 text-verdict-red hover:border-verdict-red"
              onClick={() => {
                setOpen((o) => !o);
                setErr(null);
              }}
              disabled={!canObject}
              aria-expanded={open}
              aria-controls="objection-form"
              title={canObject ? "Change one fact and hear the case again" : "No objection is on file for this exhibit. Replay mode can only rehear recorded objections."}
            >
              <span aria-hidden="true">✋</span> Objection
            </button>
          ) : null
        }
      />

      {objectionNote ? (
        <div className="mb-3 rounded border border-verdict-amber/50 bg-verdict-amber/10 px-3 py-2 text-sm text-verdict-amber" role="status">
          {objectionNote}
        </div>
      ) : null}

      {open ? (
        <form id="objection-form" onSubmit={submit} className="mb-4 rounded border border-verdict-red/40 bg-ink-900/70 p-3">
          <label htmlFor="objection-input" className="kicker mb-1 block text-verdict-red">
            Objection. Change one fact.
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id="objection-input"
              data-testid="objection-input"
              className="field"
              placeholder="The strap is leather, not plastic."
              value={live ? fact : recordedFact ?? ""}
              onChange={(e) => setFact(e.target.value)}
              readOnly={!live}
              disabled={busy}
              autoFocus
            />
            <button type="submit" data-testid="objection-submit" className="btn-brass whitespace-nowrap" disabled={busy}>
              {busy ? "Filing…" : "Rehear the case"}
            </button>
          </div>
          {err ? (
            <p role="alert" className="mt-2 text-sm text-verdict-red">
              {err}
            </p>
          ) : (
            <p className="mt-2 text-xs text-parchment-400">
              {live
                ? "The court reruns the hearing with this fact changed. The old ruling stays marked on the tree as overruled."
                : "Replay mode plays the objection recorded for this exhibit. The old ruling stays marked on the tree as overruled."}
            </p>
          )}
        </form>
      ) : null}

      {!c ? (
        <p className="text-parchment-400">
          {running ? "The hearing is in session. The ruling appears here when the bench decides." : "No ruling yet."}
        </p>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
          <div className="space-y-4">
            <div>
              <div className="kicker">{c.abstain ? "The court abstains" : `${levelName(c.hts10)} · HTSUS`}</div>
              <div
                data-testid="final-code"
                className={`code mt-1 text-[clamp(2.2rem,4.2vw,3.6rem)] font-semibold leading-none ${c.abstain ? "text-parchment-400" : "text-brass-300 drop-shadow-[0_0_18px_rgba(240,210,127,0.35)]"}`}
              >
                {c.abstain ? "No ruling" : formatHts(c.hts10)}
              </div>
              {reference && !c.abstain ? (
                <div className="mt-2 text-sm text-parchment-300" data-testid="reference-code">
                  {reference.label}: <span className="code text-parchment-100">{formatHts(reference.code)}</span>
                  <span className="ml-2 text-parchment-400">· {digitsMatched(c.hts10, reference.code)} of 10 digits match</span>
                </div>
              ) : null}
              {overruledCode && overruledCode !== c.hts10 ? (
                <div className="mt-2 text-sm text-parchment-300">
                  Overrules <span className="code text-[#d49a88] line-through">{formatHts(overruledCode)}</span>
                </div>
              ) : null}
            </div>

            <div>
              <div className="kicker mb-1">Confidence</div>
              <Meter value={unit(c.confidence)} label="Confidence in the ruling" tone={unit(c.confidence) < 0.5 ? "red" : "green"} />
            </div>

            <div>
              <div className="kicker mb-2">Path through the General Rules of Interpretation</div>
              <ol className="flex flex-wrap items-center gap-1.5" aria-label="GRI path">
                {c.gri_path.map((step, i) => {
                  const deciding = c.deciding_gri && step.toLowerCase().startsWith(c.deciding_gri.toLowerCase());
                  return (
                    <li key={`${i}-${step}`} className="flex items-center gap-1.5">
                      <span
                        className={`rounded border px-2 py-1 text-[0.82rem] ${
                          deciding ? "border-brass-300 bg-brass-400/15 text-brass-100" : "border-brass-800 bg-ink-900/60 text-parchment-200"
                        }`}
                      >
                        <span className="mr-1 font-mono text-[0.7rem] text-parchment-500">{i + 1}</span>
                        {step}
                        {deciding ? <span className="ml-1.5 badge border-brass-300 text-brass-200">Deciding</span> : null}
                      </span>
                      {i < c.gri_path.length - 1 ? (
                        <span aria-hidden="true" className="text-brass-600">
                          →
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </div>

            {c.rationale ? <p className="text-[0.92rem] leading-relaxed text-parchment-200">{c.rationale}</p> : null}
          </div>

          <div className="space-y-4">
            <div>
              <div className="kicker mb-1">Citations</div>
              {c.cited_rulings.length ? (
                <ul className="divide-y divide-brass-800/60">
                  {c.cited_rulings.map((r) => (
                    <RulingCite key={r.id} id={r.id} status={r.status} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-parchment-500">No rulings cited.</p>
              )}
            </div>

            <div>
              <div className="kicker mb-1">Rejected alternatives</div>
              {c.rejected_alternatives.length ? (
                <ul className="space-y-1 text-[0.85rem]">
                  {c.rejected_alternatives.map((r) => (
                    <li key={r.code} className="flex gap-2">
                      <span className="code shrink-0 text-parchment-400 line-through decoration-verdict-red/70">{formatHts(r.code)}</span>
                      <span className="text-parchment-200">{r.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-parchment-500">None listed.</p>
              )}
            </div>

            <div className="rounded border border-verdict-amber/40 bg-verdict-amber/5 p-3">
              <div className="kicker mb-1 text-verdict-amber">What facts would change this</div>
              {c.missing_facts.length ? (
                <ul className="list-disc space-y-0.5 pl-4 text-[0.85rem] text-parchment-100 marker:text-verdict-amber">
                  {c.missing_facts.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-parchment-400">The court found no missing fact that would move the code.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
