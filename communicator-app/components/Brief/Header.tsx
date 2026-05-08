import type { BriefMeta } from "@/lib/brief-types";
import { formatPeriod } from "./format";

export default function Header({ meta }: { meta: BriefMeta }) {
  // Split client name in two: first word in Archivo Black, rest in italic Instrument Serif coral.
  const parts = meta.client.split(/\s+/);
  const first = parts[0];
  const rest = parts.slice(1).join(" ");

  return (
    <header className="page-header">
      <div>
        <div className="eyebrow">Brief data · {meta.period_label}</div>
        <h1 className="title">
          {first} {rest && <span className="it">{rest}</span>}.
        </h1>
      </div>
      <div className="header-meta">
        <span><span className="v">{formatPeriod(meta.period_start, meta.period_end)}</span></span>
        <span>Comparé aux 30j précédents</span>
        <span>{meta.tool_calls} sources</span>
      </div>
    </header>
  );
}
