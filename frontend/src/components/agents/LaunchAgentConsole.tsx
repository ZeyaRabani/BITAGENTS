"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { Panel } from "@/components/AppShell";
import { AgentCard } from "@/components/agents/AgentCard";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchLaunchConfig,
  fetchLaunchedAgent,
  launchAgent,
  listLaunchedAgents,
  updateLaunchedAgent,
  type LaunchConfig,
  type LaunchedAgent,
} from "@/lib/launchAgentClient";
import { LAUNCH_COST_SOL, LAUNCH_MODULES, type LaunchModule } from "@/lib/launchAgentModules";
import { buildLaunchPreviewAgent } from "@/lib/launchMarketplace";

const CATEGORY_LABEL: Record<LaunchModule["category"], string> = {
  data: "Data & research",
  wallet: "Wallet",
  trading: "Trading",
  infra: "Infrastructure",
};

export function LaunchAgentConsole({ editId }: { editId?: string }) {
  const { connection } = useConnection();
  const { publicKey, connected, sendTransaction } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();

  const [config, setConfig] = useState<LaunchConfig | null>(null);
  const [agents, setAgents] = useState<LaunchedAgent[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [task, setTask] = useState("");
  const [visibility, setVisibility] = useState<"public" | "private">("private");
  const [pricePerMonth, setPricePerMonth] = useState("");
  const [selectedModules, setSelectedModules] = useState<string[]>([]);
  const [launchBusy, setLaunchBusy] = useState(false);
  const [launchPhase, setLaunchPhase] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [launchSuccess, setLaunchSuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(editId?.trim() || null);

  const feeSol = typeof config?.fee_sol === "number" ? config.fee_sol : LAUNCH_COST_SOL;
  const feeFree =
    config?.mode === "development" ||
    config?.payment_required === false ||
    feeSol <= 0;
  const feeWallet = config?.fee_wallet ?? null;
  const cluster = config?.cluster;

  const modulesByCategory = useMemo(() => {
    const groups: Record<LaunchModule["category"], LaunchModule[]> = {
      data: [],
      wallet: [],
      trading: [],
      infra: [],
    };
    for (const mod of LAUNCH_MODULES) {
      groups[mod.category].push(mod);
    }
    return groups;
  }, []);

  const previewAgent = useMemo(
    () =>
      buildLaunchPreviewAgent({
        name,
        description,
        task,
        visibility,
        pricePerMonth,
      }),
    [name, description, task, visibility, pricePerMonth]
  );

  const selectedModuleNames = useMemo(
    () =>
      LAUNCH_MODULES.filter((m) => selectedModules.includes(m.id)).map((m) => m.name),
    [selectedModules]
  );

  useEffect(() => {
    void fetchLaunchConfig().then(setConfig);
  }, []);

  useEffect(() => {
    if (!token || !editingId) return;
    void fetchLaunchedAgent(editingId, token)
      .then(({ agent }) => {
        setName(agent.name);
        setDescription(agent.description);
        setTask(agent.task);
        setVisibility(agent.visibility);
        setPricePerMonth(
          agent.price_per_month_sol != null ? String(agent.price_per_month_sol) : ""
        );
        setSelectedModules(agent.modules);
      })
      .catch((err) => {
        setLaunchError(err instanceof Error ? err.message : "Failed to load agent");
      });
  }, [token, editingId]);

  useEffect(() => {
    if (!token) {
      setAgents([]);
      return;
    }
    void listLaunchedAgents(token)
      .then(setAgents)
      .catch(() => setAgents([]));
  }, [token]);

  function toggleModule(id: string) {
    setSelectedModules((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function refreshAgents(authToken: string) {
    try {
      setAgents(await listLaunchedAgents(authToken));
    } catch {
      /* ignore list refresh errors after a successful launch */
    }
  }

  async function onLaunch(e: FormEvent) {
    e.preventDefault();
    setLaunchError(null);
    setLaunchSuccess(null);
    setLastTx(null);

    if (!connected || !publicKey) {
      setLaunchError("Connect your wallet first.");
      return;
    }
    if (!isAuthenticated || !token) {
      setLaunchError("Approve the wallet sign-in message before launching.");
      return;
    }
    if (!name.trim()) {
      setLaunchError("Agent name is required.");
      return;
    }
    if (!task.trim()) {
      setLaunchError("Describe what the agent can do in Agent task.");
      return;
    }
    if (selectedModules.length === 0) {
      setLaunchError("Select at least one module.");
      return;
    }

    let monthlyPrice: number | null = null;
    if (visibility === "public") {
      const parsed = Number(pricePerMonth);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        setLaunchError("Public agents need a price per month greater than 0 SOL.");
        return;
      }
      monthlyPrice = parsed;
    }

    setLaunchBusy(true);

    try {
      if (editingId) {
        setLaunchPhase("Saving changes…");
        const result = await updateLaunchedAgent(
          editingId,
          {
            name: name.trim(),
            description: description.trim(),
            task: task.trim(),
            modules: selectedModules,
            visibility,
            price_per_month_sol: monthlyPrice,
          },
          token
        );
        setLaunchSuccess(result.message ?? `Agent "${name.trim()}" relaunched.`);
        await refreshAgents(token);
        return;
      }

      const latest = (await fetchLaunchConfig()) ?? config;
      const latestFee =
        typeof latest?.fee_sol === "number" ? latest.fee_sol : LAUNCH_COST_SOL;
      const skipPayment =
        latest?.mode === "development" ||
        latest?.payment_required === false ||
        latestFee <= 0;
      const latestFeeWallet = latest?.fee_wallet ?? feeWallet;

      let signature = "";
      if (!skipPayment) {
        if (!latestFeeWallet) {
          throw new Error(
            "Launch fee wallet is not configured on the API. Set LAUNCH_FEE_WALLET (or TREASURY_PUBLIC_KEY)."
          );
        }
        setLaunchPhase("Preparing transaction…");
        const feePk = new PublicKey(latestFeeWallet);
        const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
        const tx = new Transaction().add(
          SystemProgram.transfer({
            fromPubkey: publicKey,
            toPubkey: feePk,
            lamports: Math.round(latestFee * LAMPORTS_PER_SOL),
          })
        );
        tx.recentBlockhash = blockhash;
        tx.feePayer = publicKey;

        setLaunchPhase("Approve in wallet…");
        signature = await sendTransaction(tx, connection);
        setLastTx(signature);

        setLaunchPhase("Confirming on-chain…");
        await connection.confirmTransaction(
          { signature, blockhash, lastValidBlockHeight },
          "confirmed"
        );
        setLaunchPhase("Verifying fee and saving agent…");
      } else {
        setLaunchPhase("Saving agent…");
      }

      const result = await launchAgent(
        {
          name: name.trim(),
          description: description.trim(),
          task: task.trim(),
          modules: selectedModules,
          signature,
          visibility,
          price_per_month_sol: monthlyPrice,
        },
        token
      );

      setLaunchSuccess(result.message ?? `Agent "${name.trim()}" launched.`);
      setName("");
      setDescription("");
      setTask("");
      setVisibility("private");
      setPricePerMonth("");
      setSelectedModules([]);
      await refreshAgents(token);
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : "Launch failed");
    } finally {
      setLaunchBusy(false);
      setLaunchPhase(null);
    }
  }

  const canSubmit = !launchBusy;

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {editingId ? (
            <>
              Update this agent&apos;s name, task, modules, or listing. Saving relaunches it
              with no extra launch fee.
            </>
          ) : (
            <>
              Compose a new agent: name it, describe its job, pick the modules it needs
              {feeFree ? (
                <>
                  , then launch for{" "}
                  <strong className="text-foreground">0 SOL</strong> (development mode).
                </>
              ) : (
                <>
                  , then pay the{" "}
                  <strong className="text-foreground">{feeSol} SOL</strong> launch fee.
                </>
              )}{" "}
              You must connect your wallet and sign the auth message before launch.
            </>
          )}
        </p>
        {editingId && (
          <Link
            href="/agents/launch"
            className="mt-3 inline-block font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline"
          >
            Cancel edit · launch new
          </Link>
        )}
        {!feeFree && feeWallet && (
          <p className="mt-2 font-mono text-[10px] text-muted-foreground">
            Fee wallet: {feeWallet.slice(0, 4)}…{feeWallet.slice(-4)}
            {cluster ? ` · ${cluster}` : ""}
          </p>
        )}
        {config && !config.configured && !feeFree && (
          <p className="mt-2 font-mono text-[11px] text-warn">
            Launch fee wallet not configured on the agents API.
          </p>
        )}
      </div>

      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {!connected && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet in the navbar to continue.
        </div>
      )}

      {connected && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to authenticate before launching an agent.
        </div>
      )}

      {connected && !isAuthenticated && !authBusy && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet connected - wait for the sign-in prompt, or reconnect if it was dismissed.
        </div>
      )}

      <form onSubmit={onLaunch} className="space-y-6">
        <Panel title="Agent identity">
          <div className="space-y-4">
            <div>
              <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Agent name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Sol News Scout"
                disabled={launchBusy}
                className="w-full border border-grid bg-background px-3 py-2.5 font-mono text-sm disabled:opacity-50"
              />
            </div>
            <div>
              <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Agent description
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Short summary shown on the marketplace"
                disabled={launchBusy}
                className="w-full border border-grid bg-background px-3 py-2.5 font-mono text-sm disabled:opacity-50"
              />
            </div>
            <div>
              <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Agent task
              </label>
              <textarea
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Describe what this agent can do - capabilities, workflows, constraints…"
                disabled={launchBusy}
                rows={6}
                className="w-full resize-y border border-grid bg-background px-3 py-2.5 font-mono text-sm leading-relaxed disabled:opacity-50"
              />
              <p className="mt-2 text-xs text-muted-foreground">
                This is the capability brief the agent will follow (similar to custom instructions +
                tool scope).
              </p>
            </div>
          </div>
        </Panel>

        <Panel title="Visibility · pricing">
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Private agents stay on your account only. Public agents can be listed for others with
              a monthly SOL price.
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                disabled={launchBusy}
                onClick={() => {
                  setVisibility("private");
                  setPricePerMonth("");
                }}
                className={`border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  visibility === "private"
                    ? "border-signal bg-signal/10"
                    : "border-grid bg-surface/30 hover:border-signal/50"
                }`}
              >
                <div className="font-mono text-xs font-semibold uppercase tracking-[0.12em]">
                  Private
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  Only you can use this agent. No monthly price.
                </p>
              </button>
              <button
                type="button"
                disabled={launchBusy}
                onClick={() => setVisibility("public")}
                className={`border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  visibility === "public"
                    ? "border-signal bg-signal/10"
                    : "border-grid bg-surface/30 hover:border-signal/50"
                }`}
              >
                <div className="font-mono text-xs font-semibold uppercase tracking-[0.12em]">
                  Public
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  List it for others and set a monthly subscription price in SOL.
                </p>
              </button>
            </div>

            {visibility === "public" && (
              <div>
                <label className="mb-2 block font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Price per month (SOL)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={pricePerMonth}
                  onChange={(e) => setPricePerMonth(e.target.value)}
                  placeholder="e.g. 0.5"
                  disabled={launchBusy}
                  className="w-full max-w-xs border border-grid bg-background px-3 py-2.5 font-mono text-sm disabled:opacity-50"
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Required for public agents. Subscription billing is stored now; charging users can
                  come later.
                </p>
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title="Modules · connectors"
          action={
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {selectedModules.length} selected
            </span>
          }
        >
          <p className="mb-4 text-sm text-muted-foreground">
            Choose what this agent needs - data feeds, wallet access, trading rails, and infra.
          </p>
          <div className="space-y-6">
            {(Object.keys(modulesByCategory) as LaunchModule["category"][]).map((cat) => (
              <div key={cat}>
                <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-signal">
                  {CATEGORY_LABEL[cat]}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {modulesByCategory[cat].map((mod) => {
                    const active = selectedModules.includes(mod.id);
                    return (
                      <button
                        key={mod.id}
                        type="button"
                        disabled={launchBusy}
                        onClick={() => toggleModule(mod.id)}
                        className={`border px-3 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
                          active
                            ? "border-signal bg-signal/10"
                            : "border-grid bg-surface/30 hover:border-signal/50"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-mono text-xs font-semibold uppercase tracking-[0.12em] text-foreground">
                            {mod.name}
                          </span>
                          <span
                            className={`mt-0.5 h-3.5 w-3.5 shrink-0 border ${
                              active ? "border-signal bg-signal" : "border-grid bg-transparent"
                            }`}
                          />
                        </div>
                        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                          {mod.description}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Marketplace preview">
          <p className="mb-4 text-sm text-muted-foreground">
            This is how your agent will appear on the marketplace
            {visibility === "public"
              ? " after you publish (public listing)."
              : " if you switch to public later. Private agents stay on your account only."}
          </p>
          <div className="max-w-md">
            <AgentCard agent={previewAgent} preview />
          </div>
          {selectedModuleNames.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {selectedModuleNames.map((label) => (
                <span
                  key={label}
                  className="border border-grid px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
          {task.trim() && (
            <div className="mt-4 border-t border-grid pt-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Agent task
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {task.trim()}
              </p>
            </div>
          )}
        </Panel>

        <Panel title={editingId ? "Relaunch" : "Launch cost"}>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                {editingId ? "Save changes" : "Required payment"}
              </div>
              <div className="mt-2 font-display text-3xl font-bold tabular-nums text-signal">
                {editingId ? "0 SOL" : `${feeSol} SOL`}
              </div>
              <p className="mt-2 max-w-md text-sm text-muted-foreground">
                {editingId
                  ? "Editing does not charge another launch fee. Your existing listing is updated in place."
                  : feeFree
                    ? "Development mode: no on-chain transfer. The API saves your agent definition at 0 SOL."
                    : `Launching sends ${feeSol} SOL to the fee wallet. The API verifies the transfer, then saves your agent definition.`}
              </p>
              {launchPhase && (
                <p className="mt-2 font-mono text-[11px] text-muted-foreground">{launchPhase}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={!canSubmit}
              className="bg-signal px-6 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {launchBusy
                ? editingId
                  ? "Saving…"
                  : "Launching…"
                : editingId
                  ? "Relaunch agent"
                  : feeFree
                    ? "Launch · 0 SOL"
                    : `Launch · ${feeSol} SOL`}
            </button>
          </div>
        </Panel>

        {launchError && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            {launchError}
          </div>
        )}
        {launchSuccess && (
          <div className="border border-signal/40 bg-signal/10 px-4 py-3 font-mono text-xs text-signal">
            {launchSuccess}
            {lastTx && (
              <a
                href={explorerUrlForSignature(lastTx, cluster)}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 block break-all text-[10px] underline hover:text-foreground"
              >
                {lastTx} ↗
              </a>
            )}
          </div>
        )}
      </form>

      {isAuthenticated && (
        <Panel title="Your launched agents">
          {agents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No launched agents yet.</p>
          ) : (
            <div className="space-y-3">
              {agents.map((agent) => (
                <div key={agent.id} className="border border-grid bg-surface/30 px-3 py-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-mono text-sm font-semibold text-foreground">
                      {agent.name}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      {agent.visibility}
                      {agent.visibility === "public" && agent.price_per_month_sol != null
                        ? ` · ${agent.price_per_month_sol} SOL/mo`
                        : ""}{" "}
                      · {agent.status} · {agent.fee_sol} SOL
                    </span>
                  </div>
                  {agent.description && (
                    <p className="mt-1 text-xs text-muted-foreground">{agent.description}</p>
                  )}
                  <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{agent.task}</p>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <Link
                      href={`/agents/launch?edit=${agent.id}`}
                      className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline"
                    >
                      Edit / relaunch
                    </Link>
                    <Link
                      href={`/agents/launched/${agent.id}`}
                      className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-signal"
                    >
                      Open agent
                    </Link>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {agent.modules.map((mid) => (
                      <span
                        key={mid}
                        className="border border-grid px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
                      >
                        {mid}
                      </span>
                    ))}
                  </div>
                  {agent.explorer_url && (
                    <a
                      href={agent.explorer_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-block font-mono text-[10px] text-signal hover:underline"
                    >
                      Fee tx ↗
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
