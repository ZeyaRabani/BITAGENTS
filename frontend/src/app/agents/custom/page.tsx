"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { AppShell, Panel } from "@/components/AppShell";
import { useCustomAgentWalletAuth } from "@/hooks/useCustomAgentWalletAuth";
import {
  createCustomAgent,
  deleteCustomAgent,
  listCustomAgents,
  type CustomAgent,
} from "@/lib/customAgentClient";

export default function CustomAgentsPage() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useCustomAgentWalletAuth();
  const [agents, setAgents] = useState<CustomAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [creating, setCreating] = useState(false);

  async function refresh(authToken: string) {
    setLoading(true);
    setError(null);
    try {
      setAgents(await listCustomAgents(authToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (token) void refresh(token);
  }, [token]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!token || !name.trim() || !systemPrompt.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createCustomAgent(
        { name: name.trim(), description: description.trim() || undefined, system_prompt: systemPrompt.trim() },
        token
      );
      setName("");
      setDescription("");
      setSystemPrompt("");
      await refresh(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(agentId: string) {
    if (!token) return;
    try {
      await deleteCustomAgent(agentId, token);
      await refresh(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete agent");
    }
  }

  return (
    <AppShell
      title="My Agents"
      subtitle="Create your own AI agent with a custom system prompt, then chat with it."
    >
      <div className="space-y-6">
        {error && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
        )}
        {authError && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            Wallet sign-in: {authError}
          </div>
        )}
        {publicKey && authBusy && (
          <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
            Approve the wallet sign-in message to manage your agents.
          </div>
        )}
        {!publicKey && (
          <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
            Connect your wallet to create and manage your agents.
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <Panel title="Create an agent" className="lg:col-span-1">
            <form onSubmit={onCreate} className="space-y-3">
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Name
                </label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={creating || !token}
                  placeholder="e.g. Pirate Token Analyst"
                  maxLength={80}
                  className="w-full border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50"
                />
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Description (optional)
                </label>
                <input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={creating || !token}
                  placeholder="What does this agent do?"
                  maxLength={280}
                  className="w-full border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50"
                />
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  System prompt
                </label>
                <textarea
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  disabled={creating || !token}
                  placeholder="You are a helpful assistant that..."
                  maxLength={4000}
                  rows={6}
                  className="w-full resize-none border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50"
                />
              </div>
              <button
                type="submit"
                disabled={creating || !token || !name.trim() || !systemPrompt.trim()}
                className="w-full bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {creating ? "Creating…" : "Create agent"}
              </button>
            </form>
          </Panel>

          <Panel title="Your agents" className="lg:col-span-2">
            {loading && <p className="font-mono text-xs text-muted-foreground">Loading…</p>}
            {!loading && isAuthenticated && agents.length === 0 && (
              <p className="text-sm text-muted-foreground">
                You haven&apos;t created any agents yet. Use the form to create your first one.
              </p>
            )}
            <div className="space-y-3">
              {agents.map((agent) => (
                <div key={agent.id} className="flex items-start justify-between gap-4 border border-grid bg-background/60 p-4">
                  <div className="min-w-0">
                    <Link
                      href={`/agents/custom/${agent.id}`}
                      className="font-display text-sm font-semibold text-foreground hover:text-signal"
                    >
                      {agent.name}
                    </Link>
                    {agent.description && (
                      <p className="mt-1 text-xs text-muted-foreground">{agent.description}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Link
                      href={`/agents/custom/${agent.id}`}
                      className="border border-grid px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-foreground"
                    >
                      Chat
                    </Link>
                    <button
                      type="button"
                      onClick={() => void onDelete(agent.id)}
                      className="border border-warn/40 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-warn transition hover:bg-warn/10"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
