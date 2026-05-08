// Display helpers for the Brief component. Pure functions, no React.

export function fr(n: number): string {
  return Math.round(n).toLocaleString("fr-FR").replace(/ | /g, " ");
}

export function eur(n: number): string {
  return `${fr(n)}€`;
}

export function eurShort(n: number): string {
  if (Math.abs(n) >= 10000) return `${(n / 1000).toFixed(1).replace(".", ",")}k€`;
  return eur(n);
}

export function pct(n: number, digits = 0): string {
  return `${n.toFixed(digits).replace(".", ",")} %`;
}

export function ratio(n: number): string {
  return `×${n.toFixed(1).replace(".", ",")}`;
}

export function deltaLabel(delta_pct: number | undefined): string | null {
  if (delta_pct === undefined || delta_pct === null) return null;
  const sign = delta_pct > 0 ? "+" : "";
  return `${sign}${delta_pct.toFixed(0)} %`;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");
}

export function encaissementBucket(pctValue: number): "green" | "amber" | "red" {
  if (pctValue >= 70) return "green";
  if (pctValue >= 50) return "amber";
  return "red";
}

export function cplBucket(cpl: number | undefined): "h-good" | "h-mid" | "h-bad" | "h-empty" {
  if (cpl === undefined || cpl === null) return "h-empty";
  if (cpl < 3) return "h-good";
  if (cpl < 6) return "h-mid";
  return "h-bad";
}

export function winsBucket(wins: number | undefined): "h-good" | "h-mid" | "h-bad" | "h-empty" {
  if (!wins || wins === 0) return "h-empty";
  if (wins >= 2) return "h-good";
  return "h-mid";
}

export function cpsBucket(cps: number | undefined): "h-good" | "h-mid" | "h-bad" | "h-empty" {
  if (cps === undefined || cps === null) return "h-empty";
  if (cps < 50) return "h-good";
  if (cps < 100) return "h-mid";
  return "h-bad";
}

export function formatGeneratedAt(iso: string): string {
  const d = new Date(iso);
  const diffMin = Math.max(0, Math.round((Date.now() - d.getTime()) / 60000));
  if (diffMin < 60) return `Généré il y a ${diffMin} min`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `Généré il y a ${diffH}h`;
  return `Généré le ${d.toLocaleDateString("fr-FR")}`;
}

export function formatPeriod(start: string, end: string): string {
  const s = new Date(start);
  const e = new Date(end);
  const months = [
    "jan", "fév", "mar", "avr", "mai", "juin",
    "juil", "août", "sep", "oct", "nov", "déc",
  ];
  const sameMonth = s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear();
  if (sameMonth) {
    return `${s.getDate()} → ${e.getDate()} ${months[e.getMonth()]} ${e.getFullYear()}`;
  }
  return `${s.getDate()} ${months[s.getMonth()]} → ${e.getDate()} ${months[e.getMonth()]} ${e.getFullYear()}`;
}
