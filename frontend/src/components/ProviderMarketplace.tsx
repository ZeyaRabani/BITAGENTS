"use client";

import {
  makeExplorerAddressUrl,
  shortAddress,
  type ComputeProvider,
  type ComputeType,
  type ProviderStatus
} from "@bitagents/shared";
import { useWallet } from "@solana/wallet-adapter-react";
import { useWalletModal } from "@solana/wallet-adapter-react-ui";
import bs58 from "bs58";
import { Cpu, Loader2, Server, Sparkles, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ActionButton, Panel, Tag } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

const COMPUTE_OPTIONS: { value: ComputeType; label: string; icon: typeof Cpu }[] = [
  { value: "CPU", label: "CPU", icon: Cpu },
  { value: "GPU_SIMULATED", label: "GPU (simulated)", icon: Server },
  { value: "LLM", label: "LLM endpoint", icon: Sparkles }
];

function buildRegistrationMessage(params: {
  wallet: string;
  name: string;
  computeType: ComputeType;
  price: number;
  status: ProviderStatus;
}) {
  return [
    "BITAGENTS Compute Provider Registration",
    "",
    `wallet: ${params.wallet}`,
    `name: ${params.name}`,
    `computeType: ${params.computeType}`,
    `pricePerTaskSol: ${params.price}`,
    `status: ${params.status}`,
    `timestamp: ${new Date().toISOString()}`
  ].join("\n");
}

export function ProviderMarketplace() {
  const { publicKey, signMessage, connected } = useWallet();
  const { setVisible } = useWalletModal();

  const [providers, setProviders] = useState<ComputeProvider[]>([]);
  const [name, setName] = useState("");
  const [computeType, setComputeType] = useState<ComputeType>("CPU");
  const [price, setPrice] = useState("0.001");
  const [status, setStatus] = useState<ProviderStatus>("online");
  const [endpoint, setEndpoint] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<{ providers: ComputeProvider[] }>("/api/providers");
      setProviders(data.providers);
    } catch {
      setProviders([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function register() {
    if (!connected || !publicKey || !signMessage) {
      toast.error("Connect a wallet that supports message signing.");
      setVisible(true);
      return;
    }
    if (!name.trim()) {
      toast.error("Enter a provider name.");
      return;
    }
    const priceNum = Number(price);
    if (!Number.isFinite(priceNum) || priceNum < 0 || priceNum > 5) {
      toast.error("Price must be between 0 and 5 SOL.");
      return;
    }

    setSubmitting(true);
    try {
      const message = buildRegistrationMessage({
        wallet: publicKey.toBase58(),
        name: name.trim(),
        computeType,
        price: priceNum,
        status
      });
      const signature = await signMessage(new TextEncoder().encode(message));
      const registrationSignature = bs58.encode(signature);

      await apiFetch<{ provider: ComputeProvider }>("/api/providers", {
        method: "POST",
        body: JSON.stringify({
          walletAddress: publicKey.toBase58(),
          name: name.trim(),
          computeType,
          pricePerTaskSol: priceNum,
          status,
          endpoint: endpoint.trim() || undefined,
          registrationSignature,
          registrationMessage: message
        })
      });
      toast.success("Provider registered.");
      await load();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <Panel title="provider.register" bodyClassName="space-y-4">
        <Field label="Provider name">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="edge-node-01"
            className="pixel-corners w-full border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground outline-none focus:border-signal"
          />
        </Field>

        <Field label="Compute type">
          <div className="grid grid-cols-3 gap-2">
            {COMPUTE_OPTIONS.map((option) => {
              const Icon = option.icon;
              const active = computeType === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setComputeType(option.value)}
                  className={cn(
                    "pixel-corners flex flex-col items-center gap-1.5 border px-2 py-3 text-center transition",
                    active ? "border-signal bg-signal/10 text-signal" : "border-border bg-surface-2 text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon size={16} />
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em]">{option.label}</span>
                </button>
              );
            })}
          </div>
        </Field>

        {computeType === "LLM" ? (
          <Field label="LLM endpoint (optional)">
            <input
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              placeholder="https://my-node.example/v1"
              className="pixel-corners w-full border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground outline-none focus:border-signal"
            />
          </Field>
        ) : null}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Price per task (SOL)">
            <input
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              inputMode="decimal"
              className="pixel-corners w-full border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground outline-none focus:border-signal"
            />
          </Field>
          <Field label="Status">
            <div className="pixel-corners inline-flex w-full border border-border bg-surface-2 p-0.5 font-mono text-[11px] uppercase tracking-[0.08em]">
              {(["online", "offline"] as ProviderStatus[]).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setStatus(value)}
                  className={cn(
                    "flex-1 px-2 py-1.5 transition",
                    status === value ? "bg-signal text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {value}
                </button>
              ))}
            </div>
          </Field>
        </div>

        {connected ? (
          <ActionButton onClick={register} disabled={submitting} className="w-full">
            {submitting ? <Loader2 className="animate-spin" size={15} /> : <Wallet size={15} />}
            Sign &amp; register provider
          </ActionButton>
        ) : (
          <ActionButton onClick={() => setVisible(true)} className="w-full">
            <Wallet size={15} /> Connect wallet to register
          </ActionButton>
        )}
        <p className="font-mono text-[11px] text-muted-foreground">
          Registration signs a message proving wallet ownership. No funds move during registration.
        </p>
      </Panel>

      <Panel title={`providers.online (${providers.filter((p) => p.status === "online").length})`} bodyClassName="space-y-3">
        {providers.length === 0 ? (
          <p className="py-8 text-center font-mono text-sm text-muted-foreground">
            No providers registered yet. Tasks fall back to BITAGENTS Local Compute.
          </p>
        ) : (
          providers.map((provider) => <ProviderCard key={provider.id} provider={provider} />)
        )}
      </Panel>
    </div>
  );
}

function ProviderCard({ provider }: { provider: ComputeProvider }) {
  return (
    <div className="pixel-corners border border-border bg-surface-2 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-sm font-semibold text-foreground">{provider.name}</p>
          <a
            href={makeExplorerAddressUrl(provider.walletAddress, "devnet")}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[11px] text-signal hover:text-signal-soft"
          >
            {shortAddress(provider.walletAddress)}
          </a>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]",
            provider.status === "online"
              ? "border-success/50 bg-success/10 text-success"
              : "border-border bg-surface text-muted-foreground"
          )}
        >
          {provider.status === "online" ? <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-current" /> : null}
          {provider.status}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Tag>{provider.computeType.replace("_", " ").toLowerCase()}</Tag>
        <Tag>{provider.pricePerTaskSol} SOL / task</Tag>
        <Tag>{provider.tasksCompleted} tasks</Tag>
        <Tag>rep {provider.reputation}</Tag>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
