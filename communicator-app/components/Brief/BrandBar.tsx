import type { BriefMeta } from "@/lib/brief-types";
import { formatGeneratedAt } from "./format";
import AskButton from "./AskButton";

export default function BrandBar({ meta }: { meta: BriefMeta }) {
  return (
    <div className="brand-bar">
      <div className="brand">
        <span className="dot" />
        Scale.
        <span style={{ fontStyle: "normal", fontFamily: "'Archivo Black',sans-serif", fontSize: 18, letterSpacing: "-0.03em" }}>
          IA
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono',monospace",
            fontStyle: "normal",
            fontSize: 10.5,
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--stone)",
            fontWeight: 600,
            marginLeft: 14,
            paddingLeft: 14,
            borderLeft: "1px solid var(--border)",
          }}
        >
          Brief Data · v1
        </span>
        <AskButton />
      </div>
      <div className="brand-meta">
        <span className="live">Live</span>
        <span className="sep">·</span>
        <span>{formatGeneratedAt(meta.generated_at)}</span>
        <span className="sep">·</span>
        <span>{meta.model}</span>
      </div>
    </div>
  );
}
