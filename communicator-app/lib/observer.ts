/**
 * Observer agent — orchestration
 *
 * 1. Run all anomaly rules
 * 2. Filter against agent_memory (skip dupes seen in last N hours)
 * 3. Push to Slack via webhook
 * 4. Log to decision_log with status='proposed'
 * 5. Update agent_memory (last_seen per rule_id)
 */
import { sb } from "@/lib/sql";
import { detectAll, Anomaly, Severity } from "@/lib/anomalies";

const DEDUPE_HOURS = 6;  // skip same rule_id if seen in last 6h

const SEVERITY_EMOJI: Record<Severity, string> = {
  critical: "🔴",
  warning: "🟠",
  info: "🔵",
};

export type ObserverRunResult = {
  ran_at: string;
  detected: number;
  pushed: number;
  skipped_dedupe: number;
  errors: string[];
};

export async function runObserver(): Promise<ObserverRunResult> {
  const ranAt = new Date().toISOString();
  const errors: string[] = [];

  let anomalies: Anomaly[];
  try {
    anomalies = await detectAll();
  } catch (e: any) {
    return { ran_at: ranAt, detected: 0, pushed: 0, skipped_dedupe: 0, errors: [String(e?.message ?? e)] };
  }

  let pushed = 0;
  let skipped = 0;

  for (const a of anomalies) {
    try {
      const isDupe = await isRecentlySeen(a.rule_id);
      if (isDupe) {
        skipped++;
        continue;
      }
      await pushToSlack(a);
      await logDecision(a);
      await markSeen(a.rule_id);
      pushed++;
    } catch (e: any) {
      errors.push(`${a.rule_id}: ${String(e?.message ?? e)}`);
    }
  }

  return { ran_at: ranAt, detected: anomalies.length, pushed, skipped_dedupe: skipped, errors };
}

// ============================================================================
// Dedupe via agent_memory
// ============================================================================
async function isRecentlySeen(ruleId: string): Promise<boolean> {
  const { data } = await sb()
    .from("agent_memory")
    .select("updated_at")
    .eq("agent_name", "observer")
    .eq("key", `last_seen:${ruleId}`)
    .maybeSingle();
  if (!data?.updated_at) return false;
  const ageMs = Date.now() - new Date(data.updated_at).getTime();
  return ageMs < DEDUPE_HOURS * 60 * 60 * 1000;
}

async function markSeen(ruleId: string): Promise<void> {
  await sb()
    .from("agent_memory")
    .upsert(
      {
        agent_name: "observer",
        key: `last_seen:${ruleId}`,
        value: { last_seen_at: new Date().toISOString() },
        updated_at: new Date().toISOString(),
      },
      { onConflict: "agent_name,key" },
    );
}

// ============================================================================
// Slack push (Block Kit)
// ============================================================================
async function pushToSlack(a: Anomaly): Promise<void> {
  const url = process.env.SLACK_WEBHOOK_URL;
  if (!url) {
    console.warn("[observer] SLACK_WEBHOOK_URL not set — skipping Slack push");
    return;
  }

  const blocks = [
    {
      type: "header",
      text: { type: "plain_text", text: `${SEVERITY_EMOJI[a.severity]} ${a.title}`, emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: `*${a.summary}*` },
    },
    {
      type: "section",
      fields: [
        { type: "mrkdwn", text: `*Maintenant*\n${a.current}` },
        { type: "mrkdwn", text: `*Référence*\n${a.baseline}` },
      ],
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: a.context_md },
    },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*Actions suggérées*\n${a.actions.map((x, i) => `${i + 1}. ${x}`).join("\n")}`,
      },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `🤖 Observer · rule \`${a.rule_id}\` · ${new Date().toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}`,
        },
      ],
    },
  ];

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blocks, text: a.title }),
  });
  if (!res.ok) {
    throw new Error(`Slack push failed: ${res.status} ${await res.text()}`);
  }
}

// ============================================================================
// Decision log
// ============================================================================
async function logDecision(a: Anomaly): Promise<void> {
  await sb()
    .from("decision_log")
    .insert({
      agent_name: "observer",
      decision_type: `anomaly:${a.rule_id}`,
      payload: {
        rule_id: a.rule_id,
        severity: a.severity,
        title: a.title,
        summary: a.summary,
        current: a.current,
        baseline: a.baseline,
        actions: a.actions,
        ...a.payload,
      },
      status: "proposed",
    });
}
