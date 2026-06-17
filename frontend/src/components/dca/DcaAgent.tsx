"use client";

import {
  JUPITER_MIN_ORDER_USD,
  WSOL_MINT,
  makeExplorerTxUrl,
  type DcaPlan
} from "@bitagents/shared";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { useWalletModal } from "@solana/wallet-adapter-react-ui";
import { ArrowUp, Bot, Loader2, ShieldCheck, Sparkles, Wallet, Zap } from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useNetwork } from "@/components/NetworkProvider";
import { ActionButton, Panel, Tag } from "@/components/primitives";
import { AgentWalletBot } from "@/components/dca/AgentWalletBot";
import { PlanCard } from "@/components/dca/PlanCard";
import { PlanPreview } from "@/components/dca/PlanPreview";
import { useDcaWallet } from "@/components/dca/useDcaWallet";
import { createDcaPlan, executeDcaPlan, marketBuy, parseDcaMessage } from "@/lib/dca";
import { sendAndConfirmBase64Transaction, signBase64Transaction } from "@/lib/solana";
import { cn } from "@/lib/utils";

function trimAmount(value: number, max = 6): string {
  if (!Number.isFinite(value)) return "0";
  return value.toFixed(max).replace(/\.?0+$/, "");
}

const URL_SPLIT_PATTERN = /(https?:\/\/[^\s]+)/g;

/** Render chat text with any URLs as clickable links (e.g. Solana Explorer). */
function renderMessageText(text: string) {
  const parts = text.split(URL_SPLIT_PATTERN);
  return parts.map((part, index) =>
    /^https?:\/\//.test(part) ? (
      <a
        key={`${part}-${index}`}
        href={part}
        target="_blank"
        rel="noreferrer"
        className="text-signal underline underline-offset-2 hover:text-signal-soft"
      >
        {part}
      </a>
    ) : (
      <Fragment key={`t-${index}`}>{part}</Fragment>
    )
  );
}

const EXAMPLES = [
  "Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total",
  "Buy BITAGENTS every 1 minute with 0.01 SOL for 3 buys",
  "Buy SOL every day with 10 USDC for 30 days",
  "Buy iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY every hour with 0.05 SOL for 10 buys"
];

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  text: string;
}

interface Fallback {
  reason: string;
  plan: DcaPlan;
}

let messageCounter = 0;
function makeMessage(role: "user" | "agent", text: string): ChatMessage {
  messageCounter += 1;
  return { id: `m${messageCounter}-${Date.now()}`, role, text };
}

const GREETING =
  "Tell me what token to buy, how much to spend, and how often. For example: \"Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total.\" I'll turn it into a buy plan for you to confirm — and you can always make a one-time \"Buy now\" purchase (no minimum) instead.";

export function DcaAgent() {
  const [messages, setMessages] = useState<ChatMessage[]>([makeMessage("agent", GREETING)]);
  const [input, setInput] = useState("");
  const [parsing, setParsing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [buying, setBuying] = useState(false);
  const [draft, setDraft] = useState<DcaPlan | null>(null);
  const [fallback, setFallback] = useState<Fallback | null>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [agentBot, setAgentBot] = useState<DcaPlan | null>(null);

  const { network, dcaModeLabel, mainnetDcaEnabled, config } = useNetwork();
  const wallet = useDcaWallet();
  const { signTransaction, sendTransaction } = useWallet();
  const { connection } = useConnection();
  const { setVisible } = useWalletModal();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, parsing]);

  const pushAgent = useCallback((text: string) => {
    setMessages((prev) => [...prev, makeMessage("agent", text)]);
  }, []);

  const submit = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (!message || parsing) return;
      setMessages((prev) => [...prev, makeMessage("user", message)]);
      setInput("");
      setDraft(null);
      setFallback(null);
      setParsing(true);
      try {
        const result = await parseDcaMessage({
          message,
          walletAddress: wallet.address ?? undefined,
          network
        });
        if (result.ok) {
          setDraft(result.plan);
          pushAgent(
            `Got it. I planned ${result.plan.numberOfOrders} buys of ${result.plan.perOrderAmountUi} ${result.plan.inputSymbol} into ${result.plan.outputSymbol}. Review the plan on the right and confirm to create it.`
          );
        } else {
          pushAgent(result.clarification ?? result.error ?? "I couldn't parse that. Try rephrasing.");
        }
      } catch (error) {
        pushAgent((error as Error).message);
      } finally {
        setParsing(false);
      }
    },
    [network, parsing, pushAgent, wallet.address]
  );

  const create = useCallback(
    async (plan: DcaPlan, forceNetwork?: "devnet" | "mainnet") => {
      const useNetworkValue = forceNetwork ?? network;
      if (!wallet.address) {
        toast.error("Wallet not ready yet — try again in a moment.");
        return;
      }
      // Mainnet Safe Mode needs a real connected wallet to sign.
      if (plan.executionMode === "jupiter_recurring" && !wallet.connected) {
        toast.error("Connect your wallet to create a mainnet order.");
        setVisible(true);
        return;
      }
      setConfirming(true);
      setFallback(null);
      try {
        const result = await createDcaPlan({ plan, walletAddress: wallet.address, network: useNetworkValue });
        if (!result.ok) {
          if (result.minOrder && result.plan) {
            // Small plans can't use Jupiter Recurring (~$50/buy floor). When the
            // agent-wallet auto-DCA is enabled and the plan is SOL-funded, route
            // straight into it instead of dead-ending on a rejection.
            if (config.enableAgentWalletMode && result.plan.inputMint === WSOL_MINT) {
              setDraft(null);
              setFallback(null);
              setAgentBot(result.plan);
              pushAgent(
                `This buy (${trimAmount(result.plan.perOrderAmountUi)} ${result.plan.inputSymbol} per order) is below Jupiter Recurring's ~$${JUPITER_MIN_ORDER_USD} minimum, so I set it up as an agent-wallet auto-DCA instead — that path has no minimum. Fund the agent wallet on the right and it buys on your schedule.`
              );
              return;
            }
            setFallback({
              reason:
                result.jupiterError ??
                `Jupiter Recurring needs ~${JUPITER_MIN_ORDER_USD} USDC per buy. For a small amount like this, use "Buy now" (one-time, no minimum) or increase the per-buy size.`,
              plan: result.plan
            });
            pushAgent(
              "This buy is below Jupiter Recurring's ~$50/buy minimum — that's a Jupiter rule, not an error. You can buy it once now (no minimum) with the button on the right, increase the per-buy size, or run it in Devnet Demo Mode."
            );
          } else {
            pushAgent(result.jupiterError ?? result.error ?? result.clarification ?? "Could not create the plan.");
          }
          return;
        }

        if (result.mode === "jupiter_recurring") {
          if (!signTransaction) {
            toast.error("Wallet cannot sign transactions.");
            return;
          }
          pushAgent("Please approve the transaction in your wallet to activate the recurring order.");
          const signedTransaction = await signBase64Transaction({ base64: result.transaction, signTransaction });
          const executed = await executeDcaPlan(result.plan.id, {
            signedTransaction,
            requestId: result.requestId
          });
          if (!executed.ok) {
            pushAgent(executed.error ?? "Jupiter could not activate the order.");
            return;
          }
          setActivePlanId(result.plan.id);
          setDraft(null);
          pushAgent("Your recurring order is live on mainnet. Track it under the active plan and in My Plans.");
        } else if (result.mode === "agent_wallet") {
          setActivePlanId(result.plan.id);
          setDraft(null);
          pushAgent(`Agent wallet created. Deposit ${result.plan.inputSymbol} to ${result.depositAddress} to fund it.`);
        } else {
          setActivePlanId(result.plan.id);
          setDraft(null);
          pushAgent(
            "Devnet Demo plan is active. I'll simulate each scheduled buy with real price reads — watch the executions stream in below."
          );
        }
      } catch (error) {
        pushAgent((error as Error).message);
      } finally {
        setConfirming(false);
      }
    },
    [config, network, pushAgent, setVisible, signTransaction, wallet.address, wallet.connected]
  );

  // One-time market buy via Jupiter's Swap API — no per-order minimum, so a
  // small purchase (e.g. 0.01 SOL of BITAGENTS) goes through immediately.
  const buyNow = useCallback(
    async (plan: DcaPlan) => {
      if (network !== "mainnet") {
        toast.error("Switch to Mainnet Safe Mode to make a real buy.");
        return;
      }
      if (!wallet.connected || !wallet.address) {
        toast.error("Connect your wallet to buy.");
        setVisible(true);
        return;
      }
      if (!sendTransaction) {
        toast.error("Wallet cannot send transactions.");
        return;
      }
      setBuying(true);
      try {
        const result = await marketBuy({
          walletAddress: wallet.address,
          network,
          outputMint: plan.outputMint,
          inputMint: plan.inputMint,
          amountUi: plan.perOrderAmountUi,
          slippageBps: plan.slippageBps
        });
        if (!result.ok) {
          pushAgent(result.error);
          return;
        }
        pushAgent(
          `Live quote: ${trimAmount(result.quote.inputAmountUi)} ${result.quote.inputSymbol} → ~${trimAmount(
            result.quote.outputAmountUi
          )} ${result.quote.outputSymbol}. Approve the swap in your wallet.`
        );
        const signature = await sendAndConfirmBase64Transaction({
          base64: result.transaction,
          connection,
          sendTransaction,
          lastValidBlockHeight: result.lastValidBlockHeight
        });
        setFallback(null);
        setDraft(null);
        pushAgent(
          `Done — bought ~${trimAmount(result.quote.outputAmountUi)} ${result.quote.outputSymbol}. View it on Solana Explorer: ${makeExplorerTxUrl(
            signature,
            "mainnet"
          )}`
        );
      } catch (error) {
        pushAgent((error as Error).message);
      } finally {
        setBuying(false);
      }
    },
    [connection, network, pushAgent, sendTransaction, setVisible, wallet.address, wallet.connected]
  );

  // Experimental Agent Wallet Mode: run the plan as a self-signing throwaway
  // wallet so small buys auto-execute on schedule (no Jupiter minimum, no
  // per-buy popup). The key stays in the browser; funds are user-swept.
  const launchAgentBot = useCallback(
    (plan: DcaPlan) => {
      if (network !== "mainnet") {
        toast.error("Switch to Mainnet Safe Mode to run an agent wallet bot.");
        return;
      }
      if (!wallet.connected || !wallet.address) {
        toast.error("Connect your wallet to set up an agent wallet.");
        setVisible(true);
        return;
      }
      if (plan.inputMint !== WSOL_MINT) {
        toast.error("The agent wallet bot currently funds buys with SOL only.");
        return;
      }
      setDraft(null);
      setFallback(null);
      setAgentBot(plan);
      pushAgent(
        "Agent wallet bot ready. I generated a throwaway wallet in your browser — fund it with a little SOL, then it auto-buys on schedule. Withdraw back to your wallet anytime."
      );
    },
    [network, pushAgent, setVisible, wallet.address, wallet.connected]
  );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <Panel
        title="dca.agent"
        badge={<Tag className="border-signal/40 text-signal">{dcaModeLabel}</Tag>}
        bodyClassName="flex h-[30rem] flex-col gap-3 p-0"
      >
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto px-4 py-4 sm:px-5">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "pixel-corners max-w-[85%] px-3 py-2 font-mono text-sm leading-relaxed",
                  message.role === "user"
                    ? "bg-signal/15 text-foreground"
                    : "border border-border bg-surface-2 text-foreground/90"
                )}
              >
                {renderMessageText(message.text)}
              </div>
            </div>
          ))}
          {parsing ? (
            <div className="flex items-center gap-2 font-mono text-xs text-signal-soft">
              <Loader2 className="animate-spin" size={14} /> planning…
            </div>
          ) : null}
        </div>

        <div className="border-t border-border px-4 py-3 sm:px-5">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => submit(example)}
                disabled={parsing}
                className="pixel-corners border border-border bg-surface-2 px-2 py-1 text-left font-mono text-[10px] text-muted-foreground transition hover:border-signal/50 hover:text-foreground disabled:opacity-50"
              >
                {example.length > 46 ? `${example.slice(0, 46)}…` : example}
              </button>
            ))}
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit(input);
            }}
            className="flex items-end gap-2"
          >
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit(input);
                }
              }}
              rows={1}
              placeholder="Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total"
              spellCheck={false}
              className="pixel-corners max-h-28 min-h-[2.5rem] w-full resize-none border border-border bg-background px-3 py-2.5 font-mono text-sm text-foreground outline-none transition focus:border-signal"
            />
            <ActionButton type="submit" disabled={parsing || !input.trim()} className="h-[2.5rem]">
              {parsing ? <Loader2 className="animate-spin" size={15} /> : <ArrowUp size={15} />}
            </ActionButton>
          </form>
        </div>
      </Panel>

      <div className="space-y-5">
        {agentBot && wallet.address ? (
          <AgentWalletBot plan={agentBot} userAddress={wallet.address} onExit={() => setAgentBot(null)} />
        ) : null}

        <Panel title="dca.plan.preview" bodyClassName="space-y-4">
          {draft ? (
            <>
              <PlanPreview plan={draft} />
              {!wallet.connected ? (
                <button
                  type="button"
                  onClick={() => setVisible(true)}
                  className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-signal hover:text-signal-soft"
                >
                  <Wallet size={13} /> connect wallet {draft.executionMode === "jupiter_recurring" ? "(required for mainnet)" : "(optional for demo)"}
                </button>
              ) : null}
              <ActionButton onClick={() => create(draft)} disabled={confirming || buying} className="w-full">
                {confirming ? <Loader2 className="animate-spin" size={15} /> : <ShieldCheck size={15} />}
                Create DCA Agent
              </ActionButton>
              {draft.executionMode === "jupiter_recurring" ? (
                <>
                  <ActionButton
                    variant="outline"
                    onClick={() => buyNow(draft)}
                    disabled={buying || confirming}
                    className="w-full"
                  >
                    {buying ? <Loader2 className="animate-spin" size={15} /> : <Zap size={15} />}
                    Buy {trimAmount(draft.perOrderAmountUi)} {draft.inputSymbol} of {draft.outputSymbol} now
                  </ActionButton>
                  <ActionButton
                    variant="outline"
                    onClick={() => launchAgentBot(draft)}
                    disabled={buying || confirming}
                    className="w-full"
                  >
                    <Bot size={15} /> Automate with an agent wallet
                  </ActionButton>
                </>
              ) : null}
              <p className="font-mono text-[10px] leading-relaxed text-muted-foreground">
                Nothing is created until you confirm. {draft.executionMode === "jupiter_recurring"
                  ? "“Create DCA Agent” uses Jupiter Recurring (≈$50/buy minimum); for a small amount it switches to the agent wallet automatically. “Buy now” is a one-time market swap with no minimum. Funds are never custodied."
                  : "Devnet Demo simulates executions; no real tokens are bought."}
              </p>
            </>
          ) : fallback ? (
            <div className="space-y-3">
              <div className="flex items-start gap-2 font-mono text-xs leading-relaxed text-warn">
                <Sparkles size={14} className="mt-0.5 shrink-0" /> {fallback.reason}
              </div>
              <PlanPreview plan={fallback.plan} />
              <ActionButton onClick={() => buyNow(fallback.plan)} disabled={buying} className="w-full">
                {buying ? <Loader2 className="animate-spin" size={15} /> : <Zap size={15} />}
                Buy {trimAmount(fallback.plan.perOrderAmountUi)} {fallback.plan.inputSymbol} of {fallback.plan.outputSymbol} now
              </ActionButton>
              <p className="font-mono text-[10px] leading-relaxed text-muted-foreground">
                A one-time market buy has no per-order minimum, so this small amount goes through. You sign it in your
                wallet — no funds are custodied.
              </p>
              <ActionButton
                variant="outline"
                onClick={() => launchAgentBot(fallback.plan)}
                disabled={confirming || buying}
                className="w-full"
              >
                <Bot size={15} /> Run it as an auto-bot (agent wallet)
              </ActionButton>
              <ActionButton
                variant="outline"
                onClick={() => create(fallback.plan, "devnet")}
                disabled={confirming || buying}
                className="w-full"
              >
                {confirming ? <Loader2 className="animate-spin" size={15} /> : null}
                Try recurring in Devnet Demo Mode
              </ActionButton>
            </div>
          ) : (
            <p className="font-mono text-sm text-muted-foreground">
              Your parsed plan will appear here. Send an instruction in the chat to get started.
              {!mainnetDcaEnabled ? " Mainnet Safe Mode is disabled on this deployment, so plans run as Devnet Demo." : ""}
            </p>
          )}
        </Panel>

        {activePlanId ? (
          <Panel title="dca.plan.active" bodyClassName="space-y-3">
            <PlanCard planId={activePlanId} />
          </Panel>
        ) : null}
      </div>
    </div>
  );
}
