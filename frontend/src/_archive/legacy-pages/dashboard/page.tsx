"use client";

import { apiFetch } from "@/lib/api";
import { getTreasuryPublicKey, sendSolTransfer } from "@/lib/solana";
import { TaskResult } from "@/components/TaskResult";
import { TaskTimeline } from "@/components/TaskTimeline";
import { StatusPill } from "@/components/StatusPill";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import {
  AGENT_LABELS,
  type AgentTask,
  type AgentType,
  type ComputeProvider,
  makeExplorerTxUrl,
  shortAddress,
  taskInputLabel
} from "@bitagents/shared";
import { ArrowRight, BadgeDollarSign, BrainCircuit, Cpu, Loader2, Search, WalletCards } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

export default function DashboardPage() {
  const { publicKey, sendTransaction, connected } = useWallet();
  const { connection } = useConnection();
  const [providers, setProviders] = useState<ComputeProvider[]>([]);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [agentType, setAgentType] = useState<AgentType>("wallet_watcher");
  const [walletAddress, setWalletAddress] = useState("");
  const [keyword, setKeyword] = useState("solana agent compute marketplace");
  const [size, setSize] = useState(64);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const requesterWallet = publicKey?.toBase58();
  const onlineProviders = providers.filter((provider) => provider.status === "online");
  const currentPrice = onlineProviders.sort((a, b) => a.pricePerTaskSol - b.pricePerTaskSol)[0]?.pricePerTaskSol ?? 0.01;

  const refresh = useCallback(async () => {
    const [providerPayload, taskPayload] = await Promise.all([
      apiFetch<{ providers: ComputeProvider[] }>("/api/providers"),
      apiFetch<{ tasks: AgentTask[] }>(requesterWallet ? `/api/tasks?requesterWallet=${requesterWallet}` : "/api/tasks")
    ]);
    setProviders(providerPayload.providers);
    setTasks(taskPayload.tasks);
  }, [requesterWallet]);

  useEffect(() => {
    refresh().catch((err) => setError((err as Error).message));
    const id = window.setInterval(() => refresh().catch(() => undefined), 3500);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (publicKey && agentType === "wallet_watcher" && !walletAddress) {
      setWalletAddress(publicKey.toBase58());
    }
  }, [agentType, publicKey, walletAddress]);

  const formHint = useMemo(() => {
    if (agentType === "wallet_watcher") return "Solana devnet wallet address";
    if (agentType === "research") return "Keyword or project name";
    return "Matrix size, 12 to 220";
  }, [agentType]);

  async function submitTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!publicKey || !connected) {
      setError("Connect a Solana wallet first.");
      return;
    }

    try {
      setBusy(true);
      const input =
        agentType === "wallet_watcher"
          ? { walletAddress }
          : agentType === "research"
            ? { keyword }
            : { size };

      const created = await apiFetch<{ task: AgentTask }>("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ type: agentType, input, requesterWallet: publicKey.toBase58() })
      });

      setNotice(`Task ${created.task.id.slice(0, 8)} created. Please approve the devnet SOL payment.`);
      const paymentSignature = await sendSolTransfer({
        connection,
        from: publicKey,
        to: getTreasuryPublicKey(),
        amountSol: created.task.priceSol,
        sendTransaction
      });

      const paid = await apiFetch<{ task: AgentTask }>(`/api/tasks/${created.task.id}/payment`, {
        method: "POST",
        body: JSON.stringify({ paymentSignature, requesterWallet: publicKey.toBase58() })
      });

      setTasks((current) => [paid.task, ...current.filter((task) => task.id !== paid.task.id)]);
      setNotice("Payment confirmed. The provider worker can now claim the task.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      refresh().catch(() => undefined);
    }
  }

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-black uppercase text-ember">User dashboard</p>
          <h1 className="mt-2 text-3xl font-black text-white sm:text-5xl">Create an agent task</h1>
          <p className="mt-3 max-w-2xl text-slate-300">Pay a provider on Solana devnet, then watch the worker run real off-chain computation.</p>
        </div>
        <WalletMultiButton />
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <form onSubmit={submitTask} className="rounded-md border border-line bg-panel/80 p-5 shadow-glow">
          <div className="grid gap-3 sm:grid-cols-3">
            <AgentButton active={agentType === "wallet_watcher"} icon={WalletCards} label="Wallet Watcher" onClick={() => setAgentType("wallet_watcher")} />
            <AgentButton active={agentType === "research"} icon={Search} label="Research" onClick={() => setAgentType("research")} />
            <AgentButton active={agentType === "benchmark"} icon={Cpu} label="Benchmark" onClick={() => setAgentType("benchmark")} />
          </div>

          <label className="mt-6 block text-sm font-black text-slate-200" htmlFor="agent-input">
            {formHint}
          </label>
          {agentType === "wallet_watcher" && (
            <input id="agent-input" value={walletAddress} onChange={(event) => setWalletAddress(event.target.value)} className="mt-2 w-full rounded-md border border-line bg-ink px-3 py-3 font-mono text-sm text-white outline-none transition focus:border-ember" placeholder="Devnet wallet address" />
          )}
          {agentType === "research" && (
            <input id="agent-input" value={keyword} onChange={(event) => setKeyword(event.target.value)} className="mt-2 w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember" placeholder="Project or keyword" />
          )}
          {agentType === "benchmark" && (
            <input id="agent-input" type="number" min={12} max={220} value={size} onChange={(event) => setSize(Number(event.target.value))} className="mt-2 w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember" />
          )}

          <div className="mt-5 grid gap-3 rounded-md border border-line bg-ink/70 p-4 sm:grid-cols-3">
            <Metric label="Provider pool" value={`${onlineProviders.length} online`} />
            <Metric label="Task fee" value={`${currentPrice.toFixed(4)} SOL`} />
            <Metric label="Network" value="Devnet" />
          </div>

          {notice && <p className="mt-4 rounded-md border border-mint/40 bg-mint/10 p-3 text-sm font-bold text-mint">{notice}</p>}
          {error && <p className="mt-4 rounded-md border border-red-400/50 bg-red-400/10 p-3 text-sm font-bold text-red-300">{error}</p>}

          <button disabled={busy || !connected} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-ember px-5 py-3 font-black text-ink transition hover:bg-coral disabled:cursor-not-allowed disabled:opacity-45">
            {busy ? <Loader2 className="animate-spin" size={18} /> : <BadgeDollarSign size={18} />}
            Create and pay task
          </button>
        </form>

        <div className="space-y-4">
          {tasks.length === 0 ? (
            <div className="rounded-md border border-line bg-panel/75 p-8 text-center text-slate-400">No tasks yet. Create one to start the provider loop.</div>
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
                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  <Metric label="Fee" value={`${task.priceSol.toFixed(4)} SOL`} />
                  <Metric label="Provider" value={task.assignedProviderWallet ? shortAddress(task.assignedProviderWallet) : "Waiting"} />
                  <Metric label="Payment" value={task.paymentSignature ? "Recorded" : "Pending"} />
                </div>
                {task.paymentSignature && (
                  <a className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-skybit hover:text-white" href={makeExplorerTxUrl(task.paymentSignature)} target="_blank" rel="noreferrer">
                    View payment <ArrowRight size={15} />
                  </a>
                )}
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

function AgentButton({ active, icon: Icon, label, onClick }: { active: boolean; icon: typeof WalletCards; label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={`flex min-h-[88px] flex-col items-start justify-between rounded-md border p-3 text-left transition ${active ? "border-ember bg-ember text-ink" : "border-line bg-ink text-slate-300 hover:border-coral"}`}>
      <Icon size={21} />
      <span className="text-sm font-black">{label}</span>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
      <p className="mt-1 break-words font-black text-white">{value}</p>
    </div>
  );
}
