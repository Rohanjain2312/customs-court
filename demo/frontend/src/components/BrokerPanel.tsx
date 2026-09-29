import type { FormEvent } from "react";
import { digitsMatched, formatHts, isPlausibleHts } from "../lib/hts";
import { totals, type Player, type Scoreboard } from "../lib/scoreboard";
import type { Arm, Exhibit, MysteryReveal } from "../lib/types";
import { SectionHead } from "./bits";

export type BrokerPhase = "idle" | "guessing" | "hearing" | "ready" | "revealed";

interface Props {
  exhibit: Exhibit | null;
  phase: BrokerPhase;
  guess: string;
  lockedGuess: string | null;
  agentCode: string | null;
  agentArm: Arm | null;
  reveal: MysteryReveal | null;
  revealError: string | null;
  scoreboard: Scoreboard;
  onGuessChange: (v: string) => void;
  onLockGuess: () => void;
  onReveal: () => void;
  onResetScores: () => void;
  otherArmAvailable: boolean;
}

const PLAYERS: { id: Player; label: string }[] = [
  { id: "human", label: "You" },
  { id: "single", label: "Single agent" },
  { id: "multi", label: "Multi-agent" },
];

function DigitsBar({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center gap-1" aria-label={`${n} of 10 digits matched`}>
      {[2, 4, 6, 8, 10].map((lvl) => (
        <span key={lvl} className={`h-2 w-3 rounded-sm ${n >= lvl ? "bg-brass-300" : "bg-ink-700 ring-1 ring-brass-800"}`} aria-hidden="true" />
      ))}
      <span className="code ml-1 text-[0.8rem] text-parchment-100">{n}/10</span>
    </span>
  );
}

export function BrokerPanel(p: Props) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (isPlausibleHts(p.guess)) p.onLockGuess();
  };
  const active = !!p.exhibit?.mystery;

  return (
    <section className="panel flex flex-col p-4" aria-labelledby="broker-title">
      <SectionHead kicker="IV · Side game" title="Beat the Broker" id="broker-title" />

      {!active ? (
        <p className="text-[0.88rem] text-parchment-300">
          Pick a mystery exhibit from the docket. Enter your code before the court hears it. Then see who matched the real CBP ruling.
        </p>
      ) : (
        <div className="space-y-3">
          <p className="text-[0.85rem] text-parchment-300">
            <span className="font-semibold text-parchment-100">{p.exhibit?.title}.</span> {p.exhibit?.description}
          </p>

          <form onSubmit={submit} className="space-y-1.5">
            <label htmlFor="broker-guess" className="kicker block">
              Your code
            </label>
            <div className="flex gap-2">
              <input
                id="broker-guess"
                data-testid="broker-guess-input"
                className="field code text-lg"
                inputMode="numeric"
                placeholder="4202.92"
                value={p.lockedGuess ?? p.guess}
                onChange={(e) => p.onGuessChange(e.target.value.replace(/[^\d.]/g, ""))}
                disabled={p.phase !== "guessing"}
                aria-describedby="broker-help"
              />
              <button type="submit" data-testid="broker-submit" className="btn-brass whitespace-nowrap" disabled={p.phase !== "guessing" || !isPlausibleHts(p.guess)}>
                Lock in
              </button>
            </div>
            <p id="broker-help" className="text-xs text-parchment-500">
              {p.phase === "guessing"
                ? "Type 2 to 10 digits, or click a node on the tree to fill it in. The court waits for you."
                : `Locked: ${p.lockedGuess ? formatHts(p.lockedGuess) : "none"}.`}
            </p>
          </form>

          <div className="flex items-center justify-between gap-2 rounded border border-brass-800 bg-ink-900/60 px-3 py-2 text-sm">
            <span className="text-parchment-400">Court's answer {p.agentArm ? `(${p.agentArm === "multi" ? "multi-agent" : "single agent"})` : ""}</span>
            <span className="code text-brass-200">
              {p.agentCode ? formatHts(p.agentCode) : p.phase === "hearing" ? "In session…" : "Pending"}
            </span>
          </div>

          <button
            type="button"
            data-testid="broker-reveal"
            className="btn-brass w-full"
            onClick={p.onReveal}
            disabled={p.phase !== "ready" && p.phase !== "revealed"}
          >
            {p.phase === "revealed" ? "Ruling unsealed" : "Unseal the real ruling"}
          </button>
          {p.revealError ? (
            <p role="alert" className="text-sm text-verdict-red">
              {p.revealError}
            </p>
          ) : null}

          {p.reveal ? (
            <div className="animate-rise rounded border border-brass-400 bg-brass-500/10 p-3" data-testid="broker-result">
              <div className="flex items-baseline justify-between gap-2">
                <span className="kicker text-brass-300">
                  {p.reveal.ruling_id ? `CBP ruling ${p.reveal.ruling_id}` : "The CBP ruling's code"}
                </span>
                <span className="text-xs text-parchment-400">{p.reveal.ruling_date}</span>
              </div>
              <div className="code mt-1 text-3xl font-semibold text-brass-200">{formatHts(p.reveal.gold_code)}</div>
              {p.reveal.reference_excerpt ? (
                <blockquote className="scroll-thin mt-2 max-h-28 overflow-y-auto border-l-2 border-brass-600 pl-2 text-[0.8rem] italic text-parchment-200">
                  {p.reveal.reference_excerpt}
                </blockquote>
              ) : null}
              {!p.reveal.ruling_id ? (
                <p className="mt-1 text-[0.72rem] text-parchment-500">
                  Source: {p.reveal.dataset || "dataset"}. The ATLAS dataset stores the ruling's code and a summary of the
                  ruling, not its number.
                </p>
              ) : null}
              <dl className="mt-3 space-y-1 text-sm">
                {p.lockedGuess ? (
                  <div className="flex items-center justify-between">
                    <dt className="text-parchment-300">You</dt>
                    <dd>
                      <DigitsBar n={digitsMatched(p.lockedGuess, p.reveal.gold_code)} />
                    </dd>
                  </div>
                ) : null}
                {p.agentCode && p.agentArm ? (
                  <div className="flex items-center justify-between">
                    <dt className="text-parchment-300">{p.agentArm === "multi" ? "Multi-agent" : "Single agent"}</dt>
                    <dd>
                      <DigitsBar n={digitsMatched(p.agentCode, p.reveal.gold_code)} />
                    </dd>
                  </div>
                ) : null}
              </dl>
              {p.otherArmAvailable ? (
                <p className="mt-2 text-xs text-parchment-400">Switch the agent in the header to hear the other one on the same exhibit.</p>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      <div data-testid="scoreboard" className="mt-4 border-t border-brass-800/80 pt-3" aria-label="Scoreboard">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="kicker">Scoreboard · this session</span>
          <button type="button" className="text-xs text-parchment-500 underline hover:text-parchment-300" onClick={p.onResetScores}>
            Reset
          </button>
        </div>
        <table className="w-full text-[0.85rem]">
          <thead>
            <tr className="text-left text-[0.7rem] uppercase tracking-wider text-parchment-500">
              <th className="font-medium">Player</th>
              <th className="font-medium">Rounds</th>
              <th className="font-medium">Last</th>
              <th className="text-right font-medium">Digits</th>
            </tr>
          </thead>
          <tbody>
            {PLAYERS.map((pl) => {
              const t = totals(p.scoreboard, pl.id);
              return (
                <tr key={pl.id} data-player={pl.id} className="border-t border-brass-900/60">
                  <td className="py-1 text-parchment-100">{pl.label}</td>
                  <td className="code text-parchment-300">{t.rounds}</td>
                  <td className="code text-parchment-300">{t.last === null ? "--" : `${t.last}/10`}</td>
                  <td className="code text-right text-brass-200">{t.digits}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
