"use client";

import { useEffect, useState, useTransition } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type BriefData = {
  markdown: string;
  generatedAt: string;
  toolCalls: number;
  modelUsed: string;
  warnings: string[];
  cached?: boolean;
  ageMs?: number;
};

type HistoryItem = {
  id: number;
  markdown: string;
  created_at: string;
  model_used: string | null;
};

function formatAge(ms: number): string {
  const m = Math.floor(ms / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

export default function BriefView({ initial }: { initial: BriefData }) {
  const [data, setData] = useState<BriefData>(initial);
  const [isPending, startTransition] = useTransition();
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [age, setAge] = useState<number>(initial.ageMs ?? 0);
  const [copiedToast, setCopiedToast] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setAge((a) => a + 30_000), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    setAge(Date.now() - new Date(data.generatedAt).getTime());
  }, [data.generatedAt]);

  async function regenerate() {
    startTransition(async () => {
      const r = await fetch("/api/brief?force=1", { cache: "no-store" });
      const j = await r.json();
      if (j?.markdown) setData(j);
    });
  }

  async function loadHistory() {
    if (history.length === 0) {
      const r = await fetch("/api/history", { cache: "no-store" });
      const j = await r.json();
      setHistory(j.briefs ?? []);
    }
    setShowHistory(true);
  }

  return (
    <main className="relative z-10 max-w-3xl mx-auto px-6 sm:px-10 py-10">
      <header className="mb-12 pb-6 border-b border-sand">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="eyebrow mb-2">01 ── COMMUNICATEUR</div>
            <h1 className="font-display text-4xl sm:text-5xl tracking-display leading-none">
              Brief Gigi Academy
            </h1>
            <p className="mt-3 text-stone text-sm">
              MAJ {formatAge(age)} · {data.modelUsed} · {data.toolCalls} requêtes data
              {data.cached ? " · cache" : " · live"}
            </p>
          </div>
          <div className="flex gap-3 flex-wrap">
            <button
              onClick={regenerate}
              disabled={isPending}
              className="bg-coral hover:bg-coral-deep disabled:opacity-50 text-paper font-mono text-xs uppercase tracking-widest px-4 py-2.5 rounded-sm transition"
            >
              {isPending ? "Génération…" : "Régénérer"}
            </button>
            <button
              onClick={async () => {
                const cmd = "cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi/ && claude";
                try {
                  await navigator.clipboard.writeText(cmd);
                  setCopiedToast(true);
                  setTimeout(() => setCopiedToast(false), 3500);
                } catch {
                  alert(cmd);
                }
              }}
              title="Copie la commande pour ouvrir Claude Code dans le projet (MCP Supabase déjà branché — pose ta question, l'agent IA répond avec les data live)"
              className="border border-stone text-espresso font-mono text-xs uppercase tracking-widest px-4 py-2.5 rounded-sm hover:bg-paper transition"
            >
              💬 Pose une question
            </button>
            <button
              onClick={loadHistory}
              className="border border-stone text-espresso font-mono text-xs uppercase tracking-widest px-4 py-2.5 rounded-sm hover:bg-paper transition"
            >
              Historique
            </button>
          </div>
        </div>
        {data.warnings?.length > 0 && (
          <div className="mt-4 p-3 bg-paper border-l-2 border-coral text-sm text-stone">
            {data.warnings.map((w, i) => (
              <div key={i} className="font-mono text-xs">⚠ {w}</div>
            ))}
          </div>
        )}
      </header>

      <article className="brief-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.markdown}</ReactMarkdown>
      </article>

      <footer className="mt-20 pt-6 border-t border-sand text-stone font-mono text-xs uppercase tracking-widest flex justify-between">
        <span>Scale.IA · Powered by AIOS</span>
        <span>{new Date(data.generatedAt).toISOString().slice(0, 16).replace("T", " ")}</span>
      </footer>

      {/* Toast — Pose une question */}
      <div
        role="status"
        aria-live="polite"
        className={`fixed bottom-6 right-6 max-w-md z-50 transition-opacity duration-300 ${
          copiedToast ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
      >
        <div className="bg-espresso text-paper px-5 py-4 rounded-sm shadow-lg border border-stone">
          <div className="font-mono text-xs uppercase tracking-widest text-coral mb-2">
            ✓ Commande copiée
          </div>
          <div className="text-sm leading-relaxed">
            Ouvre ton terminal et colle. Claude Code lance avec MCP Supabase déjà branché — pose ta question, l'agent query la data live.
          </div>
          <code className="mt-3 block text-xs bg-paper text-espresso p-2 font-mono break-all">
            cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi/ && claude
          </code>
        </div>
      </div>

      {showHistory && (
        <div
          className="fixed inset-0 bg-espresso/60 z-50 flex items-start justify-center p-6 overflow-y-auto"
          onClick={() => setShowHistory(false)}
        >
          <div
            className="bg-ivory max-w-2xl w-full p-8 mt-12 border border-sand"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-sand">
              <h2 className="font-display text-2xl tracking-display">5 derniers briefs</h2>
              <button
                onClick={() => setShowHistory(false)}
                className="font-mono text-xs uppercase tracking-widest text-stone hover:text-espresso"
              >
                ✕ Fermer
              </button>
            </div>
            {history.length === 0 ? (
              <p className="text-stone">Aucun brief archivé.</p>
            ) : (
              <ul className="space-y-4">
                {history.map((h) => (
                  <li key={h.id} className="border-b border-sand pb-4 last:border-0">
                    <div className="eyebrow mb-1">
                      {new Date(h.created_at).toLocaleString("fr-FR")} · {h.model_used}
                    </div>
                    <p className="text-sm text-espresso/80 line-clamp-3">
                      {h.markdown.split("\n").find((l) => l.trim() && !l.startsWith("#")) ?? ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
