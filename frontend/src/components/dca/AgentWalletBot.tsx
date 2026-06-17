"use client";

import {
  makeExplorerAddressUrl,
  makeExplorerTxUrl,
  shortAddress,
  type DcaPlan
} from "@bitagents/shared";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { Keypair } from "@solana/web3.js";
import {
  ArrowDownToLine,
  CheckCircle2,
  Copy,
  ExternalLink,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  Square,
  Wallet
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ActionButton, Panel, Tag } from "@/components/primitives";
import {
  AGENT_BOT_CAPS,
  clampAgentPlan,
  estimateFundingSol,
  fundAgentWallet,
  getOrCreateAgentKeypair,
  getSolBalance,
  signAndSendSwap,
  sweepAgentWallet
} from "@/lib/agentWallet";
import { marketBuy } from "@/lib/dca";
import { cn } from "@/lib/utils";

function trimAmount(value: number, max = 6): string {
  if (!Number.isFinite(value)) return "0";
  return value.toFixed(max).replace(/\.?0+$/, "");
}

type Phase = "fund" | "ready" | "running" | "completed" | "stopped";

interface BotExecution {
  index: number;
  status: "success" | "failed";
  signature: string | null;
  outputAmountUi: number | null;
  note: string;
  at: number;
}

export function AgentWalletBot({
  plan,
  userAddress,
  onExit
}: {
  plan: DcaPlan;
  userAddress: string;
  onExit: () => void;
}) {
  const { connection } = useConnection();
  const { sendTransaction } = useWallet();

  const clamped = useMemo(
    () =>
      clampAgentPlan({
        numberOfOrders: plan.numberOfOrders,
        perOrderAmountUi: plan.perOrderAmountUi,
        intervalSeconds: plan.intervalSeconds
      }),
    [plan]
  );
  const fundingSol = useMemo(
    () => estimateFundingSol(clamped.perOrderAmountUi, clamped.numberOfOrders),
    [clamped]
  );

  const [keypair, setKeypair] = useState<Keypair | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("fund");
  const [executions, setExecutions] = useState<BotExecution[]>([]);
  const [funding, setFunding] = useState(false);
  const [starting, setStarting] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  const runningRef = useRef(false);
  const ordersDoneRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const agentAddress = keypair?.publicKey.toBase58() ?? "";

  useEffect(() => {
    setKeypair(getOrCreateAgentKeypair(userAddress));
  }, [userAddress]);

  const refreshBalance = useCallback(async () => {
    if (!keypair) return;
    try {
      const bal = await getSolBalance(connection, keypair.publicKey);
      setBalance(bal);
      setPhase((current) =>
        current === "fund" && bal >= clamped.perOrderAmountUi ? "ready" : current
      );
    } catch {
      /* transient RPC error — leave balance as-is */
    }
  }, [clamped.perOrderAmountUi, connection, keypair]);

  useEffect(() => {
    if (keypair) void refreshBalance();
  }, [keypair, refreshBalance]);

  useEffect(() => {
    return () => {
      runningRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const addExecution = useCallback((execution: BotExecution) => {
    setExecutions((prev) => [...prev, execution]);
  }, []);

  const stop = useCallback(() => {
    runningRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
    setPhase((current) => (current === "running" ? "stopped" : current));
  }, []);

  const tick = useCallback(async () => {
    if (!runningRef.current || !keypair) return;
    if (ordersDoneRef.current >= clamped.numberOfOrders) {
      runningRef.current = false;
      setPhase("completed");
      return;
    }

    let bal: number;
    try {
      bal = await getSolBalance(connection, keypair.publicKey);
      setBalance(bal);
    } catch {
      timerRef.current = setTimeout(() => void tick(), clamped.intervalSeconds * 1000);
      return;
    }

    if (bal < clamped.perOrderAmountUi + 0.003) {
      addExecution({
        index: ordersDoneRef.current + 1,
        status: "failed",
        signature: null,
        outputAmountUi: null,
        note: "Not enough SOL in the agent wallet. Fund it, then start again.",
        at: Date.now()
      });
      stop();
      return;
    }

    const index = ordersDoneRef.current + 1;
    try {
      const result = await marketBuy({
        walletAddress: agentAddress,
        network: "mainnet",
        outputMint: plan.outputMint,
        inputMint: plan.inputMint,
        amountUi: clamped.perOrderAmountUi,
        slippageBps: plan.slippageBps
      });
      if (!result.ok) {
        addExecution({ index, status: "failed", signature: null, outputAmountUi: null, note: result.error, at: Date.now() });
      } else {
        const signature = await signAndSendSwap({
          base64: result.transaction,
          connection,
          keypair
        });
        ordersDoneRef.current = index;
        addExecution({
          index,
          status: "success",
          signature,
          outputAmountUi: result.quote.outputAmountUi,
          note: `Bought ~${trimAmount(result.quote.outputAmountUi)} ${result.quote.outputSymbol}`,
          at: Date.now()
        });
      }
    } catch (error) {
      addExecution({
        index,
        status: "failed",
        signature: null,
        outputAmountUi: null,
        note: (error as Error).message,
        at: Date.now()
      });
    }

    if (!runningRef.current) return;
    if (ordersDoneRef.current >= clamped.numberOfOrders) {
      runningRef.current = false;
      setPhase("completed");
      return;
    }
    timerRef.current = setTimeout(() => void tick(), clamped.intervalSeconds * 1000);
  }, [addExecution, agentAddress, clamped, connection, keypair, plan.inputMint, plan.outputMint, plan.slippageBps, stop]);

  const start = useCallback(() => {
    if (runningRef.current) return;
    runningRef.current = true;
    setPhase("running");
    void tick();
  }, [tick]);

  const fund = useCallback(async () => {
    if (!keypair) return;
    if (!sendTransaction) {
      toast.error("Wallet cannot send transactions.");
      return;
    }
    setFunding(true);
    try {
      const { PublicKey } = await import("@solana/web3.js");
      await fundAgentWallet({
        connection,
        from: new PublicKey(userAddress),
        to: keypair.publicKey,
        amountSol: fundingSol,
        sendTransaction
      });
      toast.success(`Funded the agent wallet with ${fundingSol} SOL.`);
      await refreshBalance();
      setPhase("ready");
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setFunding(false);
    }
  }, [connection, fundingSol, keypair, refreshBalance, sendTransaction, userAddress]);

  const withdraw = useCallback(async () => {
    if (!keypair) return;
    stop();
    setWithdrawing(true);
    try {
      const result = await sweepAgentWallet({
        connection,
        keypair,
        destination: userAddress,
        outputMint: plan.outputMint
      });
      if (!result.tokenSignature && !result.solSignature) {
        toast.info("Nothing to withdraw — the agent wallet is empty.");
      } else {
        toast.success("Swept funds back to your wallet.");
      }
      await refreshBalance();
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setWithdrawing(false);
    }
  }, [connection, keypair, plan.outputMint, refreshBalance, stop, userAddress]);

  const copyAddress = useCallback(() => {
    if (!agentAddress) return;
    void navigator.clipboard.writeText(agentAddress);
    toast.success("Agent wallet address copied.");
  }, [agentAddress]);

  const startWrap = useCallback(() => {
    setStarting(true);
    start();
    setStarting(false);
  }, [start]);

  return (
    <Panel
      title="agent.wallet.bot"
      badge={<Tag className="border-signal/40 text-signal">{phase}</Tag>}
      bodyClassName="space-y-4"
    >
      <div className="flex items-start gap-2 border border-warn/40 bg-warn/5 px-3 py-2 font-mono text-[11px] leading-relaxed text-warn">
        <ShieldAlert size={14} className="mt-0.5 shrink-0" />
        This is a hot wallet whose key lives only in your browser. Only fund the small test amount; withdraw anytime.
      </div>

      <div className="space-y-2 font-mono text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">agent wallet</span>
          <span className="flex items-center gap-2 text-foreground">
            {agentAddress ? shortAddress(agentAddress) : "…"}
            <button type="button" onClick={copyAddress} className="text-muted-foreground hover:text-signal" aria-label="Copy address">
              <Copy size={13} />
            </button>
            {agentAddress ? (
              <a
                href={makeExplorerAddressUrl(agentAddress, "mainnet")}
                target="_blank"
                rel="noreferrer"
                className="text-muted-foreground hover:text-signal"
                aria-label="View on Solana Explorer"
              >
                <ExternalLink size={13} />
              </a>
            ) : null}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">balance</span>
          <span className="flex items-center gap-2 text-foreground">
            {balance == null ? "…" : `${trimAmount(balance)} SOL`}
            <button type="button" onClick={() => void refreshBalance()} className="text-muted-foreground hover:text-signal" aria-label="Refresh balance">
              <RefreshCw size={13} />
            </button>
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">plan</span>
          <span className="text-foreground">
            {trimAmount(clamped.perOrderAmountUi)} SOL → {plan.outputSymbol} · {clamped.numberOfOrders}× · every{" "}
            {clamped.intervalSeconds}s
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted-foreground">progress</span>
          <span className="text-foreground">
            {ordersDoneRef.current}/{clamped.numberOfOrders} buys
          </span>
        </div>
      </div>

      {clamped.warnings.length > 0 ? (
        <ul className="space-y-1 font-mono text-[10px] leading-relaxed text-muted-foreground">
          {clamped.warnings.map((warning) => (
            <li key={warning}>· {warning}</li>
          ))}
        </ul>
      ) : null}

      <div className="space-y-2">
        {phase === "fund" ? (
          <ActionButton onClick={() => void fund()} disabled={funding} className="w-full">
            {funding ? <Loader2 className="animate-spin" size={15} /> : <Wallet size={15} />}
            Fund {fundingSol} SOL
          </ActionButton>
        ) : null}

        {phase === "ready" ? (
          <ActionButton onClick={startWrap} disabled={starting} className="w-full">
            {starting ? <Loader2 className="animate-spin" size={15} /> : <Play size={15} />}
            Start auto-buy ({clamped.numberOfOrders}× every {clamped.intervalSeconds}s)
          </ActionButton>
        ) : null}

        {phase === "running" ? (
          <ActionButton variant="outline" onClick={stop} className="w-full">
            <Square size={15} /> Stop
          </ActionButton>
        ) : null}

        {(phase === "stopped" || phase === "completed") && ordersDoneRef.current < clamped.numberOfOrders ? (
          <ActionButton onClick={start} className="w-full">
            <Play size={15} /> Resume
          </ActionButton>
        ) : null}

        <ActionButton variant="outline" onClick={() => void withdraw()} disabled={withdrawing} className="w-full">
          {withdrawing ? <Loader2 className="animate-spin" size={15} /> : <ArrowDownToLine size={15} />}
          Withdraw all to my wallet
        </ActionButton>
      </div>

      {executions.length > 0 ? (
        <div className="space-y-1.5 border-t border-border pt-3">
          {executions.map((execution) => (
            <div
              key={`${execution.index}-${execution.at}`}
              className="flex items-center justify-between gap-2 font-mono text-[11px]"
            >
              <span className={cn("flex items-center gap-1.5", execution.status === "success" ? "text-success" : "text-danger")}>
                <CheckCircle2 size={12} className={execution.status === "success" ? "" : "hidden"} />
                #{execution.index} {execution.note}
              </span>
              {execution.signature ? (
                <a
                  href={makeExplorerTxUrl(execution.signature, "mainnet")}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 text-signal underline underline-offset-2 hover:text-signal-soft"
                >
                  tx
                </a>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {phase === "completed" ? (
        <div className="flex items-center gap-2 font-mono text-xs text-success">
          <CheckCircle2 size={14} /> Done — {ordersDoneRef.current} buys complete. Withdraw your BITAGENTS + leftover SOL.
        </div>
      ) : null}

      <button
        type="button"
        onClick={onExit}
        className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground hover:text-foreground"
      >
        ← back to chat
      </button>
    </Panel>
  );
}
