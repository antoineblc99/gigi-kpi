import type { ClosingSection } from "@/lib/brief-types";
import { fr, initials, encaissementBucket } from "./format";

export default function ClosingTable({ closing }: { closing: ClosingSection }) {
  return (
    <section className="section">
      <div className="section-head">
        <span className="label">Closing</span>
        <span className="count">03 · Encaissement</span>
      </div>
      <div className="tbl-card">
        <table className="tbl">
          <thead>
            <tr>
              <th>Closeuse</th>
              <th className="num">Calls</th>
              <th className="num">Show rate</th>
              <th className="num">Ventes</th>
              <th className="num">Contracté</th>
              <th className="num">Collecté</th>
              <th>Encaissé</th>
            </tr>
          </thead>
          <tbody>
            {closing.closers.map((c, idx) => {
              const bucket = encaissementBucket(c.encaissement_pct);
              const showRateDisplay = c.calls_recus === 0 ? "—" : `${Math.round(c.show_rate_pct)}`;
              return (
                <tr key={c.closer_name}>
                  <td>
                    <div className={`closer ${idx === 0 ? "is-top" : ""}`}>
                      <div className="av">{initials(c.closer_name)}</div>
                      <div className="nm">{c.closer_name}</div>
                    </div>
                  </td>
                  <td className="num">{c.calls_recus}</td>
                  <td className="num" style={c.calls_recus === 0 ? { color: "var(--stone-soft)" } : undefined}>
                    {showRateDisplay}{c.calls_recus > 0 && <span className="u">%</span>}
                  </td>
                  <td className="num">{c.ventes}</td>
                  <td className="num">{fr(c.cash_contracted)}<span className="u">€</span></td>
                  <td className="num">{fr(c.cash_collected)}<span className="u">€</span></td>
                  <td>
                    <div className="bar-wrap">
                      <div className={`bar ${bucket}`}>
                        <div className="fill" style={{ width: `${Math.min(100, c.encaissement_pct)}%` }} />
                      </div>
                      <span className={`bar-pct ${bucket}`}>{Math.round(c.encaissement_pct)} %</span>
                    </div>
                  </td>
                </tr>
              );
            })}
            <ClosingTotalsRow totals={closing.totals} />
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ClosingTotalsRow({ totals }: { totals: ClosingSection["totals"] }) {
  const bucket = encaissementBucket(totals.encaissement_pct);
  return (
    <tr className="row-total">
      <td>
        <div className="closer is-total">
          <div className="av">Σ</div>
          <div className="nm">Total</div>
        </div>
      </td>
      <td className="num">{totals.calls_recus}</td>
      <td className="num">{Math.round(totals.show_rate_pct)}<span className="u">%</span></td>
      <td className="num">{totals.ventes}</td>
      <td className="num">{fr(totals.cash_contracted)}<span className="u">€</span></td>
      <td className="num">{fr(totals.cash_collected)}<span className="u">€</span></td>
      <td>
        <div className="bar-wrap">
          <div className={`bar ${bucket}`}>
            <div className="fill" style={{ width: `${Math.min(100, totals.encaissement_pct)}%` }} />
          </div>
          <span className={`bar-pct ${bucket}`}>{Math.round(totals.encaissement_pct)} %</span>
        </div>
      </td>
    </tr>
  );
}
