// HTS code helpers. Codes are compared by their digits only, so "4202.22.15.00",
// "4202221500" and "4202.22.1500" all mean the same line.

export function digitsOf(code: string | null | undefined): string {
  if (!code) return "";
  const d = code.replace(/\D/g, "");
  // Chapter codes such as "1" or "Chapter 3" normalise to two digits.
  return d.length === 1 ? d.padStart(2, "0") : d;
}

/** Formats digits as 42, 4202, 4202.22, 4202.22.15, 4202.22.15.00. */
export function formatHts(code: string | null | undefined): string {
  const d = digitsOf(code);
  if (d.length <= 4) return d;
  const parts = [d.slice(0, 4), d.slice(4, 6), d.slice(6, 8), d.slice(8, 10)].filter(Boolean);
  const rest = d.slice(10);
  return parts.join(".") + (rest ? rest : "");
}

export function levelName(code: string): string {
  const n = digitsOf(code).length;
  if (n === 0) return "Schedule";
  if (n <= 2) return "Chapter";
  if (n <= 4) return "Heading";
  if (n <= 6) return "Subheading";
  if (n <= 8) return "Tariff line";
  return "Statistical line";
}

const LEVELS = [10, 8, 6, 4, 2] as const;

/** Digits matched at the 2/4/6/8/10 boundaries. 0 when even the chapter differs. */
export function digitsMatched(guess: string, gold: string): number {
  const g = digitsOf(guess);
  const t = digitsOf(gold);
  for (const n of LEVELS) {
    if (g.length >= n && t.length >= n && g.slice(0, n) === t.slice(0, n)) return n;
  }
  return 0;
}

/** Ancestor prefixes of a code at the standard levels, shortest first, including the code itself. */
export function prefixesOf(code: string): string[] {
  const d = digitsOf(code);
  const out: string[] = [];
  for (const n of [2, 4, 6, 8, 10]) {
    if (d.length >= n) out.push(d.slice(0, n));
  }
  if (d.length > 10) out.push(d);
  return out;
}

export function isPlausibleHts(input: string): boolean {
  const d = digitsOf(input);
  return d.length >= 2 && d.length <= 10 && d.length % 2 === 0;
}
