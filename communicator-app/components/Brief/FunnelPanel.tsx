import type { FunnelVsl, FunnelFollow, AdRef } from "@/lib/brief-types";
import Spark from "./Spark";
import { fr, deltaLabel, eur } from "./format";

type Props =
  | { kind: "vsl"; data: FunnelVsl }
  | { kind: "follow"; data: FunnelFollow };

export default function FunnelPanel(props: Props) {
  const { kind, data } = props;
  const isVsl = kind === "vsl";
  const variant = isVsl ? "coral" : "stone";
  const title = isVsl ? "VSL" : "Follow";
  const pillLabel = isVsl ? "Lead generation" : "Audience growth";

  const spendVerdict = data.spend.verdict ?? "neutral";
  const spendDeltaTxt = deltaLabel(data.spend.delta_pct) ?? "";
  const deltaCls =
    spendVerdict === "good" ? "up" :
    spendVerdict === "bad" || spendVerdict === "warning" ? "down" :
    "neutral";

  const sub = isVsl
    ? `7j · vs ${fr((data.spend.prev_value ?? data.spend.value))}€/sem (30j moy.)`
    : `7j · ${fr((props.data as FunnelFollow).followers_gained.value)} followers gagnés`;

  return (
    <div className="funnel">
      <div className="funnel-head">
        <div className="funnel-name">
          {title} <span className="it">funnel</span>
        </div>
        <span className="pill">{pillLabel}</span>
      </div>
      <div className="funnel-spend">
        <span className="v">{fr(data.spend.value)}</span>
        <span className="u">€</span>
        {spendDeltaTxt && <span className={`delta ${deltaCls}`}>{spendDeltaTxt}</span>}
      </div>
      <div className="funnel-sub">{sub}</div>

      <Spark spark={data.spend_spark} variant={variant} />

      {isVsl ? <VslStats data={props.data} /> : <FollowStats data={props.data} />}

      {data.top_ad && <TopAdCard ad={data.top_ad} kind="top" />}
      {!data.top_ad && data.drain && <TopAdCard ad={data.drain} kind="drain" />}
    </div>
  );
}

function VslStats({ data }: { data: FunnelVsl }) {
  const ctrPct = undefined; // not in BriefData; show CTR placeholder if absent
  return (
    <div className="funnel-stats">
      <div className="fs"><div className="lbl">Opt-ins</div><div className="val">{fr(data.opt_ins.value)}</div></div>
      <div className="fs">
        <div className="lbl">VSL vue</div>
        <div className="val">
          {fr(data.vsl_watched.value)}
          <span className="pct">/ {Math.round(data.rate_watched.value)}%</span>
        </div>
      </div>
      <div className="fs"><div className="lbl">Leads chauds</div><div className="val">{fr(data.leads_chauds.value)}</div></div>
      <div className="fs"><div className="lbl">Calls bookés</div><div className="val">{fr(data.calls_booked.value)}</div></div>
      <div className="fs">
        <div className="lbl">Cost / call</div>
        <div className="val">{Math.round(data.cost_per_call.value)}<span className="pct">€</span></div>
      </div>
      <div className="fs">
        <div className="lbl">CPL opt-in</div>
        <div className="val">{data.cpl_opt_in.value.toFixed(2).replace(".", ",")}<span className="pct">€</span></div>
      </div>
    </div>
  );
}

function FollowStats({ data }: { data: FunnelFollow }) {
  const costPerFollower = data.followers_gained.value > 0
    ? data.spend.value / data.followers_gained.value
    : 0;
  const convFollower = data.followers_gained.value > 0
    ? (data.calls_booked.value / data.followers_gained.value) * 100
    : 0;

  return (
    <div className="funnel-stats">
      <div className="fs"><div className="lbl">Followers</div><div className="val">+{fr(data.followers_gained.value)}</div></div>
      <div className="fs"><div className="lbl">Calls bookés</div><div className="val">{fr(data.calls_booked.value)}</div></div>
      <div className="fs">
        <div className="lbl">Cost / call</div>
        <div className="val">{Math.round(data.cost_per_call.value)}<span className="pct">€</span></div>
      </div>
      <div className="fs">
        <div className="lbl">Cost / follower</div>
        <div className="val">{costPerFollower.toFixed(2).replace(".", ",")}<span className="pct">€</span></div>
      </div>
      <div className="fs">
        <div className="lbl">Conv. follower→call</div>
        <div className="val">{convFollower.toFixed(1).replace(".", ",")}<span className="pct">%</span></div>
      </div>
      <div className="fs"><div className="lbl">Total IG</div><div className="val">{fr(data.followers_total)}</div></div>
    </div>
  );
}

function TopAdCard({ ad, kind }: { ad: AdRef; kind: "top" | "drain" }) {
  if (kind === "drain") {
    return (
      <div className="top-ad drain">
        <div className="head">
          <span>Drain · à couper</span>
          <span>{ad.wins ?? 0} call</span>
        </div>
        <div className="name">{ad.name}</div>
        <div className="meta">
          <strong>{eur(ad.spend)}</strong> brûlés · {ad.leads_attributed ?? 0} conversion en 7j
        </div>
      </div>
    );
  }

  const wins = ad.wins ?? 0;
  const cps = ad.cost_per_sale ?? (wins > 0 ? Math.round(ad.spend / wins) : null);
  return (
    <div className="top-ad">
      <div className="head">
        <span>Top ad · 7j</span>
        <span>{wins} {wins > 1 ? "ventes" : "vente"}</span>
      </div>
      <div className="name">{ad.name}</div>
      <div className="meta">
        {cps !== null && (
          <>
            <strong>{cps} €</strong> par vente
            {wins > 0 && ad.spend > 0 && (
              <> · ROAS <strong>×{Math.round((wins * 2000) / ad.spend)}</strong></>
            )}
          </>
        )}
        {cps === null && ad.cpl !== undefined && (
          <>
            <strong>{ad.cpl.toFixed(2).replace(".", ",")} €</strong> CPL · {ad.leads_attributed ?? 0} leads
          </>
        )}
      </div>
    </div>
  );
}
