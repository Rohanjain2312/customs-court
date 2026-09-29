import { digitsMatched } from "./hts";
import type { Arm } from "./types";

export type Player = "human" | Arm;

export interface Round {
  exhibitId: string;
  gold: string;
  human?: { guess: string; matched: number };
  single?: { guess: string; matched: number };
  multi?: { guess: string; matched: number };
}

export interface Scoreboard {
  rounds: Round[];
}

const KEY = "customs-court:scoreboard:v1";

export function loadScoreboard(): Scoreboard {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return { rounds: [] };
    const parsed = JSON.parse(raw) as Scoreboard;
    return Array.isArray(parsed.rounds) ? parsed : { rounds: [] };
  } catch {
    return { rounds: [] };
  }
}

export function saveScoreboard(sb: Scoreboard): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(sb));
  } catch {
    /* storage can be blocked; the scoreboard still works for this page view */
  }
}

/** Records a score for one player on one exhibit. Replaces an earlier score for the same pair. */
export function recordScore(sb: Scoreboard, exhibitId: string, gold: string, player: Player, guess: string): Scoreboard {
  const matched = digitsMatched(guess, gold);
  const rounds = [...sb.rounds];
  let idx = rounds.findIndex((r) => r.exhibitId === exhibitId);
  if (idx === -1) {
    rounds.push({ exhibitId, gold });
    idx = rounds.length - 1;
  }
  const round = rounds[idx];
  if (!round) return sb;
  rounds[idx] = { ...round, gold, [player]: { guess, matched } };
  return { rounds };
}

export interface PlayerTotals {
  rounds: number;
  digits: number;
  best: number;
  last: number | null;
}

export function totals(sb: Scoreboard, player: Player): PlayerTotals {
  let rounds = 0;
  let digits = 0;
  let best = 0;
  let last: number | null = null;
  for (const r of sb.rounds) {
    const s = r[player];
    if (!s) continue;
    rounds += 1;
    digits += s.matched;
    best = Math.max(best, s.matched);
    last = s.matched;
  }
  return { rounds, digits, best, last };
}
