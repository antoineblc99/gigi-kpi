import type { BriefData } from "@/lib/brief-types";
import BrandBar from "./BrandBar";
import Header from "./Header";
import TLDRCard from "./TLDRCard";
import FunnelPanel from "./FunnelPanel";
import ClosingTable from "./ClosingTable";
import AttributionTable from "./AttributionTable";
import ActionsList from "./ActionsList";
import Footer from "./Footer";
import "./brief.css";

export default function Brief({ data }: { data: BriefData }) {
  if (data.fallback_markdown) {
    return (
      <div className="brief-root">
        <div className="page">
          <BrandBar meta={data.meta} />
          <Header meta={data.meta} />
          <div className="tbl-card" style={{ padding: 32, whiteSpace: "pre-wrap" }}>
            {data.fallback_markdown}
          </div>
          <Footer />
        </div>
      </div>
    );
  }

  return (
    <div className="brief-root">
      <div className="page">
        <BrandBar meta={data.meta} />
        <Header meta={data.meta} />

        <TLDRCard tldr={data.tldr} />

        <section className="section">
          <div className="section-head">
            <span className="label">Funnels</span>
            <span className="count">02 · VSL &amp; Follow</span>
          </div>
          <div className="funnels">
            <FunnelPanel kind="vsl" data={data.funnels.vsl} />
            <FunnelPanel kind="follow" data={data.funnels.follow} />
          </div>
        </section>

        <ClosingTable closing={data.closing} />
        <AttributionTable attribution={data.attribution} />
        <ActionsList actions={data.actions} />

        <Footer />
      </div>
    </div>
  );
}
