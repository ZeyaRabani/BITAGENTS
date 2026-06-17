"use client";

import {
  AGENT_LABELS,
  makeExplorerTxUrl,
  shortAddress,
  taskInputLabel,
  type AgentTask
} from "@bitagents/shared";
import { useWallet } from "@solana/wallet-adapter-react";
import { ChevronDown, ExternalLink, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Panel } from "@/components/primitives";
import { StatusPill } from "@/components/StatusPill";
import { TaskResult } from "@/components/TaskResult";
import { TaskTimeline } from "@/components/TaskTimeline";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

type Scope = "all" | "mine";

export function TaskList({ limit, showFilters = false }: { limit?: number; showFilters?: boolean }) {
  const { publicKey } = useWallet();
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [scope, setScope] = useState<Scope>("all");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query = scope === "mine" && publicKey ? `?requesterWallet=${publicKey.toBase58()}` : "";
      const data = await apiFetch<{ tasks: AgentTask[] }>(`/api/tasks${query}`);
      setTasks(limit ? data.tasks.slice(0, limit) : data.tasks);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [scope, publicKey, limit]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Panel
      title="tasks.history"
      badge={
        <div className="flex items-center gap-2">
          {showFilters ? (
            <div className="pixel-corners inline-flex border border-border bg-surface-2 p-0.5 font-mono text-[10px] uppercase tracking-[0.08em]">
              {(["all", "mine"] as Scope[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setScope(value)}
                  disabled={value === "mine" && !publicKey}
                  className={cn(
                    "px-2 py-0.5 transition disabled:opacity-40",
                    scope === value ? "bg-signal text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {value}
                </button>
              ))}
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => void load()}
            className="text-muted-foreground transition hover:text-signal"
            aria-label="Refresh"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : undefined} />
          </button>
        </div>
      }
      bodyClassName="p-0"
    >
      {tasks.length === 0 ? (
        <p className="px-4 py-8 text-center font-mono text-sm text-muted-foreground">
          {loading ? "loading tasks…" : "No tasks yet. Run an agent to create one."}
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {tasks.map((task) => {
            const open = expanded === task.id;
            return (
              <li key={task.id}>
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : task.id)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-surface-2"
                >
                  <StatusPill status={task.status} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-display text-sm font-semibold text-foreground">
                      {AGENT_LABELS[task.type]}
                    </span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">
                      {taskInputLabel(task)}
                    </span>
                  </span>
                  <span className="hidden font-mono text-[11px] text-muted-foreground sm:block">
                    {new Date(task.createdAt).toLocaleString()}
                  </span>
                  <ChevronDown
                    size={15}
                    className={cn("shrink-0 text-muted-foreground transition", open && "rotate-180")}
                  />
                </button>
                {open ? (
                  <div className="space-y-4 border-t border-border bg-background/40 px-4 py-4">
                    <div className="grid gap-2 font-mono text-[11px] text-muted-foreground sm:grid-cols-2">
                      <span>task id: {task.id}</span>
                      <span>network: {task.network}</span>
                      <span>provider: {task.assignedProviderName ?? "—"}</span>
                      <span>
                        requester: {task.requesterWallet ? shortAddress(task.requesterWallet) : "free demo"}
                      </span>
                      <span>fee: {task.priceSol} SOL</span>
                      <span>runtime: {task.runtimeMs ? `${task.runtimeMs}ms` : "—"}</span>
                    </div>
                    <TaskTimeline task={task} />
                    {task.paymentSignature ? (
                      <a
                        href={makeExplorerTxUrl(task.paymentSignature, "devnet")}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 font-mono text-[11px] text-signal hover:text-signal-soft"
                      >
                        <ExternalLink size={12} /> devnet payment {shortAddress(task.paymentSignature)}
                      </a>
                    ) : null}
                    {task.status === "failed" ? (
                      <p className="border-l-2 border-danger pl-3 text-sm text-danger">{task.error}</p>
                    ) : null}
                    {task.result ? <TaskResult result={task.result} network={task.network} /> : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
