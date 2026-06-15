"use client";

import { apiFetch } from "@/lib/api";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useWallet } from "@solana/wallet-adapter-react";
import type { ComputeProvider, ComputeType, ProviderStatus } from "@bitagents/shared";
import { shortAddress } from "@bitagents/shared";
import { Cpu, Gauge, Loader2, Save, Signal, WalletCards } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

export default function ProviderPage() {
  const { publicKey } = useWallet();
  const [providers, setProviders] = useState<ComputeProvider[]>([]);
  const [name, setName] = useState("Local BIT Agents Provider");
  const [walletAddress, setWalletAddress] = useState("");
  const [computeType, setComputeType] = useState<ComputeType>("CPU");
  const [pricePerTaskSol, setPricePerTaskSol] = useState(0.01);
  const [status, setStatus] = useState<ProviderStatus>("online");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const payload = await apiFetch<{ providers: ComputeProvider[] }>("/api/providers");
    setProviders(payload.providers);
  }, []);

  useEffect(() => {
    refresh().catch((err) => setError((err as Error).message));
    const id = window.setInterval(() => refresh().catch(() => undefined), 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (publicKey && !walletAddress) {
      setWalletAddress(publicKey.toBase58());
    }
  }, [publicKey, walletAddress]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const payload = await apiFetch<{ provider: ComputeProvider }>("/api/providers", {
        method: "POST",
        body: JSON.stringify({ name, walletAddress, computeType, pricePerTaskSol, status })
      });
      setNotice(`${payload.provider.name} is ${payload.provider.status}. Start the worker with this wallet to process tasks.`);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-black uppercase text-ember">Compute provider dashboard</p>
          <h1 className="mt-2 text-3xl font-black text-foreground sm:text-5xl">Register available compute</h1>
          <p className="mt-3 max-w-2xl text-muted-foreground">Providers publish a wallet, price, and status. The worker uses the same wallet to claim assigned tasks.</p>
        </div>
        <WalletMultiButton />
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
        <form onSubmit={submit} className="rounded-md border border-line bg-panel/80 p-5 shadow-glow">
          <Field label="Provider name" icon={Cpu}>
            <input value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-foreground outline-none transition focus:border-ember" />
          </Field>
          <Field label="Provider wallet" icon={WalletCards}>
            <input value={walletAddress} onChange={(event) => setWalletAddress(event.target.value)} className="w-full rounded-md border border-line bg-ink px-3 py-3 font-mono text-sm text-foreground outline-none transition focus:border-ember" placeholder="Solana wallet public key" />
          </Field>
          <Field label="Compute type" icon={Gauge}>
            <select value={computeType} onChange={(event) => setComputeType(event.target.value as ComputeType)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-foreground outline-none transition focus:border-ember">
              <option value="CPU">CPU</option>
              <option value="GPU_SIMULATED">GPU simulated</option>
              <option value="GENERAL">General</option>
            </select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Price per task" icon={Gauge}>
              <input type="number" min={0.000001} step={0.001} value={pricePerTaskSol} onChange={(event) => setPricePerTaskSol(Number(event.target.value))} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-foreground outline-none transition focus:border-ember" />
            </Field>
            <Field label="Status" icon={Signal}>
              <select value={status} onChange={(event) => setStatus(event.target.value as ProviderStatus)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-foreground outline-none transition focus:border-ember">
                <option value="online">Online</option>
                <option value="offline">Offline</option>
              </select>
            </Field>
          </div>

          {notice && <p className="mt-4 rounded-md border border-mint/40 bg-mint/10 p-3 text-sm font-bold text-mint">{notice}</p>}
          {error && <p className="mt-4 rounded-md border border-red-400/50 bg-red-400/10 p-3 text-sm font-bold text-red-500">{error}</p>}

          <button disabled={busy} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-ember px-5 py-3 font-black text-ink transition hover:bg-coral disabled:cursor-not-allowed disabled:opacity-45">
            {busy ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
            Register provider
          </button>
        </form>

        <div className="rounded-md border border-line bg-panel/80 p-5">
          <div className="flex items-center justify-between gap-4 border-b border-line pb-4">
            <div>
              <p className="font-black text-foreground">Provider pool</p>
              <p className="text-sm text-muted-foreground">Stored locally for the MVP</p>
            </div>
            <span className="rounded-md border border-line px-3 py-1 text-sm font-black text-muted-foreground">{providers.length} total</span>
          </div>
          <div className="mt-5 space-y-3">
            {providers.length === 0 ? (
              <p className="rounded-md border border-line bg-ink/70 p-5 text-center text-muted-foreground">No providers registered.</p>
            ) : (
              providers.map((provider) => (
                <div key={provider.id} className="rounded-md border border-line bg-ink/70 p-4">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                    <div className="min-w-0">
                      <p className="break-words text-lg font-black text-foreground">{provider.name}</p>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">{shortAddress(provider.walletAddress)}</p>
                    </div>
                    <span className={`rounded-md border px-2.5 py-1 text-xs font-black uppercase ${provider.status === "online" ? "border-mint/50 bg-mint/10 text-mint" : "border-line bg-surface-2 text-muted-foreground"}`}>
                      {provider.status}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <SmallStat label="Compute" value={provider.computeType.replace("_", " ")} />
                    <SmallStat label="Price" value={`${provider.pricePerTaskSol.toFixed(4)} SOL`} />
                    <SmallStat label="Updated" value={new Date(provider.updatedAt).toLocaleTimeString()} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({ label, icon: Icon, children }: { label: string; icon: typeof Cpu; children: React.ReactNode }) {
  return (
    <label className="mt-4 block">
      <span className="mb-2 flex items-center gap-2 text-sm font-black text-foreground"><Icon size={16} className="text-ember" />{label}</span>
      {children}
    </label>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-panel/60 p-3">
      <p className="text-xs font-bold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 break-words font-black text-foreground">{value}</p>
    </div>
  );
}
