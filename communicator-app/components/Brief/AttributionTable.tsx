import type { AttributionSection } from "@/lib/brief-types";
import { cplBucket, winsBucket, cpsBucket } from "./format";

export default function AttributionTable({ attribution }: { attribution: AttributionSection }) {
  const rows = attribution.top_by_spend.slice(0, 5);
  return (
    <section className="section">
      <div className="section-head">
        <span className="label">Attribution</span>
        <span className="count">04 · Top {rows.length} ads</span>
      </div>
      <div className="tbl-card attr-wrap">
        <table className="tbl attr-tbl">
          <thead>
            <tr>
              <th>Ad</th>
              <th className="num">Spend</th>
              <th className="num">Leads</th>
              <th className="num">Wins</th>
              <th className="num">CPL</th>
              <th className="num">CPS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((ad) => {
              const wins = ad.wins ?? 0;
              const cps = ad.cost_per_sale ?? (wins > 0 ? ad.spend / wins : undefined);
              return (
                <tr key={ad.ad_id}>
                  <td>
                    <div className="ad-name">
                      <span className={`rank ${ad.rank === 1 ? "r1" : ""}`}>{ad.rank}</span>
                      {ad.name}
                    </div>
                  </td>
                  <td className="num">{Math.round(ad.spend)}<span className="u">€</span></td>
                  <td className="num">{ad.leads_attributed ?? 0}</td>
                  <td className="num"><span className={`heat ${winsBucket(wins)}`}>{wins}</span></td>
                  <td className="num">
                    {ad.cpl !== undefined
                      ? <span className={`heat ${cplBucket(ad.cpl)}`}>{ad.cpl.toFixed(2).replace(".", ",")}</span>
                      : <span className="heat h-empty">—</span>}
                  </td>
                  <td className="num">
                    {cps !== undefined
                      ? <span className={`heat ${cpsBucket(cps)}`}>{Math.round(cps)} €</span>
                      : <span className="heat h-empty">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
