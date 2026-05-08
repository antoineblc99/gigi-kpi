import type { Spark as SparkType } from "@/lib/brief-types";

type Variant = "coral" | "stone";

type Props = {
  spark: SparkType;
  variant?: Variant;
};

const COLORS: Record<Variant, { line: string; area: string; areaOpacity: number }> = {
  coral: { line: "#CC785C", area: "#F4DDD2", areaOpacity: 0.6 },
  stone: { line: "#7A7367", area: "#E0DDD3", areaOpacity: 0.5 },
};

const W = 600;
const H = 60;
const PAD_TOP = 14;
const PAD_BOTTOM = 16;

export default function Spark({ spark, variant = "coral" }: Props) {
  const series = spark.series ?? [];
  if (series.length < 2) {
    return <div className="spark-wrap"><svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" /></div>;
  }

  const values = series.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = W / (series.length - 1);

  const points = series.map((p, i) => {
    const x = i * stepX;
    const y = PAD_TOP + (1 - (p.value - min) / range) * (H - PAD_TOP - PAD_BOTTOM);
    return [x, y] as const;
  });

  const linePath = points.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${W},${H} L 0,${H} Z`;
  const [lastX, lastY] = points[points.length - 1];

  // Baseline reference = average value, mapped into svg space
  const avg = values.reduce((s, v) => s + v, 0) / values.length;
  const baselineY = PAD_TOP + (1 - (avg - min) / range) * (H - PAD_TOP - PAD_BOTTOM);

  const c = COLORS[variant];

  return (
    <div className="spark-wrap">
      <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <line x1="0" y1={baselineY} x2={W} y2={baselineY} stroke="#E0DDD3" strokeWidth="1" strokeDasharray="3 4" />
        <path d={areaPath} fill={c.area} opacity={c.areaOpacity} />
        <path d={linePath} fill="none" stroke={c.line} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={lastX} cy={lastY} r="3.5" fill={c.line} />
        {variant === "coral" && (
          <circle cx={lastX} cy={lastY} r="6" fill="none" stroke={c.line} strokeWidth="1" opacity="0.4" />
        )}
      </svg>
    </div>
  );
}
