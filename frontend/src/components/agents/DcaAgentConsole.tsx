"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { DcaAgentDeposit } from "@/components/agents/DcaAgentDeposit";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { useWallet } from "@solana/wallet-adapter-react";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import type { UserDepositBalances } from "@/lib/dcaWalletClient";
import {
  createDcaPlan,
  fetchStrategiesCatalog,
  getDcaPlan,
  getDcaPlanExecutions,
  listDcaPlans,
  previewDcaBuy,
  setDcaPlanStatus,
  updateDcaPlan,
  type StrategyConfiguration,
  type StrategyExecution,
  type StrategyPlan,
} from "@/lib/strategyClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  signature?: string;
};

type DraftConfig = StrategyConfiguration;

function executionSignature(run: StrategyExecution | Record<string, unknown> | null | undefined) {
  if (!run || typeof run !== "object") return "";
  const record = run as Record<string, unknown>;
  const nested =
    record.result && typeof record.result === "object"
      ? (record.result as Record<string, unknown>)
      : null;
  const signature =
    (typeof record.signature === "string" && record.signature) ||
    (typeof nested?.signature === "string" && nested.signature) ||
    (typeof nested?.receipt === "string" && nested.receipt) ||
    "";
  return signature.trim();
}

function executionSucceeded(run: StrategyExecution | Record<string, unknown> | null | undefined) {
  if (!run || typeof run !== "object") return false;
  const record = run as Record<string, unknown>;
  const nested =
    record.result && typeof record.result === "object"
      ? (record.result as Record<string, unknown>)
      : null;
  const status = String(record.status || nested?.status || "").toLowerCase();
  return status === "success" && Boolean(executionSignature(run));
}

function buySuccessMessage(planId: string, signature: string, outputToken: string) {
  return `Buy completed for plan ${planId}. ${outputToken} purchase landed on-chain. Open the explorer link below for the transaction.`;
}

const INTRO =
  "Create a recurring buy, check your plans, or adjust a schedule. Examples: “Buy BITAGENTS for 0.001 SOL for 1 time in next 5 sec” or “Buy 0.01 SOL of JUP daily for 2 buys”.";

const EXAMPLES = [
  "Buy BITAGENTS for 0.001 SOL for 1 time in next 5 sec",
  "Buy 0.01 SOL of JUP daily for 2 buys",
  "Preview next buy",
  "How is my strategy doing?",
  "Pause my plan",
];

function money(n: number | null | undefined) {
  const value = typeof n === "number" && Number.isFinite(n) ? n : 0;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}

function budgetFromAmount(amount: number, buys: number) {
  return Number((amount * buys * 1.005).toFixed(6));
}

function normalizeInterval(raw: string): string {
  const key = raw.trim().toLowerCase();
  if (key === "daily" || key === "day") return "1 day";
  if (key === "hourly" || key === "hour") return "1 hour";
  if (key === "weekly" || key === "week") return "1 week";
  return raw.trim();
}

function parseBuyCommand(prompt: string): DraftConfig | null {
  const text = prompt.trim().replace(/\s+/g, " ");

  // Buy BITAGENTS for 0.001 SOL for 1 time in next 5 sec
  let match =
    /^buy\s+([A-Za-z0-9]+)\s+for\s+(\d+(?:\.\d+)?)\s+([A-Za-z0-9]+)\s+for\s+(\d+)\s+times?(?:\s+in\s+(?:the\s+)?next\s+(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m))?\.?$/i.exec(
      text
    );
  if (match) {
    const output = match[1].toUpperCase();
    const amount = Number(match[2]);
    const input = match[3].toUpperCase();
    const buys = Number(match[4]);
    const soonAmount = match[5] ? Number(match[5]) : null;
    const soonUnit = (match[6] || "s").toLowerCase();
    const startSoon = soonAmount != null;
    const isMinutes = /^(minutes?|mins?|m)$/i.test(soonUnit);
    // “next 5 sec” => short interval + start now so the first buy can land quickly.
    const interval =
      startSoon && soonAmount != null
        ? `${soonAmount} ${isMinutes ? "minutes" : "seconds"}`
        : "1 day";
    return {
      name: `${input} → ${output}`,
      input_token: input,
      output_token: output,
      amount_per_buy: amount,
      interval,
      total_budget: budgetFromAmount(amount, buys),
      max_executions: buys,
      slippage_bps: 100,
      start_immediately: startSoon || buys === 1,
    };
  }

  // Buy 0.01 SOL of JUP daily for 2 buys
  match =
    /^buy\s+(\d+(?:\.\d+)?)\s+([A-Za-z0-9]+)\s+of\s+([A-Za-z0-9]+)\s+(?:every\s+)?(.+?)\s+for\s+(\d+)\s+buys?\.?$/i.exec(
      text
    );
  if (match) {
    const amount = Number(match[1]);
    const input = match[2].toUpperCase();
    const output = match[3].toUpperCase();
    const buys = Number(match[5]);
    const interval = normalizeInterval(match[4]);
    return {
      name: `${input} → ${output}`,
      input_token: input,
      output_token: output,
      amount_per_buy: amount,
      interval,
      total_budget: budgetFromAmount(amount, buys),
      max_executions: buys,
      slippage_bps: 100,
      start_immediately: false,
    };
  }

  // Buy BITAGENTS with 0.001 SOL once / now
  match =
    /^buy\s+([A-Za-z0-9]+)\s+(?:with|using)\s+(\d+(?:\.\d+)?)\s+([A-Za-z0-9]+)(?:\s+(once|now|(?:for\s+)?1\s+time))?\.?$/i.exec(
      text
    );
  if (match) {
    const output = match[1].toUpperCase();
    const amount = Number(match[2]);
    const input = match[3].toUpperCase();
    const immediate = Boolean(match[4]);
    return {
      name: `${input} → ${output}`,
      input_token: input,
      output_token: output,
      amount_per_buy: amount,
      interval: immediate ? "5 seconds" : "1 day",
      total_budget: budgetFromAmount(amount, 1),
      max_executions: 1,
      slippage_bps: 100,
      start_immediately: immediate,
    };
  }

  return null;
}

export function DcaAgentConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "intro", role: "assistant", content: INTRO },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eventLog, setEventLog] = useState<string[]>(["Connecting…"]);
  const [draft, setDraft] = useState<DraftConfig | null>(null);
  const [editing, setEditing] = useState(false);
  const [plan, setPlan] = useState<StrategyPlan | null>(null);
  const [executions, setExecutions] = useState<StrategyExecution[]>([]);
  const [previewNote, setPreviewNote] = useState<string | null>(null);
  const [userBalances, setUserBalances] = useState<UserDepositBalances | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const cluster = "mainnet";

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, draft, busy, plan]);

  useEffect(() => {
    if (!token) {
      setEventLog(["Sign in to connect the strategy service"]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const catalog = await fetchStrategiesCatalog(token);
        const strategies = (catalog.strategies as unknown[]) ?? [];
        if (!cancelled) {
          setEventLog([
            `${strategies.length} strategy available · DCA · live mainnet`,
            "Connected · /strategies/dca",
          ]);
        }
        const plans = await listDcaPlans(token);
        if (!cancelled && plans.length > 0) {
          const active =
            plans.find((item) => item.status === "active") ??
            plans.find((item) => item.status === "paused") ??
            plans[0];
          await refreshPlan(token, active.id);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Could not load strategies";
          setError(message);
          setEventLog([message]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, refreshTick]);

  function pushMessage(
    role: "user" | "assistant",
    content: string,
    extras?: { signature?: string }
  ) {
    setMessages((current) => [
      ...current,
      {
        id: `${role}-${Date.now()}-${current.length}`,
        role,
        content,
        signature: extras?.signature,
      },
    ]);
  }

  function log(line: string) {
    setEventLog((current) => [line, ...current].slice(0, 8));
  }

  function normalizePlan(raw: StrategyPlan): StrategyPlan {
    return {
      ...raw,
      amount_per_buy: Number(raw.amount_per_buy ?? 0),
      total_budget: Number(raw.total_budget ?? 0),
      max_executions: Number(raw.max_executions ?? 0),
      executions_count: Number(raw.executions_count ?? 0),
      spent_so_far: Number(raw.spent_so_far ?? 0),
      slippage_bps: Number(raw.slippage_bps ?? 100),
      next_execution_at: raw.next_execution_at || "",
      input_token: raw.input_token || "",
      output_token: raw.output_token || "",
      name: raw.name || raw.id,
      status: raw.status || "unknown",
    };
  }

  async function refreshPlan(authToken: string, planId: string) {
    const next = normalizePlan(await getDcaPlan(authToken, planId));
    const history = await getDcaPlanExecutions(authToken, planId);
    setPlan(next);
    setExecutions(history);
    log(`GET /strategies/dca/plans/${next.id} · ${next.status}`);
    return { plan: next, history };
  }

  async function waitForSuccessfulBuy(
    authToken: string,
    planId: string,
    outputToken: string,
    options?: { attempts?: number; delayMs?: number }
  ) {
    const attempts = options?.attempts ?? 24;
    const delayMs = options?.delayMs ?? 3000;
    for (let i = 0; i < attempts; i += 1) {
      const { history } = await refreshPlan(authToken, planId);
      const success = history.find((run) => executionSucceeded(run));
      const signature = success ? executionSignature(success) : "";
      if (signature) {
        pushMessage("assistant", buySuccessMessage(planId, signature, outputToken), {
          signature,
        });
        log(`Buy landed · ${signature.slice(0, 12)}…`);
        return signature;
      }
      if (i < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
    return null;
  }

  async function authorizeDraft() {
    if (!token || !draft) return;
    const pendingDraft = draft;
    setBusy(true);
    setError(null);
    try {
      if (editing && plan) {
        const { name: _n, input_token: _i, output_token: _o, ...changes } = pendingDraft;
        await updateDcaPlan(token, plan.id, changes);
        pushMessage("assistant", "Your limits are updated. Future runs use the saved configuration.");
        log(`PATCH /strategies/dca/plans/${plan.id}`);
        await refreshPlan(token, plan.id);
      } else {
        const created = await createDcaPlan(token, pendingDraft);
        const planId = created.plan?.id;
        const first = created.first_execution;
        const firstRecord =
          first && typeof first === "object" ? (first as Record<string, unknown>) : null;
        const firstError = firstRecord
          ? String(firstRecord.error || (firstRecord.execution_failed ? "swap failed" : "") || "")
          : "";
        const immediateSignature =
          firstRecord && executionSucceeded(firstRecord) ? executionSignature(firstRecord) : "";

        if (immediateSignature && planId) {
          pushMessage(
            "assistant",
            buySuccessMessage(planId, immediateSignature, pendingDraft.output_token),
            { signature: immediateSignature }
          );
          log(`POST /strategies/dca/plans · ${planId} · buy ${immediateSignature.slice(0, 12)}…`);
        } else if (firstError) {
          pushMessage(
            "assistant",
            `Plan ${planId} was saved, but the first buy did not land yet: ${firstError}. Watching the scheduler for a successful retry…`
          );
          log(`POST /strategies/dca/plans · ${planId} · first buy failed`);
        } else if (pendingDraft.start_immediately) {
          pushMessage(
            "assistant",
            `Plan ${planId} is live. Waiting for the first on-chain buy (Aomi gate, then Circle sign)…`
          );
          log(`POST /strategies/dca/plans · ${planId} · waiting for buy`);
        } else {
          pushMessage(
            "assistant",
            "Your plan is live within your approved limits. The Python scheduler runs buys on-chain after each interval (Aomi gate, then Circle sign). Ask to preview the next buy, check status, pause, or edit anytime."
          );
          log(`POST /strategies/dca/plans · ${planId}`);
        }

        if (planId) {
          await refreshPlan(token, planId);
          if (!immediateSignature && pendingDraft.start_immediately) {
            const landed = await waitForSuccessfulBuy(
              token,
              planId,
              pendingDraft.output_token
            );
            if (!landed) {
              pushMessage(
                "assistant",
                `Still waiting on plan ${planId}. Ask “How is my strategy doing?” in a moment, or check Agent actions / Solscan once the scheduler prints a success.`
              );
            }
          }
        }
      }
      setDraft(null);
      setEditing(false);
      setRefreshTick((tick) => tick + 1);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setError(message);
      pushMessage("assistant", message);
    } finally {
      setBusy(false);
    }
  }

  async function previewBuy(active: StrategyPlan) {
    if (!token) return;
    const result = await previewDcaBuy(token, active.id);
    const quote = `Preview: ${money(Number(result.input_amount ?? active.amount_per_buy))} ${active.input_token} buys approximately ${result.estimated_output ?? result.output_amount ?? "-"} ${active.output_token}, plus the 0.5% platform fee. No trade submitted. Live buys run on the scheduler.`;
    setPreviewNote(quote);
    pushMessage("assistant", quote);
    log(`POST /strategies/dca/run · preview`);
  }

  async function handleCommand(raw: string) {
    const prompt = raw.trim();
    if (!prompt) return;
    if (!token) {
      pushMessage("user", prompt);
      pushMessage("assistant", "Sign in with your wallet first, then fund the agent wallet.");
      return;
    }
    setBusy(true);
    setError(null);
    pushMessage("user", prompt);
    try {
      const command = prompt.toLowerCase();
      const parsed = parseBuyCommand(prompt);

      if (parsed) {
        setDraft(parsed);
        setEditing(false);
        pushMessage(
          "assistant",
          parsed.start_immediately
            ? "I’ve prepared a strategy. Review the limits below. Confirming can run the first buy immediately on mainnet from your deposit balance."
            : "I’ve prepared a recurring strategy. Review the limits below. It starts after one interval and stops at the budget or execution cap. This authorizes real mainnet buys from your deposit balance."
        );
        return;
      }

      if (!plan) {
        pushMessage(
          "assistant",
          'Try “Buy BITAGENTS for 0.001 SOL for 1 time in next 5 sec” or “Buy 0.01 SOL of JUP daily for 2 buys”. Deposit the input token first.'
        );
        return;
      }

      if (/preview/.test(command)) {
        await previewBuy(plan);
        return;
      }

      if (/pause/.test(command)) {
        await setDcaPlanStatus(token, plan.id, "pause");
        await refreshPlan(token, plan.id);
        pushMessage(
          "assistant",
          "Plan paused. Future buys are stopped; history remains available."
        );
        return;
      }

      if (/resume/.test(command)) {
        await setDcaPlanStatus(token, plan.id, "resume");
        await refreshPlan(token, plan.id);
        pushMessage(
          "assistant",
          "Plan resumed. An overdue buy may run on the next scheduler tick (real on-chain)."
        );
        return;
      }

      if (/edit|change/.test(command)) {
        setEditing(true);
        setDraft({
          name: plan.name,
          input_token: plan.input_token,
          output_token: plan.output_token,
          amount_per_buy: plan.amount_per_buy,
          interval: plan.interval,
          total_budget: plan.total_budget,
          max_executions: plan.max_executions,
          slippage_bps: plan.slippage_bps,
        });
        pushMessage("assistant", "Review the updated limits before authorizing changes.");
        return;
      }

      if (/doing|performance|status|profit|earned/.test(command)) {
        const { plan: current, history } = await refreshPlan(token, plan.id);
        const acquired = history.reduce(
          (sum, run) => sum + (run.result?.output_amount || 0),
          0
        );
        const latestSuccess = [...history].reverse().find((run) => executionSucceeded(run));
        const latestSignature = latestSuccess ? executionSignature(latestSuccess) : "";
        pushMessage(
          "assistant",
          `Your plan is ${current.status}: ${current.executions_count} of ${current.max_executions} buys completed. Spent ${money(current.spent_so_far)} / ${money(current.total_budget)} ${current.input_token}. Recorded output: ${acquired || 0} ${current.output_token}.${latestSignature ? " Latest successful buy is linked below." : ""}`,
          latestSignature ? { signature: latestSignature } : undefined
        );
        return;
      }

      pushMessage(
        "assistant",
        "You can ask: Preview next buy, How is my strategy doing?, Edit my plan, Pause my plan, or Resume my plan. Or create another plan like “Buy BITAGENTS for 0.001 SOL for 1 time in next 5 sec”."
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setError(message);
      pushMessage("assistant", message);
    } finally {
      setBusy(false);
      setInput("");
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void handleCommand(input);
  }

  const availableBalance = useMemo(() => {
    if (!userBalances?.balances?.length) return null;
    if (plan) {
      const row = userBalances.balances.find(
        (item) => item.token.toUpperCase() === plan.input_token.toUpperCase()
      );
      if (row) return { token: row.token, available: row.available };
    }
    const sol = userBalances.balances.find((item) => item.token === "SOL");
    return sol ? { token: "SOL", available: sol.available } : null;
  }, [userBalances, plan]);

  const acquiredOut = executions.reduce(
    (sum, run) => sum + (run.result?.output_amount || 0),
    0
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-grid pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Automated recurring buys on Solana. Create and manage your plans with natural language.
            Same flow as the Aomi strategy app UI, backed by the live Python `/strategies` API.
          </p>
        </div>
        <span className="shrink-0 border border-warn/40 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-warn">
          Mainnet · live funds
        </span>
      </div>

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}
      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to authenticate.
        </div>
      )}

      <DcaAgentDeposit
        cluster={cluster}
        authToken={token}
        refreshTick={refreshTick}
        onBalancesChange={setUserBalances}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.8fr)_minmax(300px,1fr)]">
        <div className="space-y-6">
          <Panel
            title="Conversation · DCA Agent"
            action={<span className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">Solana</span>}
          >
            <div className="flex min-h-[480px] flex-col">
              <div className="max-h-[420px] flex-1 space-y-4 overflow-y-auto pr-1">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`rounded border px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "ml-6 border-grid bg-surface/60 text-foreground"
                        : "mr-4 border-signal/30 bg-surface/30 text-muted-foreground"
                    }`}
                  >
                    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                      {msg.role === "user" ? "You" : "Agent"}
                    </div>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.signature ? (
                      <a
                        href={explorerUrlForSignature(msg.signature, cluster)}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 block break-all font-mono text-[11px] text-foreground underline"
                      >
                        {msg.signature}
                      </a>
                    ) : null}
                  </div>
                ))}

                {draft && (
                  <div className="border border-grid bg-surface/50">
                    <div className="border-b border-grid px-4 py-3">
                      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
                        DCA plan · Solana
                      </div>
                      <h2 className="mt-1 text-lg font-semibold text-foreground">
                        {editing ? "Review plan changes" : "Review DCA plan"}
                      </h2>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Nothing runs until you authorize this schedule.
                      </p>
                    </div>
                    <div className="grid gap-3 p-4 sm:grid-cols-2">
                      {(
                        [
                          ["name", "Plan name", "text"],
                          ["input_token", "Input token", "text"],
                          ["output_token", "Output token", "text"],
                          ["amount_per_buy", "Amount per buy", "number"],
                          ["interval", "Interval", "text"],
                          ["max_executions", "Max buys", "number"],
                          ["total_budget", "Total budget", "number"],
                          ["slippage_bps", "Slippage bps", "number"],
                        ] as const
                      ).map(([key, label, type]) => (
                        <label
                          key={key}
                          className="grid gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
                        >
                          {label}
                          <input
                            type={type}
                            disabled={
                              busy ||
                              (editing && (key === "name" || key === "input_token" || key === "output_token"))
                            }
                            value={String(draft[key])}
                            onChange={(event) => {
                              const value =
                                type === "number" ? Number(event.target.value) : event.target.value;
                              setDraft((current) => {
                                if (!current) return current;
                                const next = { ...current, [key]: value };
                                if (key === "amount_per_buy" || key === "max_executions") {
                                  next.total_budget = budgetFromAmount(
                                    Number(next.amount_per_buy),
                                    Number(next.max_executions)
                                  );
                                }
                                if (key === "input_token" || key === "output_token") {
                                  next[key] = String(value).toUpperCase();
                                  next.name = `${next.input_token} → ${next.output_token}`;
                                }
                                return next;
                              });
                            }}
                            className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground outline-none focus:border-signal disabled:opacity-50"
                          />
                        </label>
                      ))}
                    </div>
                    <div className="space-y-2 border-t border-grid px-4 py-3 font-mono text-xs">
                      <div className="flex justify-between gap-3">
                        <span className="text-muted-foreground">Strategy</span>
                        <strong className="font-normal text-foreground">
                          {draft.input_token} → {draft.output_token} · Solana
                        </strong>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-muted-foreground">Platform fee</span>
                        <strong className="font-normal text-foreground">
                          0.5% per buy · included in budget
                        </strong>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span className="text-muted-foreground">First buy</span>
                        <strong className="font-normal text-foreground">
                          {draft.start_immediately ? "Start immediately (live)" : "After one interval"}
                        </strong>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Authorizes buys from your BIT Agents agent wallet. Network costs also apply.
                        Pause stops future runs, not a trade already in flight.
                      </p>
                      <div className="flex flex-wrap gap-2 pt-2">
                        <button
                          type="button"
                          disabled={busy || !token}
                          onClick={() => void authorizeDraft()}
                          className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
                        >
                          {editing ? "Save & authorize changes" : "Confirm & create plan"}
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            setDraft(null);
                            setEditing(false);
                          }}
                          className="border border-grid px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:border-signal hover:text-foreground"
                        >
                          Discard
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
                <div className="flex flex-col gap-3 sm:flex-row">
                  <input
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    disabled={busy || !token}
                    placeholder={
                      token
                        ? plan
                          ? "Ask about your plan, preview a buy, or pause…"
                          : "Buy 0.01 SOL of JUP daily for 2 buys"
                        : "Sign in with wallet to chat"
                    }
                    className="flex-1 border border-grid bg-background px-4 py-3 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={busy || !input.trim() || !token}
                    className="bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Send
                  </button>
                </div>
              </form>
              <div className="mt-3 flex flex-wrap gap-2">
                {EXAMPLES.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={busy || !token}
                    onClick={() => {
                      if (/preview|doing|pause/i.test(prompt)) {
                        void handleCommand(prompt);
                        return;
                      }
                      setInput(prompt);
                    }}
                    className="border border-grid px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-foreground disabled:opacity-40"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
              <p className="mt-3 font-mono text-[10px] text-muted-foreground">
                Guided conversation · live `/strategies` · real mainnet scheduler (no fixture swaps)
              </p>
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel title="Agent wallet">
            <div className="space-y-2">
              <div className="text-3xl font-semibold tracking-tight text-foreground">
                {availableBalance == null ? "-" : money(availableBalance.available)}{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  {availableBalance?.token ?? "SOL"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">Available deposit balance</p>
              <div className="flex justify-between border-t border-grid pt-3 font-mono text-xs">
                <span className="text-muted-foreground">Network</span>
                <span>Solana mainnet</span>
              </div>
              <div className="flex justify-between font-mono text-xs">
                <span className="text-muted-foreground">Platform fee</span>
                <span>0.5% per buy</span>
              </div>
            </div>
          </Panel>

          {plan && (
            <Panel
              title={plan.name}
              action={
                <span
                  className={`border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] ${
                    plan.status === "paused"
                      ? "border-warn/40 text-warn"
                      : "border-signal/40 text-signal"
                  }`}
                >
                  {plan.status}
                </span>
              }
            >
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                BITAGENTS / DCA · {plan.id}
              </p>
              <div className="space-y-2 font-mono text-xs">
                <div className="flex justify-between border-b border-grid py-2">
                  <span className="text-muted-foreground">Each buy</span>
                  <span>
                    {money(plan.amount_per_buy)} {plan.input_token} → {plan.output_token}
                  </span>
                </div>
                <div className="flex justify-between border-b border-grid py-2">
                  <span className="text-muted-foreground">Schedule</span>
                  <span>Every {plan.interval}</span>
                </div>
                <div className="flex justify-between border-b border-grid py-2">
                  <span className="text-muted-foreground">Budget used</span>
                  <span>
                    {money(plan.spent_so_far)} / {money(plan.total_budget)} {plan.input_token}
                  </span>
                </div>
                <div className="flex justify-between border-b border-grid py-2">
                  <span className="text-muted-foreground">Runs completed</span>
                  <span>
                    {plan.executions_count} / {plan.max_executions}
                  </span>
                </div>
                <div className="flex justify-between border-b border-grid py-2">
                  <span className="text-muted-foreground">Next run</span>
                  <span>
                    {plan.status === "active"
                      ? `${new Date(plan.next_execution_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC`
                      : "Paused"}
                  </span>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || !token}
                  onClick={() => void handleCommand("Preview next buy")}
                  className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground disabled:opacity-40"
                >
                  Preview next buy
                </button>
                <button
                  type="button"
                  disabled={busy || !token}
                  onClick={() =>
                    void handleCommand(plan.status === "paused" ? "Resume my plan" : "Pause my plan")
                  }
                  className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground disabled:opacity-40"
                >
                  {plan.status === "paused" ? "Resume plan" : "Pause plan"}
                </button>
                <button
                  type="button"
                  disabled={busy || !token}
                  onClick={() => void handleCommand("Edit my plan")}
                  className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground disabled:opacity-40"
                >
                  Edit plan
                </button>
              </div>
              {previewNote && <p className="mt-3 font-mono text-xs text-warn">{previewNote}</p>}
              <p className="mt-3 font-mono text-[11px] text-warn">
                {acquiredOut
                  ? `On-chain position · ${acquiredOut} ${plan.output_token} recorded · cost ${money(plan.spent_so_far)} ${plan.input_token}`
                  : "Awaiting the first scheduled buy."}
              </p>
              <div className="mt-3 space-y-2">
                {executions
                  .slice()
                  .reverse()
                  .slice(0, 6)
                  .map((run, index) => {
                    const signature = run.result?.signature || run.result?.receipt;
                    return (
                      <div
                        key={`${signature ?? index}`}
                        className="border border-signal/30 px-3 py-2 font-mono text-[11px]"
                      >
                        <div>
                          {(run.result?.status === "success" ? "Buy completed" : "Run") +
                            ` · ${money(Number(run.amount ?? 0))} ${plan.input_token}`}
                        </div>
                        {signature ? (
                          <a
                            href={explorerUrlForSignature(String(signature), cluster)}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block truncate text-foreground underline"
                          >
                            {signature}
                          </a>
                        ) : (
                          <div className="text-muted-foreground">No signature yet</div>
                        )}
                      </div>
                    );
                  })}
              </div>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Live buys are executed by the Python scheduler after each interval. There is no
                fixture “simulate tick” on this page.
              </p>
            </Panel>
          )}

          <Panel title="Agent actions">
            <div className="space-y-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
              {eventLog.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </Panel>

          <Panel title="How it works">
            <ol className="space-y-4 font-mono text-[11px] text-muted-foreground">
              <li>
                <span className="mb-1 block text-foreground">01 · Send a command</span>
                Choose a token, amount and cadence.
              </li>
              <li>
                <span className="mb-1 block text-foreground">02 · Confirm your plan</span>
                Review the budget and max buys.
              </li>
              <li>
                <span className="mb-1 block text-foreground">03 · Manage recurring buys</span>
                Preview, edit or pause. Scheduler runs real swaps through the Aomi gate.
              </li>
            </ol>
          </Panel>
        </div>
      </div>

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above to deposit and run DCA plans tied to your balance.
        </div>
      )}
      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to use the DCA agent.
        </div>
      )}
    </div>
  );
}
