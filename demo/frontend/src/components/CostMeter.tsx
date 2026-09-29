import type { RunState } from "../lib/runState";
import type { Arm, Config, Exhibit } from "../lib/types";
import { fmtInt, fmtPct, fmtSecs, fmtUsd, Meter, SectionHead } from "./bits";

interface Props {
  run: RunState;
  config: Config | null;
  exhibit: Exhibit | null;
  pairs: Partial<Record<Arm, Exhibit>>;
  onSwitchArm: (arm: Arm) => void;
  busy: boolean;
}

function Row({ label, value, testid }: { label: string; value: string; testid?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-t border-brass-900/60 py-1 text-[0.85rem]">
      <dt className="text-parchment-400">{label}</dt>
      <dd className="code text-parchment-100" data-testid={testid}>
        {value}
      </dd>
    </div>
  );
}

export function CostMeter({ run, config, exhibit, pairs, onSwitchArm, busy }: Props) {
  const live = config?.mode === "live" && !exhibit;
  const c = run.cost;
  const tokens = c ? c.input_tokens + c.output_tokens + c.cache_read_tokens + c.cache_write_tokens : null;
  const both = !!(pairs.single && pairs.multi);
  const placeholder = exhibit?.placeholder;

  return (
    <section className="panel flex flex-col p-4" aria-labelledby="cost-title" data-testid="cost-meter">
      <SectionHead
        kicker="VI · Court costs"
        title="Cost Meter"
        id="cost-title"
        right={
          <span className={`badge ${live ? "border-verdict-green/70 text-verdict-green" : "border-brass-600 text-brass-300"}`}>
            {live ? "Live" : "Recorded"}
          </span>
        }
      />
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="kicker">{live ? "This hearing" : "Recorded cost of this hearing"}</div>
          <div data-testid="cost-usd" className="code text-[2.4rem] font-semibold leading-none text-brass-300">
            {c ? fmtUsd(c.usd) : "$0.0000"}
          </div>
        </div>
        <div className="w-40">
          <div className="kicker mb-1">Cache hit rate</div>
          <Meter value={c?.cache_hit_rate ?? 0} label="Share of input tokens read from the prompt cache" tone="green" />
        </div>
      </div>
      {placeholder ? (
        <p className="mt-2 text-[0.78rem] text-verdict-amber">Placeholder hearing. The model was scripted, so these numbers are not real costs.</p>
      ) : null}

      <dl className="mt-3">
        <Row label="Model calls" value={fmtInt(c?.calls)} />
        <Row label="Tokens, all" value={fmtInt(tokens)} testid="cost-tokens" />
        <Row label="Input, uncached" value={fmtInt(c?.input_tokens)} />
        <Row label="Cache reads" value={fmtInt(c?.cache_read_tokens)} />
        <Row label="Cache writes" value={fmtInt(c?.cache_write_tokens)} />
        <Row label="Output" value={fmtInt(c?.output_tokens)} />
        {exhibit && !live ? (
          <Row
            label="Recorded API time"
            value={exhibit.recorded.api_latency_s != null ? fmtSecs(exhibit.recorded.api_latency_s) : "--"}
          />
        ) : null}
      </dl>

      {both ? (
        <div className="mt-3 rounded border border-brass-800 bg-ink-900/60 p-2.5" data-testid="arm-compare">
          <div className="kicker mb-2">Same exhibit, both courts</div>
          <table className="w-full text-[0.82rem]">
            <thead>
              <tr className="text-left text-[0.68rem] uppercase tracking-wider text-parchment-500">
                <th className="font-medium">Court</th>
                <th className="font-medium">Cost</th>
                <th className="font-medium">Tokens</th>
                <th className="font-medium">Cache</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(["single", "multi"] as const).map((a) => {
                const ex = pairs[a];
                if (!ex) return null;
                const on = exhibit?.exhibit_id === ex.exhibit_id;
                return (
                  <tr key={a} className={`border-t border-brass-900/60 ${on ? "text-brass-200" : "text-parchment-200"}`}>
                    <td className="py-1">
                      {a === "multi" ? "Multi-agent" : "Single agent"}
                      {ex.placeholder ? <span className="ml-1 text-[0.7rem] text-verdict-amber">placeholder</span> : null}
                    </td>
                    <td className="code">{fmtUsd(ex.recorded.usd)}</td>
                    <td className="code">{fmtInt(ex.recorded.tokens)}</td>
                    <td className="code">{fmtPct(ex.recorded.cache_hit_rate)}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        data-testid={`cost-switch-${a}`}
                        className="text-xs text-brass-300 underline disabled:no-underline disabled:opacity-50"
                        disabled={on || busy}
                        onClick={() => onSwitchArm(a)}
                      >
                        {on ? "showing" : "hear it"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : exhibit ? (
        <p className="mt-3 text-[0.78rem] text-parchment-500">
          Only one court has heard this exhibit so far, so there is no single vs multi-agent comparison for it.
        </p>
      ) : null}

      {config?.mode === "live" ? (
        <div className="mt-3">
          <div className="kicker mb-1">Session budget</div>
          <Meter value={config.session_spent_usd / Math.max(0.01, config.session_cap_usd)} label="Share of this session's live budget used" tone="brass" />
          <div className="mt-1 text-[0.75rem] text-parchment-400">
            {fmtUsd(config.session_spent_usd)} of {fmtUsd(config.session_cap_usd, 2)} used. Live hearings stop at the cap.
          </div>
        </div>
      ) : (
        <p className="mt-3 text-[0.75rem] text-parchment-500">Replay mode spends nothing. Numbers are what the recorded run cost.</p>
      )}
    </section>
  );
}
