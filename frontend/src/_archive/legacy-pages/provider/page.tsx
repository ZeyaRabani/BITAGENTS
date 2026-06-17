"use client";

import { useMemo, useState, ReactNode } from "react";
import { AppShell, Panel, Stat } from "@/components/AppShell";
import { addListing } from "@/lib/marketplaceStore";
import {
  useWallet,
} from "@solana/wallet-adapter-react";
import { buildProviderMessage } from "@/lib/solana/providers";
import { toast } from "sonner";

export default function ProviderPage() {
  const { publicKey, connected, signMessage } = useWallet();

  const [gpu, setGpu] = useState("H100");
  const [count, setCount] = useState(4);
  const [hours, setHours] = useState(1000);
  const [price, setPrice] = useState(0.42);
  const [loading, setLoading] = useState(false);

  const canSubmit = useMemo(() => {
    return connected && publicKey && signMessage;
  }, [connected, publicKey, signMessage]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!canSubmit || !publicKey || !signMessage) {
      alert("Connect wallet first");
      return;
    }

    try {
      setLoading(true);

      const message = buildProviderMessage({
        wallet: publicKey,
        gpu,
        hours: count * hours,
        price,
      });

      const encoded = new TextEncoder().encode(message);
      const signature = await signMessage(encoded);

      const signatureBase64 = Buffer.from(signature).toString("base64");

      // 🔥 "devent" simulation (replace later with real event bus / backend)
      console.log("📡 DEVENT: provider_listing_signed", {
        wallet: publicKey.toBase58(),
        gpu,
        hours: count * hours,
        price,
        signature: signatureBase64,
      });

      toast.success('Listing signed and submitted!');

      addListing({
        provider: publicKey.toBase58().slice(0, 6) + "...",
        gpu,
        hours: count * hours,
        price,
      });
    } catch (err) {
      console.error(err);
      alert("Signature failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell
      title="Provider Dashboard"
      subtitle="Register GPU capacity. Sign listings on-chain identity. Earn cGPU yield."
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <Panel title="// Register GPU">
          <form className="space-y-5" onSubmit={handleSubmit}>
            <Field label="GPU Type">
              <div className="grid grid-cols-3 gap-px bg-[color:var(--border)]">
                {["H100", "A100", "4090"].map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGpu(g)}
                    className={`bg-background py-2.5 font-mono text-xs uppercase tracking-[0.16em] transition ${gpu === g
                      ? "text-signal"
                      : "text-muted-foreground hover:text-foreground"
                      }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="GPU Count">
              <Input value={count} onChange={(v) => setCount(Number(v))} />
            </Field>

            <Field label="Available Hours">
              <Input value={hours} onChange={(v) => setHours(Number(v))} />
            </Field>

            <Field label="Expected Price ($ / GPU-hr)">
              <Input value={price} onChange={(v) => setPrice(Number(v))} />
            </Field>

            <button
              type="submit"
              disabled={!canSubmit || loading}
              className={`w-full py-3 font-mono text-xs font-semibold uppercase tracking-[0.16em] transition
                ${!canSubmit
                  ? "bg-gray-600 text-gray-300 cursor-not-allowed"
                  : "bg-signal text-primary-foreground hover:opacity-90"
                }`}
            >
              {loading ? "Signing..." : "Sign & List Capacity →"}
            </button>
          </form>
        </Panel>

        <div className="space-y-6">
          <Panel title="// Listed Capacity">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-display text-3xl font-bold tabular-nums">
                  1,000{" "}
                  <span className="text-base font-normal text-muted-foreground">
                    GPU-hrs
                  </span>
                </div>

                <div className="mt-1 font-mono text-xs text-muted-foreground">
                  H100 · cluster-01
                </div>
              </div>

              <span className="inline-flex items-center gap-2 border border-grid bg-surface/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                <span className="h-1.5 w-1.5 rounded-full bg-signal animate-pulse-dot" />
                Active
              </span>
            </div>

            <div className="mt-4 h-2 w-full bg-surface-2">
              <div className="h-full bg-signal" style={{ width: "68%" }} />
            </div>

            <div className="mt-2 flex justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              <span>680 consumed</span>
              <span>320 remaining</span>
            </div>
          </Panel>

          <div className="grid gap-4 sm:grid-cols-3">
            <Stat label="Revenue Earned" value="$284.40" accent="signal" />
            <Stat label="cGPU Minted" value="1,000" />
            <Stat label="Utilization" value="68%" accent="warn" />
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <div className="mt-2">{children}</div>
    </label>
  );
}

function Input({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: string) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full border border-grid bg-background px-3 py-2.5 font-mono text-sm tabular-nums text-foreground outline-none transition focus:border-signal"
    />
  );
}

// "use client";

// import { apiFetch } from "@/lib/api";
// import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
// import { useWallet } from "@solana/wallet-adapter-react";
// import type { ComputeProvider, ComputeType, ProviderStatus } from "@bitagents/shared";
// import { shortAddress } from "@bitagents/shared";
// import { Cpu, Gauge, Loader2, Save, Signal, WalletCards } from "lucide-react";
// import { useCallback, useEffect, useState } from "react";

// export default function ProviderPage() {
//   const { publicKey } = useWallet();
//   const [providers, setProviders] = useState<ComputeProvider[]>([]);
//   const [name, setName] = useState("Local BIT Agents Provider");
//   const [walletAddress, setWalletAddress] = useState("");
//   const [computeType, setComputeType] = useState<ComputeType>("CPU");
//   const [pricePerTaskSol, setPricePerTaskSol] = useState(0.01);
//   const [status, setStatus] = useState<ProviderStatus>("online");
//   const [busy, setBusy] = useState(false);
//   const [notice, setNotice] = useState("");
//   const [error, setError] = useState("");

//   const refresh = useCallback(async () => {
//     const payload = await apiFetch<{ providers: ComputeProvider[] }>("/api/providers");
//     setProviders(payload.providers);
//   }, []);

//   useEffect(() => {
//     refresh().catch((err) => setError((err as Error).message));
//     const id = window.setInterval(() => refresh().catch(() => undefined), 4000);
//     return () => window.clearInterval(id);
//   }, [refresh]);

//   useEffect(() => {
//     if (publicKey && !walletAddress) {
//       setWalletAddress(publicKey.toBase58());
//     }
//   }, [publicKey, walletAddress]);

//   async function submit(event: React.FormEvent<HTMLFormElement>) {
//     event.preventDefault();
//     setBusy(true);
//     setError("");
//     setNotice("");

//     try {
//       const payload = await apiFetch<{ provider: ComputeProvider }>("/api/providers", {
//         method: "POST",
//         body: JSON.stringify({ name, walletAddress, computeType, pricePerTaskSol, status })
//       });
//       setNotice(`${payload.provider.name} is ${payload.provider.status}. Start the worker with this wallet to process tasks.`);
//       await refresh();
//     } catch (err) {
//       setError((err as Error).message);
//     } finally {
//       setBusy(false);
//     }
//   }

//   return (
//     <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
//       <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
//         <div>
//           <p className="text-sm font-black uppercase text-ember">Compute provider dashboard</p>
//           <h1 className="mt-2 text-3xl font-black text-white sm:text-5xl">Register available compute</h1>
//           <p className="mt-3 max-w-2xl text-slate-300">Providers publish a wallet, price, and status. The worker uses the same wallet to claim assigned tasks.</p>
//         </div>
//         <WalletMultiButton />
//       </div>

//       <div className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
//         <form onSubmit={submit} className="rounded-md border border-line bg-panel/80 p-5 shadow-glow">
//           <Field label="Provider name" icon={Cpu}>
//             <input value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember" />
//           </Field>
//           <Field label="Provider wallet" icon={WalletCards}>
//             <input value={walletAddress} onChange={(event) => setWalletAddress(event.target.value)} className="w-full rounded-md border border-line bg-ink px-3 py-3 font-mono text-sm text-white outline-none transition focus:border-ember" placeholder="Solana wallet public key" />
//           </Field>
//           <Field label="Compute type" icon={Gauge}>
//             <select value={computeType} onChange={(event) => setComputeType(event.target.value as ComputeType)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember">
//               <option value="CPU">CPU</option>
//               <option value="GPU_SIMULATED">GPU simulated</option>
//               <option value="GENERAL">General</option>
//             </select>
//           </Field>
//           <div className="grid gap-4 sm:grid-cols-2">
//             <Field label="Price per task" icon={Gauge}>
//               <input type="number" min={0.000001} step={0.001} value={pricePerTaskSol} onChange={(event) => setPricePerTaskSol(Number(event.target.value))} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember" />
//             </Field>
//             <Field label="Status" icon={Signal}>
//               <select value={status} onChange={(event) => setStatus(event.target.value as ProviderStatus)} className="w-full rounded-md border border-line bg-ink px-3 py-3 text-sm text-white outline-none transition focus:border-ember">
//                 <option value="online">Online</option>
//                 <option value="offline">Offline</option>
//               </select>
//             </Field>
//           </div>

//           {notice && <p className="mt-4 rounded-md border border-mint/40 bg-mint/10 p-3 text-sm font-bold text-mint">{notice}</p>}
//           {error && <p className="mt-4 rounded-md border border-red-400/50 bg-red-400/10 p-3 text-sm font-bold text-red-300">{error}</p>}

//           <button disabled={busy} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-ember px-5 py-3 font-black text-ink transition hover:bg-coral disabled:cursor-not-allowed disabled:opacity-45">
//             {busy ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />}
//             Register provider
//           </button>
//         </form>

//         <div className="rounded-md border border-line bg-panel/80 p-5">
//           <div className="flex items-center justify-between gap-4 border-b border-line pb-4">
//             <div>
//               <p className="font-black text-white">Provider pool</p>
//               <p className="text-sm text-slate-400">Stored locally for the MVP</p>
//             </div>
//             <span className="rounded-md border border-line px-3 py-1 text-sm font-black text-slate-300">{providers.length} total</span>
//           </div>
//           <div className="mt-5 space-y-3">
//             {providers.length === 0 ? (
//               <p className="rounded-md border border-line bg-ink/70 p-5 text-center text-slate-400">No providers registered.</p>
//             ) : (
//               providers.map((provider) => (
//                 <div key={provider.id} className="rounded-md border border-line bg-ink/70 p-4">
//                   <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
//                     <div className="min-w-0">
//                       <p className="break-words text-lg font-black text-white">{provider.name}</p>
//                       <p className="mt-1 font-mono text-xs text-slate-500">{shortAddress(provider.walletAddress)}</p>
//                     </div>
//                     <span className={`rounded-md border px-2.5 py-1 text-xs font-black uppercase ${provider.status === "online" ? "border-mint/50 bg-mint/10 text-mint" : "border-slate-500/50 bg-slate-500/10 text-slate-300"}`}>
//                       {provider.status}
//                     </span>
//                   </div>
//                   <div className="mt-4 grid gap-3 sm:grid-cols-3">
//                     <SmallStat label="Compute" value={provider.computeType.replace("_", " ")} />
//                     <SmallStat label="Price" value={`${provider.pricePerTaskSol.toFixed(4)} SOL`} />
//                     <SmallStat label="Updated" value={new Date(provider.updatedAt).toLocaleTimeString()} />
//                   </div>
//                 </div>
//               ))
//             )}
//           </div>
//         </div>
//       </div>
//     </section>
//   );
// }

// function Field({ label, icon: Icon, children }: { label: string; icon: typeof Cpu; children: React.ReactNode }) {
//   return (
//     <label className="mt-4 block">
//       <span className="mb-2 flex items-center gap-2 text-sm font-black text-slate-200"><Icon size={16} className="text-ember" />{label}</span>
//       {children}
//     </label>
//   );
// }

// function SmallStat({ label, value }: { label: string; value: string }) {
//   return (
//     <div className="min-w-0 rounded-md border border-line bg-panel/60 p-3">
//       <p className="text-xs font-bold uppercase text-slate-500">{label}</p>
//       <p className="mt-1 break-words font-black text-white">{value}</p>
//     </div>
//   );
// }
