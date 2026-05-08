import type { BriefTldr } from "@/lib/brief-types";
import { fr, eur, deltaLabel } from "./format";

export default function TLDRCard({ tldr }: { tldr: BriefTldr }) {
  const spend = Math.round(tldr.spend_total.value);
  const calls = Math.round(tldr.calls_total.value);
  const ventes = Math.round(tldr.ventes.value);
  const contracted = Math.round(tldr.cash_contracted.value);
  const roasContractedX = Math.round(tldr.roas_contracted.value);
  const encaissementPct = tldr.cash_contracted.value > 0
    ? Math.round((tldr.cash_collected.value / tldr.cash_contracted.value) * 100)
    : 0;

  const spendDelta = deltaLabel(tldr.spend_total.delta_pct);
  const closeRate = calls > 0 ? Math.round((ventes / calls) * 100) : 0;
  const cashCollected = Math.round(tldr.cash_collected.value);
  const cashRemaining = Math.max(0, contracted - cashCollected);
  const callsCost = calls > 0 ? Math.round(spend / calls) : 0;

  const alert = tldr.alerts[0];
  const alertCls = alert
    ? alert.level === "critical" ? "alert alert-critical"
    : alert.level === "info" ? "alert alert-info"
    : "alert"
    : "alert";

  return (
    <section className="section">
      <div className="section-head">
        <span className="label">TL;DR</span>
        <span className="count">01 · Punchline</span>
      </div>
      <div className="tldr">
        <p className="tldr-headline">
          <span className="num">{eur(spend)}</span> de spend{" "}
          <span className="arrow">→</span>{" "}
          <span className="num">{calls} calls</span>{" "}
          <span className="arrow">→</span>{" "}
          <span className="num">{ventes} ventes</span> pour{" "}
          <span className="num">{fr(contracted)} €</span> contractés.
          <br />
          ROAS cash <span className="it">×{roasContractedX}</span>, mais{" "}
          <span className="it">{encaissementPct} %</span> seulement encaissés.
        </p>

        <div className="kpi-grid">
          <div className="kpi">
            <div className="lbl">Spend</div>
            <div className="val">
              {fr(spend)}
              <span className="unit">€</span>
            </div>
            {spendDelta && (
              <div className={`sub ${tldr.spend_total.verdict === "good" ? "up" : tldr.spend_total.verdict === "bad" ? "down" : ""}`}>
                {spendDelta} vs 30j moy.
              </div>
            )}
          </div>
          <div className="kpi">
            <div className="lbl">Calls bookés</div>
            <div className="val">{calls}</div>
            <div className="sub">{callsCost}€ par call</div>
          </div>
          <div className="kpi">
            <div className="lbl">Ventes</div>
            <div className="val">{ventes}</div>
            <div className={`sub ${closeRate >= 30 ? "up" : ""}`}>Close rate {closeRate} %</div>
          </div>
          <div className="kpi">
            <div className="lbl">Cash collecté</div>
            <div className="val">
              {fr(cashCollected)}
              <span className="unit">€</span>
            </div>
            {cashRemaining > 0 ? (
              <div className="sub down">{fr(cashRemaining)} € à recouvrer</div>
            ) : (
              <div className="sub up">Tout encaissé</div>
            )}
          </div>
        </div>

        {alert && (
          <div className={alertCls}>
            <span className="icon">!</span>
            <div>
              <span className="alert-lbl">{alert.level === "critical" ? "Critical" : alert.level === "info" ? "Info" : "Warning"}</span>
              {alert.msg}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
