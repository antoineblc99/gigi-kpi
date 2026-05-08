"use client";

import { useState } from "react";

const CMD = "cd ~/Dev/projets/scale-ia/clients/lea/gigi-kpi/ && claude";

export default function AskButton() {
  const [copied, setCopied] = useState(false);

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(CMD);
    } catch {
      // fallback
      window.prompt("Copie cette commande puis lance-la dans ton terminal :", CMD);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 4000);
  }

  return (
    <>
      <button
        onClick={handleClick}
        title="Copie la commande pour ouvrir Claude Code dans le projet (MCP Supabase déjà branché). Pose ta question, l'agent IA répond avec les data live."
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 10.5,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          color: "var(--stone)",
          fontWeight: 600,
          marginLeft: 14,
          paddingLeft: 14,
          paddingRight: 0,
          borderLeft: "1px solid var(--border)",
          background: "transparent",
          border: "none",
          borderLeftWidth: 1,
          borderLeftStyle: "solid",
          borderLeftColor: "var(--border)",
          cursor: "pointer",
        }}
      >
        💬 Pose une question
      </button>

      {copied && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            maxWidth: 420,
            zIndex: 50,
            background: "var(--espresso, #2a2520)",
            color: "var(--paper, #faf8f5)",
            padding: "16px 20px",
            borderRadius: 4,
            boxShadow: "0 6px 20px rgba(0,0,0,0.18)",
            border: "1px solid var(--stone)",
            fontFamily: "Inter, sans-serif",
            fontSize: 14,
            lineHeight: 1.5,
          }}
        >
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10.5,
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color: "var(--coral, #ff5a4d)",
              marginBottom: 8,
              fontWeight: 600,
            }}
          >
            ✓ Commande copiée
          </div>
          <div style={{ marginBottom: 10 }}>
            Ouvre ton terminal et colle. Claude Code lance avec MCP Supabase déjà
            branché — pose ta question, l'agent query la data live.
          </div>
          <code
            style={{
              display: "block",
              fontSize: 12,
              background: "var(--paper, #faf8f5)",
              color: "var(--espresso, #2a2520)",
              padding: 10,
              fontFamily: "'JetBrains Mono', monospace",
              wordBreak: "break-all",
              borderRadius: 2,
            }}
          >
            {CMD}
          </code>
        </div>
      )}
    </>
  );
}
