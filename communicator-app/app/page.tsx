import Brief from "@/components/Brief/Brief";
import { MOCK_BRIEF } from "@/lib/brief-mock";
import type { BriefData } from "@/lib/brief-types";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const CACHE_MS = 60 * 60 * 1000;

async function loadBrief(): Promise<BriefData> {
  // Prefer recent stored brief; fall back to live generation; fall back to mock.
  try {
    const { listBriefs } = await import("@/lib/store");
    const recent = await listBriefs(1);
    const r = recent[0];
    if (r?.data) {
      const ageMs = Date.now() - new Date(r.created_at).getTime();
      if (ageMs < CACHE_MS) return r.data;
    }
  } catch (e) {
    console.warn("listBriefs failed:", e);
  }

  try {
    const { generateBrief } = await import("@/lib/brief");
    const { saveBrief } = await import("@/lib/store");
    const result = await generateBrief();
    saveBrief(result).catch((e) => console.error("saveBrief failed", e));
    return result.data;
  } catch (e) {
    console.error("generateBrief failed, falling back to MOCK_BRIEF:", e);
    return MOCK_BRIEF;
  }
}

export default async function Page() {
  const data = await loadBrief();
  return <Brief data={data} />;
}
