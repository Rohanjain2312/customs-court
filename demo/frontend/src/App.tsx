import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type FormEvent } from "react";
import { BrokerPanel, type BrokerPhase } from "./components/BrokerPanel";
import { CostMeter } from "./components/CostMeter";
import { ExhibitPanel } from "./components/ExhibitPanel";
import { Hearing } from "./components/Hearing";
import { HtsTree } from "./components/HtsTree";
import { RulingPanel } from "./components/RulingPanel";
import { TimeMachine, type TimeTarget } from "./components/TimeMachine";
import { Seal, SectionHead } from "./components/bits";
import { api, ApiError } from "./lib/api";
import { formatHts, isPlausibleHts } from "./lib/hts";
import { carryOverruled, initialRunState, runReducer, type FocusEntry } from "./lib/runState";
import { loadScoreboard, recordScore, saveScoreboard, type Scoreboard } from "./lib/scoreboard";
import type { Arm, Config, Exhibit, MysteryReveal, RunEvent } from "./lib/types";

function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

function ArmToggle({
  value,
  available,
  onChange,
  disabled,
}: {
  value: Arm | null;
  available: Partial<Record<Arm, boolean>>;
  onChange: (a: Arm) => void;
  disabled: boolean;
}) {
  return (
    <div role="radiogroup" aria-label="Which court hears the case" className="flex rounded border border-brass-700 bg-ink-900/80 p-0.5">
      {(["single", "multi"] as const).map((a) => {
        const on = value === a;
        const can = !!available[a];
        return (
          <button
            key={a}
            type="button"
            role="radio"
            aria-checked={on}
            data-testid={`arm-${a}`}
            disabled={disabled || !can}
            title={can ? undefined : "No recorded hearing with this court for this exhibit"}
            onClick={() => onChange(a)}
            className={`rounded px-2.5 py-1 text-[0.78rem] font-medium transition-colors disabled:cursor-not-allowed ${
              on ? "bg-brass-500 text-walnut-950" : can ? "text-parchment-200 hover:text-brass-200" : "text-parchment-600"
            }`}
          >
            {a === "single" ? "Single agent" : "Multi-agent"}
          </button>
        );
      })}
    </div>
  );
}

function SealedExhibit({
  exhibit,
  guess,
  onGuess,
  onLock,
  onSkip,
}: {
  exhibit: Exhibit;
  guess: string;
  onGuess: (v: string) => void;
  onLock: () => void;
  onSkip: () => void;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (isPlausibleHts(guess)) onLock();
  };
  return (
    <div className="flex flex-col gap-3 p-1" data-testid="sealed-exhibit">
      <div className="rounded border border-dashed border-brass-500 bg-ink-900/70 p-3">
        <div className="kicker text-brass-300">Mystery exhibit · the ruling is sealed</div>
        <p className="mt-1.5 text-[0.95rem] leading-relaxed text-parchment-100">{exhibit.description}</p>
      </div>
      <p className="text-[0.85rem] text-parchment-300">
        Beat the Broker. Enter your code first. Use the tree as a helper: click a line to fill it in. Then the court hears
        the case, and you unseal the real CBP ruling.
      </p>
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor="sealed-guess" className="sr-only">
          Your code
        </label>
        <input
          id="sealed-guess"
          data-testid="sealed-guess-input"
          className="field code text-lg"
          inputMode="numeric"
          placeholder="e.g. 6109.90"
          value={guess}
          onChange={(e) => onGuess(e.target.value.replace(/[^\d.]/g, ""))}
        />
        <button type="submit" data-testid="sealed-lock" className="btn-brass whitespace-nowrap" disabled={!isPlausibleHts(guess)}>
          Lock in
        </button>
      </form>
      <button type="button" data-testid="sealed-skip" className="self-start text-xs text-parchment-400 underline hover:text-brass-200" onClick={onSkip}>
        Skip the guess and hear the case
      </button>
    </div>
  );
}

export function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [exhibits, setExhibits] = useState<Exhibit[] | null>(null);
  const [exhibitsError, setExhibitsError] = useState<string | null>(null);
  const [run, dispatch] = useReducer(runReducer, undefined, () => initialRunState());
  const [base, setBase] = useState<Exhibit | null>(null);
  const [heard, setHeard] = useState<Exhibit | null>(null);
  const [liveArm, setLiveArm] = useState<Arm>("single");
  const [liveDescription, setLiveDescription] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [phase, setPhase] = useState<BrokerPhase>("idle");
  const [guess, setGuess] = useState("");
  const [lockedGuess, setLockedGuess] = useState<string | null>(null);
  const [reveal, setReveal] = useState<MysteryReveal | null>(null);
  const [revealError, setRevealError] = useState<string | null>(null);
  const [scoreboard, setScoreboard] = useState<Scoreboard>(() => loadScoreboard());

  const [objectionNote, setObjectionNote] = useState<string | null>(null);
  const [overruledCode, setOverruledCode] = useState<string | null>(null);
  const [pickedCode, setPickedCode] = useState<string | null>(null);
  const [tmTarget, setTmTarget] = useState<TimeTarget | null>(null);
  const [treeReset, setTreeReset] = useState(0);
  const rulingRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    api
      .config()
      .then(setConfig)
      .catch((e: unknown) => setBootError(e instanceof Error ? e.message : "The court backend did not answer."));
    api
      .exhibits()
      .then(setExhibits)
      .catch((e: unknown) => setExhibitsError(e instanceof Error ? e.message : "The docket could not be loaded."));
  }, []);

  useEffect(() => saveScoreboard(scoreboard), [scoreboard]);

  const byId = useMemo(() => new Map((exhibits ?? []).map((e) => [e.exhibit_id, e])), [exhibits]);
  const docket = useMemo(() => (exhibits ?? []).filter((e) => e.kind !== "objection" && !(e.agent === "multi" && e.arms?.single)), [exhibits]);
  const pairs = useMemo(() => {
    const out: Partial<Record<Arm, Exhibit>> = {};
    if (!base?.arms) return out;
    for (const a of ["single", "multi"] as const) {
      const id = base.arms[a];
      const ex = id ? byId.get(id) : undefined;
      if (ex) out[a] = ex;
    }
    return out;
  }, [base, byId]);

  const sink = useCallback((ev: RunEvent) => dispatch({ type: "event", ev, wall: performance.now() }), []);

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
  };

  const hear = useCallback(
    (ex: Exhibit, carried?: Record<string, FocusEntry>) => {
      stop();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: "reset", status: "running", carried, description: ex.description, arm: ex.agent });
      setHeard(ex);
      if (!carried) setTreeReset((n) => n + 1);
      api.replay(ex.exhibit_id, sink, ctrl.signal).catch((e: unknown) => {
        if (!isAbort(e)) dispatch({ type: "fail", message: e instanceof Error ? e.message : "The replay failed." });
      });
    },
    [sink],
  );

  const hearLive = useCallback(
    (description: string, carried?: Record<string, FocusEntry>) => {
      stop();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: "reset", status: "running", carried, description, arm: liveArm });
      setHeard(null);
      setLiveDescription(description);
      if (!carried) setTreeReset((n) => n + 1);
      const liveSink = (ev: RunEvent) => {
        sink(ev);
        if (ev.type === "done") void api.config().then(setConfig).catch(() => undefined);
      };
      api.classify(description, liveArm, liveSink, ctrl.signal).catch((e: unknown) => {
        if (!isAbort(e)) dispatch({ type: "fail", message: e instanceof ApiError || e instanceof Error ? e.message : "The hearing failed." });
      });
    },
    [liveArm, sink],
  );

  // When a hearing ends: advance Beat the Broker, score a late arm, point the time machine at the ruling.
  const lastDone = useRef<number>(-1);
  useEffect(() => {
    if (run.status !== "done" || lastDone.current === run.epoch) return;
    lastDone.current = run.epoch;
    if (phase === "hearing") setPhase("ready");
    if (phase === "revealed" && reveal && heard && run.ruling?.hts10) {
      setScoreboard((sb) => recordScore(sb, reveal.exhibit_id, reveal.gold_code, heard.agent, run.ruling?.hts10 ?? ""));
    }
    if (run.ruling?.hts10 && !run.ruling.abstain && !heard?.timemachine) {
      setTmTarget({ code: run.ruling.hts10, seq: ++seq.current });
    }
  }, [run.status, run.epoch, run.ruling, phase, reveal, heard]);

  const pickExhibit = (ex: Exhibit) => {
    setBase(ex);
    setObjectionNote(null);
    setOverruledCode(null);
    setReveal(null);
    setRevealError(null);
    setGuess("");
    setLockedGuess(null);
    setLiveDescription(null);
    if (ex.timemachine) setTmTarget({ code: ex.timemachine.code, rev: ex.timemachine.rev_a, seq: ++seq.current });
    if (ex.mystery) {
      stop();
      dispatch({ type: "reset", status: "idle" });
      setHeard(ex);
      setPhase("guessing");
      setTreeReset((n) => n + 1);
    } else {
      setPhase("idle");
      hear(ex);
    }
  };

  const lockGuess = () => {
    if (!heard || !isPlausibleHts(guess)) return;
    setLockedGuess(guess);
    setPhase("hearing");
    hear(heard);
  };

  const skipGuess = () => {
    if (!heard) return;
    setLockedGuess(null);
    setPhase("hearing");
    hear(heard);
  };

  const doReveal = async () => {
    if (!base) return;
    setRevealError(null);
    try {
      const r = await api.reveal(base.exhibit_id);
      setReveal(r);
      setPhase("revealed");
      setScoreboard((sb) => {
        let next = sb;
        if (lockedGuess) next = recordScore(next, r.exhibit_id, r.gold_code, "human", lockedGuess);
        if (run.ruling?.hts10 && heard) next = recordScore(next, r.exhibit_id, r.gold_code, heard.agent, run.ruling.hts10);
        return next;
      });
    } catch (e) {
      setRevealError(e instanceof Error ? e.message : "The ruling could not be unsealed.");
    }
  };

  const switchArm = (a: Arm) => {
    if (!base) {
      setLiveArm(a);
      return;
    }
    const target = pairs[a];
    if (!target) return;
    if (phase === "guessing") {
      setHeard(target);
      return;
    }
    setObjectionNote(null);
    setOverruledCode(null);
    hear(target);
  };

  const objection = async (fact: string): Promise<string | null> => {
    const prior = run.ruling?.hts10 ?? null;
    const carried = carryOverruled(run);
    try {
      const res = await api.objection(base?.exhibit_id ?? "", fact, base?.description ?? liveDescription ?? "");
      setOverruledCode(prior);
      if (res.mode === "replay") {
        const ex = byId.get(res.exhibit_id);
        if (!ex) return "The recorded objection is missing from the docket.";
        setObjectionNote(
          `Objection: "${res.fact_change}" The court reheard the case with that fact.` +
            (res.placeholder ? " This rehearing is a scripted placeholder, not a model run." : ""),
        );
        hear(ex, carried);
      } else {
        setObjectionNote(`Objection: "${res.fact_change}" The court is rehearing the case live.`);
        hearLive(res.description, carried);
      }
      window.setTimeout(() => document.getElementById("hearing-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      return null;
    } catch (e) {
      return e instanceof Error ? e.message : "The objection could not be filed.";
    }
  };

  const onTreePick = (code: string) => {
    setPickedCode(code);
    if (phase === "guessing") setGuess(formatHts(code));
  };

  const live = !!config?.live;
  const running = run.status === "running";
  const recordedFact = base && !live ? byId.get(base.objections[0] ?? "")?.fact_change ?? null : null;
  const canObjectHere = live || (!!recordedFact && heard?.kind !== "objection");
  const reference = heard?.gold_code
    ? {
        code: heard.gold_code,
        label: heard.source.dataset.startsWith("tests/") ? "Expected code (test fixture)" : "Code in the CBP ruling",
      }
    : reveal
      ? { code: reveal.gold_code, label: "Code in the CBP ruling" }
      : null;
  const armValue: Arm | null = heard ? heard.agent : base ? null : liveArm;
  const armAvailable: Partial<Record<Arm, boolean>> = base
    ? { single: !!pairs.single, multi: !!pairs.multi }
    : { single: live, multi: live };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-brass-800/80 bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1920px] flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
          <Seal className="h-11 w-11 shrink-0 text-brass-300" />
          <div className="min-w-0">
            <h1 className="font-display text-[2rem] font-semibold leading-none tracking-wide text-brass-200">Customs Court</h1>
            <div className="kicker mt-1">TariffAgent argues tariff codes on the record, grounded in CBP rulings</div>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {config ? (
              <span
                data-testid="mode-badge"
                data-mode={config.mode}
                className={`badge px-2 py-1 ${config.live ? "border-verdict-green/70 text-verdict-green" : "border-brass-500 text-brass-300"}`}
                title={config.live ? `Live mode. Session cap $${config.session_cap_usd.toFixed(2)}.` : config.timing_note}
              >
                {config.live ? "Live court" : "Replay · recorded hearings"}
              </span>
            ) : null}
            <ArmToggle value={armValue} available={armAvailable} onChange={switchArm} disabled={running && !base} />
          </div>
        </div>
        {config && !config.live ? (
          <div className="border-t border-brass-900/70 bg-walnut-950/70 px-4 py-1 text-center text-[0.72rem] text-parchment-400" data-testid="timing-note">
            {config.timing_note}
          </div>
        ) : null}
      </header>

      {bootError ? (
        <div role="alert" className="mx-4 mt-4 rounded border border-verdict-red/60 bg-verdict-red/10 p-3 text-verdict-red">
          The court backend did not answer: {bootError}. Start it with <code className="code">make replay</code>.
        </div>
      ) : null}

      <main className="mx-auto max-w-[1920px] px-4 pb-10 pt-4">
        <div className="grid gap-4 lg:h-[calc(100vh-7rem)] lg:min-h-[36rem] lg:grid-cols-[17.5rem_minmax(0,1fr)_minmax(22rem,27rem)]">
          <section className="panel flex min-h-0 flex-col p-3" aria-labelledby="exhibits-title" data-testid="exhibit-panel">
            <SectionHead kicker="I · Bring an exhibit" title="The Docket" id="exhibits-title" />
            <div className="min-h-0 flex-1">
              <ExhibitPanel
                exhibits={exhibits ? docket : null}
                exhibitsError={exhibitsError}
                live={live}
                liveReason={config?.live_reason ?? ""}
                activeId={base?.exhibit_id ?? null}
                busy={running}
                onPick={pickExhibit}
                onSubmitTyped={(d) => {
                  setBase(null);
                  setPhase("idle");
                  setObjectionNote(null);
                  setOverruledCode(null);
                  hearLive(d);
                }}
                onDescribePhoto={async (img) => (await api.describePhoto(img)).description}
              />
            </div>
          </section>

          <section className="panel flex min-h-[26rem] flex-col p-3" aria-labelledby="tree-title" data-testid="tree-panel">
            <SectionHead
              kicker="The schedule, as the court walks it"
              title="Harmonized Tariff Schedule"
              id="tree-title"
              right={<span className="text-[0.72rem] text-parchment-500">Hover a dimmed line to see why it was rejected</span>}
            />
            <div className="min-h-0 flex-1 overflow-hidden rounded border border-brass-900/80">
              <HtsTree
                api={api}
                focus={run.focus}
                follow={run.lastFocus}
                resetKey={treeReset}
                onPick={onTreePick}
                pickHint={phase === "guessing" ? "Click a line to use it as your guess" : null}
              />
            </div>
          </section>

          <section id="hearing-panel" className="panel flex min-h-0 flex-col p-3" aria-labelledby="hearing-title" data-testid="hearing-panel">
            <SectionHead
              kicker="II · In session"
              title="The Hearing"
              id="hearing-title"
              right={
                heard || liveDescription ? (
                  <span className="badge border-ink-600 text-parchment-300">{(heard?.agent ?? run.arm) === "multi" ? "Multi-agent" : "Single agent"}</span>
                ) : null
              }
            />
            {(heard && phase !== "guessing") || liveDescription ? (
              <div className="mb-3 rounded border border-brass-800/70 bg-ink-900/60 p-2.5 text-[0.85rem]" data-testid="exhibit-card">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="kicker">{heard ? `Exhibit · ${heard.title}` : "Exhibit · typed by you"}</span>
                  {heard?.kind === "objection" ? <span className="badge border-verdict-red/60 text-verdict-red">Rehearing</span> : null}
                </div>
                <p className="mt-1 line-clamp-4 whitespace-pre-line text-parchment-100">
                  {(heard?.description ?? liveDescription ?? "").split("\n\nCorrection to the facts")[0]}
                </p>
                {heard?.kind === "objection" && heard.fact_change ? (
                  <p className="mt-1.5 text-[0.85rem] text-verdict-red" data-testid="objection-fact">
                    Objection sustained for the rehearing: {heard.fact_change}
                  </p>
                ) : null}
                {heard?.placeholder ? (
                  <p className="mt-1.5 text-[0.75rem] text-verdict-amber" data-testid="placeholder-note">
                    Placeholder: {heard.placeholder_note}
                  </p>
                ) : null}
                {heard?.note ? <p className="mt-1.5 text-[0.75rem] text-parchment-400">Note: {heard.note}</p> : null}
                {heard ? (
                  <p className="mt-1 text-[0.7rem] text-parchment-500">
                    Recorded run {heard.source.run_id} · {Object.values(heard.models).filter(Boolean).join(", ")}
                  </p>
                ) : null}
              </div>
            ) : null}
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto pr-1">
              <Hearing
                run={run}
                onJumpToRuling={() => rulingRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
                idle={
                  phase === "guessing" && heard ? (
                    <SealedExhibit exhibit={heard} guess={guess} onGuess={setGuess} onLock={lockGuess} onSkip={skipGuess} />
                  ) : undefined
                }
              />
            </div>
          </section>
        </div>

        <div ref={rulingRef} className="mt-4 scroll-mt-28">
          <RulingPanel
            run={run}
            live={live}
            recordedFact={canObjectHere ? recordedFact : null}
            objectionNote={objectionNote}
            overruledCode={overruledCode}
            reference={base?.mystery && !reveal ? null : reference}
            onObjection={objection}
          />
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-3">
          <BrokerPanel
            exhibit={base}
            phase={phase}
            guess={guess}
            lockedGuess={lockedGuess}
            agentCode={phase === "guessing" ? null : run.ruling?.hts10 ?? null}
            agentArm={heard?.agent ?? null}
            reveal={reveal}
            revealError={revealError}
            scoreboard={scoreboard}
            onGuessChange={setGuess}
            onLockGuess={lockGuess}
            onReveal={() => void doReveal()}
            onResetScores={() => setScoreboard({ rounds: [] })}
            otherArmAvailable={!!(pairs.single && pairs.multi)}
          />
          <TimeMachine api={api} target={tmTarget} pickedCode={pickedCode} />
          <CostMeter run={run} config={config} exhibit={heard} pairs={pairs} onSwitchArm={switchArm} busy={false} />
        </div>

        <footer className="mt-8 border-t border-brass-900/70 pt-4 text-[0.75rem] leading-relaxed text-parchment-500">
          <p>
            Customs Court is the demo of TariffAgent. Replays are recorded runs from the project's eval harness, streamed
            again with compressed timing. Hearings marked placeholder use a scripted stand-in model and are there only
            until a real run is recorded. Not legal advice. A licensed customs broker or a binding CBP ruling decides real
            entries.
          </p>
        </footer>
      </main>
    </div>
  );
}
