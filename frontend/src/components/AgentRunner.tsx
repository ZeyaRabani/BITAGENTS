"use client";

import {
  DEFAULT_TASK_PRICE_SOL,
  makeExplorerTxUrl,
  shortAddress,
  type AgentTask,
  type AgentType
} from "@bitagents/shared";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { useWalletModal } from "@solana/wallet-adapter-react-ui";
import { ArrowRight, ExternalLink, Loader2, Play, Wallet } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useNetwork } from "@/components/NetworkProvider";
import { ActionButton, Panel, Tag } from "@/components/primitives";
import { StatusPill } from "@/components/StatusPill";
import { TaskResult } from "@/components/TaskResult";
import { TaskTimeline } from "@/components/TaskTimeline";
import { apiFetch } from "@/lib/api";
import { AGENTS, agentMeta } from "@/lib/agents";
import { sendSolTransfer, toPublicKey } from "@/lib/solana";
import { cn } from "@/lib/utils";

type Phase = "idle" | "creating" | "paying" | "computing" | "done" | "error";

export function AgentRunner({ defaultType = "wallet_watcher" }: { defaultType?: AgentType }) {
  const [type, setType] = useState<AgentType>(defaultType);
  const [value, setValue] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [task, setTask] = useState<AgentTask | null>(null);
  const [paymentSig, setPaymentSig] = useState<string | null>(null);

  const meta = useMemo(() => agentMeta(type), [type]);
  const { network, paymentsEnabled, config, label } = useNetwork();
  const { connection } = useConnection();
  const { publicKey, sendTransaction, connected } = useWallet();
  const { setVisible } = useWalletModal();

  const busy = phase === "creating" || phase === "paying" || phase === "computing";
  const canPay = paymentsEnabled && connected && config.treasuryConfigured;
  const feeSol = config.taskFeeSol || DEFAULT_TASK_PRICE_SOL;

  function selectAgent(next: AgentType) {
    setType(next);
    setValue("");
    setTask(null);
    setPaymentSig(null);
    setPhase("idle");
  }

  async function run(free: boolean) {
    const trimmed = value.trim();
    if (!trimmed) {
      toast.error(`Enter ${meta.inputLabel.toLowerCase()} first.`);
      return;
    }

    setTask(null);
    setPaymentSig(null);

    try {
      setPhase("creating");
      const input =
        meta.inputField === "walletAddress" ? { walletAddress: trimmed } : { query: trimmed };
      const requesterWallet = !free && publicKey ? publicKey.toBase58() : undefined;

      const created = await apiFetch<{ task: AgentTask }>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ type, input, network, requesterWallet, free })
      });
      let current = created.task;
      setTask(current);

      if (!free && publicKey) {
        setPhase("paying");
        const treasury = toPublicKey(config.treasuryWallet);
        const signature = await sendSolTransfer({
          connection,
          from: publicKey,
          to: treasury,
          amountSol: current.priceSol || feeSol,
          sendTransaction
        });
        setPaymentSig(signature);
        const paid = await apiFetch<{ task: AgentTask }>(`/api/tasks/${current.id}/payment`, {
          method: "POST",
          body: JSON.stringify({ paymentSignature: signature, requesterWallet: publicKey.toBase58() })
        });
        current = paid.task;
        setTask(current);
        toast.success("Devnet payment confirmed.");
      }

      setPhase("computing");
      const ran = await apiFetch<{ task: AgentTask }>(`/api/tasks/${current.id}/run`, { method: "POST" });
      setTask(ran.task);
      setPhase(ran.task.status === "failed" ? "error" : "done");
      if (ran.task.status === "failed") {
        toast.error(ran.task.error ?? "Computation failed.");
      } else {
        toast.success("Task completed.");
      }
    } catch (error) {
      setPhase("error");
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="space-y-5">
        <Panel title="agent.select">
          <div className="grid gap-2">
            {AGENTS.map((agent) => {
              const Icon = agent.icon;
              const active = agent.type === type;
              return (
                <button
                  key={agent.type}
                  type="button"
                  onClick={() => selectAgent(agent.type)}
                  className={cn(
                    "pixel-corners flex items-start gap-3 border p-3 text-left transition",
                    active
                      ? "border-signal bg-signal/10"
                      : "border-border bg-surface-2 hover:border-signal/50"
                  )}
                >
                  <span
                    className={cn(
                      "pixel-corners flex h-9 w-9 shrink-0 items-center justify-center border",
                      active ? "border-signal bg-signal/15 text-signal" : "border-border text-muted-foreground"
                    )}
                  >
                    <Icon size={16} />
                  </span>
                  <span className="min-w-0">
                    <span className="block font-display text-sm font-semibold text-foreground">{agent.label}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{agent.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </Panel>

        <Panel title="agent.input">
          <label className="mb-1.5 block font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            {meta.inputLabel}
          </label>
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder={meta.placeholder}
            spellCheck={false}
            className="pixel-corners w-full border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground outline-none transition focus:border-signal"
          />
          <button
            type="button"
            onClick={() => setValue(meta.example)}
            className="mt-2 font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground hover:text-signal"
          >
            use example → {shortAddress(meta.example)}
          </button>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
            <Tag>{label}</Tag>
            {canPay ? (
              <Tag className="border-signal/40 text-signal">fee {feeSol} SOL</Tag>
            ) : (
              <Tag>free demo</Tag>
            )}
            {connected && publicKey ? <Tag>wallet {shortAddress(publicKey.toBase58())}</Tag> : null}
          </div>

          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            {canPay ? (
              <ActionButton onClick={() => run(false)} disabled={busy} className="flex-1">
                {busy ? <Loader2 className="animate-spin" size={15} /> : <Play size={15} />}
                Pay {feeSol} SOL &amp; run
              </ActionButton>
            ) : null}
            <ActionButton
              variant={canPay ? "outline" : "primary"}
              onClick={() => run(true)}
              disabled={busy}
              className="flex-1"
            >
              {busy && !canPay ? <Loader2 className="animate-spin" size={15} /> : <Play size={15} />}
              Run free demo
            </ActionButton>
          </div>

          {!connected ? (
            <button
              type="button"
              onClick={() => setVisible(true)}
              className="mt-3 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-signal hover:text-signal-soft"
            >
              <Wallet size={13} /> connect wallet to pay on devnet
            </button>
          ) : null}
          {connected && !paymentsEnabled ? (
            <p className="mt-3 font-mono text-[11px] text-muted-foreground">
              Mainnet is read-only. Switch to Devnet Demo to pay a task fee.
            </p>
          ) : null}
          {connected && paymentsEnabled && !config.treasuryConfigured ? (
            <p className="mt-3 font-mono text-[11px] text-warn">
              Treasury wallet not configured — running as free demo.
            </p>
          ) : null}
        </Panel>
      </div>

      <Panel
        title="agent.run"
        badge={task ? <StatusPill status={task.status} /> : <span className="cursor-blink font-mono text-xs text-muted-foreground" />}
        bodyClassName="space-y-4"
      >
        {!task ? (
          <EmptyRun phase={phase} outputs={meta.outputs} />
        ) : (
          <>
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-muted-foreground">
                <span>task {task.id.slice(0, 8)}</span>
                <span>{task.assignedProviderName ?? "—"}</span>
              </div>
              <TaskTimeline task={task} />
            </div>

            {paymentSig ? (
              <a
                href={makeExplorerTxUrl(paymentSig, "devnet")}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 font-mono text-[11px] text-signal hover:text-signal-soft"
              >
                <ExternalLink size={12} /> devnet payment {shortAddress(paymentSig)}
              </a>
            ) : null}

            {busy ? (
              <div className="flex items-center gap-2 font-mono text-xs text-signal-soft">
                <Loader2 className="animate-spin" size={14} />
                {phase === "creating" ? "creating task…" : phase === "paying" ? "awaiting devnet payment…" : "running real computation…"}
              </div>
            ) : null}

            {task.status === "failed" ? (
              <p className="border-l-2 border-danger pl-3 text-sm text-danger">{task.error}</p>
            ) : null}

            {task.result ? <TaskResult result={task.result} network={task.network} /> : null}
          </>
        )}
      </Panel>
    </div>
  );
}

function EmptyRun({ phase, outputs }: { phase: Phase; outputs: string[] }) {
  return (
    <div className="space-y-4">
      <p className="font-mono text-sm text-muted-foreground">
        {phase === "error" ? "Run failed. Adjust input and try again." : "Awaiting input. Select an agent and run a task."}
      </p>
      <div className="space-y-1.5">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">expected output</p>
        {outputs.map((output) => (
          <p key={output} className="flex items-center gap-2 font-mono text-xs text-foreground/80">
            <ArrowRight size={12} className="text-signal" />
            {output}
          </p>
        ))}
      </div>
    </div>
  );
}
