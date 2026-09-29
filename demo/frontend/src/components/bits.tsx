import type { ReactNode } from "react";
import type { RulingStatus } from "../lib/types";

export function fmtUsd(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "$0.00";
  return `$${n.toFixed(n >= 1 ? 2 : digits)}`;
}

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "--";
  return n.toLocaleString("en-US");
}

export function fmtSecs(s: number | null | undefined): string {
  if (s === null || s === undefined || s < 0) return "--";
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "--";
  return `${Math.round(n * 100)}%`;
}

const STATUS: Record<RulingStatus, { label: string; icon: string; cls: string }> = {
  in_force: { label: "In force", icon: "✓", cls: "border-verdict-green/70 bg-verdict-green/10 text-verdict-green" },
  modified: { label: "Modified", icon: "~", cls: "border-verdict-amber/70 bg-verdict-amber/10 text-verdict-amber" },
  revoked: { label: "Revoked", icon: "✕", cls: "border-verdict-red/70 bg-verdict-red/10 text-verdict-red" },
  unknown: { label: "Unknown", icon: "?", cls: "border-verdict-gray/60 bg-verdict-gray/10 text-verdict-gray" },
};

export function StatusBadge({ status }: { status: RulingStatus }) {
  const s = STATUS[status] ?? STATUS.unknown;
  return (
    <span className={`badge ${s.cls}`} aria-label={`Status: ${s.label}`}>
      <span aria-hidden="true">{s.icon}</span>
      {s.label}
    </span>
  );
}

export function RulingCite({ id, status }: { id: string; status: RulingStatus }) {
  return (
    <li className="flex items-center justify-between gap-2 py-0.5">
      <span className={`code text-[0.85rem] ${status === "revoked" ? "text-parchment-400 line-through" : "text-parchment-100"}`}>{id}</span>
      <StatusBadge status={status} />
    </li>
  );
}

/** A labelled 0..1 bar with its value in text, so it does not rely on colour. */
export function Meter({ value, label, tone = "brass" }: { value: number; label: string; tone?: "brass" | "green" | "red" }) {
  const v = Math.max(0, Math.min(1, value));
  const color = tone === "green" ? "bg-verdict-green" : tone === "red" ? "bg-verdict-red" : "bg-brass-400";
  return (
    <div className="flex items-center gap-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label={label}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-800 ring-1 ring-brass-800">
        <div className={`h-full ${color} transition-[width] duration-700`} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="code w-10 text-right text-[0.8rem] text-parchment-200">{Math.round(v * 100)}%</span>
    </div>
  );
}

/** Normalises a strength or confidence that may arrive as 0..1, 0..10 or 0..100. */
export function unit(n: number | null | undefined): number {
  if (n === null || n === undefined || Number.isNaN(n)) return 0;
  if (n <= 1) return n;
  if (n <= 10) return n / 10;
  return n / 100;
}

export function SectionHead({ kicker, title, right, id }: { kicker: string; title: string; right?: ReactNode; id?: string }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <div className="kicker">{kicker}</div>
        <h2 id={id} className="panel-title mt-1">
          {title}
        </h2>
      </div>
      {right}
    </div>
  );
}

export function Seal({ className = "" }: { className?: string }) {
  // Scales of justice drawn inline so there is no external asset.
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <circle cx="24" cy="24" r="22.5" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.55" />
      <circle cx="24" cy="24" r="19" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.4" strokeDasharray="1.5 2" />
      <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <path d="M24 11v24M17 36h14M13 16h22" />
        <path d="M13 16l-4.5 9h9zM35 16l-4.5 9h9z" strokeLinejoin="round" />
      </g>
      <circle cx="24" cy="11" r="1.8" fill="currentColor" />
    </svg>
  );
}
