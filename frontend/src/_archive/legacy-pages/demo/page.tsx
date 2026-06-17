"use client";

import { StatusPill } from "@/components/StatusPill";
import { TaskResult } from "@/components/TaskResult";
import { TaskTimeline } from "@/components/TaskTimeline";
import { apiFetch } from "@/lib/api";
import { sendSolTransfer } from "@/lib/solana";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import {
  AGENT_LABELS,
  type AgentTask,
  type ComputeProvider,
  makeExplorerTxUrl,
  shortAddress,
  taskInputLabel
} from "@bitagents/shared";
import { ArrowRight, ClipboardList, Loader2, RefreshCw, Send } from "lucide-react";
import { PublicKey } from "@solana/web3.js";
import { useCallback, useEffect, useState } from "react";

export default function DemoPage() {
  const { publicKey, sendTransaction } = useWallet();
  const { connection } = useConnection();
  const [providers, setProviders] = useState<ComputeProvider[]>([]);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [providerPayload, taskPayload] = await Promise.all([
      apiFetch<{ providers: ComputeProvider[] }>("/api/providers"),
      apiFetch<{ tasks: AgentTask[] }>("/api/tasks")
    ]);
    setProviders(providerPayload.providers);
    setTasks(taskPayload.tasks);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setError((err as Error).message));
    const id = window.setInterval(() => refresh().catch(() => undefined), 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  async function payout(task: AgentTask) {
    setError("");
    if (!publicKey) {
      setError("Connect the treasury/admin wallet before sending payout.");
      return;
    }
    if (!task.assignedProviderWallet) {
      setError("Task has no provider wallet.");
      return;
    }

    try {
      setBusyTaskId(task.id);
      const payoutSignature = await sendSolTransfer({
        connection,
        from: publicKey,
        to: new PublicKey(task.assignedProviderWallet),
        amountSol: task.priceSol,
        sendTransaction
      });

      const payload = await apiFetch<{ task: AgentTask }>(`/api/tasks/${task.id}/payout`, {
        method: "POST",
        body: JSON.stringify({ payoutSignature })
      });
      setTasks((current) => current.map((item) => (item.id === payload.task.id ? payload.task : item)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyTaskId(null);
      refresh().catch(() => undefined);
    }
  }

  const completedUnpaid = tasks.filter((task) => task.status === "completed").length;

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-black uppercase text-ember">Admin demo monitor</p>
          <h1 className="mt-2 text-3xl font-black text-white sm:text-5xl">Full BIT Agents flow</h1>
          <p className="mt-3 max-w-2xl text-slate-300">Watch providers, task statuses, devnet signatures, worker results, and payout settlement.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button onClick={() => refresh().catch((err) => setError((err as Error).message))} className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-panel px-4 py-2 font-black text-white transition hover:border-ember">
            <RefreshCw size={17} /> Refresh
          </button>
          <WalletMultiButton />
        </div>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-4">
        <HeroStat label="Providers" value={String(providers.length)} />
        <HeroStat label="Online" value={String(providers.filter((provider) => provider.status === "online").length)} />
        <HeroStat label="Tasks" value={String(tasks.length)} />
        <HeroStat label="Ready payout" value={String(completedUnpaid)} />
      </div>

      {error && <p className="mb-5 rounded-md border border-red-400/50 bg-red-400/10 p-3 text-sm font-bold text-red-300">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[0.78fr_1.22fr]">
        <aside className="rounded-md border border-line bg-panel/80 p-5">
          <div className="flex items-center gap-3 border-b border-line pb-4">
            <ClipboardList className="text-ember" size={21} />
            <div>
              <p className="font-black text-white">Registered providers</p>
              <p className="text-sm text-slate-400">Worker wallets must match these entries</p>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {providers.length === 0 ? (
              <p className="rounded-md border border-line bg-ink/70 p-4 text-sm text-slate-400">Register a provider to enable assignment.</p>
            ) : (
              providers.map((provider) => (
                <div key={provider.id} className="rounded-md border border-line bg-ink/70 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="break-words font-black text-white">{provider.name}</p>
                      <p className="mt-1 font-mono text-xs text-slate-500">{shortAddress(provider.walletAddress)}</p>
                    </div>
                    <span className={`rounded-md border px-2 py-1 text-xs font-black uppercase ${provider.status === "online" ? "border-mint/50 bg-mint/10 text-mint" : "border-slate-600 bg-slate-500/10 text-slate-300"}`}>{provider.status}</span>
                  </div>
                  <p className="mt-3 text-sm text-slate-400">{provider.computeType.replace("_", " ")} at {provider.pricePerTaskSol.toFixed(4)} SOL</p>
                </div>
              ))
            )}
          </div>
        </aside>

        <div className="space-y-4">
          {tasks.length === 0 ? (
            <div className="rounded-md border border-line bg-panel/80 p-8 text-center text-slate-400">No task history yet.</div>
          ) : (
            tasks.map((task) => (
              <article key={task.id} className="rounded-md border border-line bg-panel/80 p-5">
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div className="min-w-0">
                    <p className="text-xs font-black uppercase text-ember">{AGENT_LABELS[task.type]}</p>
                    <h2 className="mt-1 break-words text-xl font-black text-white">{taskInputLabel(task)}</h2>
                    <p className="mt-2 font-mono text-xs text-slate-500">{task.id}</p>
                  </div>
                  <StatusPill status={task.status} />
                </div>

                <div className="mt-5">
                  <TaskTimeline task={task} />
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-4">
                  <Info label="Requester" value={shortAddress(task.requesterWallet)} />
                  <Info label="Provider" value={task.assignedProviderWallet ? shortAddress(task.assignedProviderWallet) : "Unassigned"} />
                  <Info label="Fee" value={`${task.priceSol.toFixed(4)} SOL`} />
                  <Info label="Updated" value={new Date(task.updatedAt).toLocaleTimeString()} />
                </div>

                <div className="mt-4 flex flex-wrap gap-3">
                  {task.paymentSignature && <TxLink label="Payment tx" signature={task.paymentSignature} />}
                  {task.payoutSignature && <TxLink label="Payout tx" signature={task.payoutSignature} />}
                  {task.status === "completed" && !task.payoutSignature && (
                    <button disabled={busyTaskId === task.id} onClick={() => payout(task)} className="inline-flex items-center gap-2 rounded-md bg-ember px-4 py-2 text-sm font-black text-ink transition hover:bg-coral disabled:opacity-45">
                      {busyTaskId === task.id ? <Loader2 className="animate-spin" size={15} /> : <Send size={15} />}
                      Pay provider
                    </button>
                  )}
                </div>

                <div className="mt-5 border-t border-line pt-5">
                  <TaskResult result={task.result} />
                </div>
              </article>
            ))
          )}
        </div>
      </div>
    </section>
  );
}

function HeroStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel/80 p-4">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-black text-white">{value}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-ink/70 p-3">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-1 break-words font-black text-white">{value}</p>
    </div>
  );
}

function TxLink({ label, signature }: { label: string; signature: string }) {
  return (
    <a className="inline-flex items-center gap-2 rounded-md border border-skybit/45 bg-skybit/10 px-4 py-2 text-sm font-black text-skybit transition hover:border-white hover:text-white" href={makeExplorerTxUrl(signature)} target="_blank" rel="noreferrer">
      {label} <ArrowRight size={15} />
    </a>
  );
}
