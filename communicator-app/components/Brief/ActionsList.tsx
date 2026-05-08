import type { ActionItem } from "@/lib/brief-types";
import { initials } from "./format";

const TOP_OWNERS = new Set(["Léa", "Toi", "Antoine"]);

export default function ActionsList({ actions }: { actions: ActionItem[] }) {
  return (
    <section className="section">
      <div className="section-head">
        <span className="label">Actions</span>
        <span className="count">05 · Cette semaine</span>
      </div>
      <div className="actions">
        {actions.map((a) => (
          <div className="action" key={a.rank}>
            <div className="num">{String(a.rank).padStart(2, "0")}</div>
            <div className="body">
              <div className="meta-row">
                <span className={`owner-badge ${TOP_OWNERS.has(a.owner) ? "is-top" : ""}`}>
                  <span className="av">{initials(a.owner)[0] ?? "?"}</span>
                  {a.owner}
                </span>
                <span className="deadline-tag">{a.deadline}</span>
              </div>
              <div className="verb">{renderVerb(a.action)}</div>
            </div>
            <div className="arrow">→</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Highlight inline numbers (€/jour, € amounts, percentages, multipliers) with .num-extract */
function renderVerb(text: string) {
  const parts: Array<string | { kind: "num"; value: string }> = [];
  // Match patterns like "41 €/j", "60 €/jour", "3 700 €", "47 €", "×24", "50%", "ROAS 24x"
  const regex = /(\d[\d  .,]*\s?(?:€\/(?:j|jour|sem|mois)|€|%|x|×\d[\d.,]*))/giu;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIdx) parts.push(text.slice(lastIdx, m.index));
    parts.push({ kind: "num", value: m[0].trim() });
    lastIdx = m.index + m[0].length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));

  return parts.map((p, i) =>
    typeof p === "string" ? <span key={i}>{p}</span> : <span key={i} className="num-extract">{p.value}</span>
  );
}
