export type SimulatedAction = {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  status: "running" | "done";
  result: string;
};

export type SimulationResult = {
  reply: string;
  actions: SimulatedAction[];
};

const MOCK_PLANS = [
  {
    id: "63309a2f",
    name: "USDC → JUP Daily",
    input_token: "USDC",
    output_token: "JUP",
    amount_per_buy: 10,
    interval: "daily",
    status: "active",
    executions_count: 14,
    total_budget: 300,
    spent_so_far: 140,
  },
  {
    id: "f8a21bc0",
    name: "SOL Micro DCA",
    input_token: "SOL",
    output_token: "BONK",
    amount_per_buy: 0.05,
    interval: "every_15_minutes",
    status: "paused",
    executions_count: 6,
    total_budget: 50,
    spent_so_far: 0.3,
  },
];

function action(id: string, tool: string, args: Record<string, unknown>, result: string): SimulatedAction {
  return { id, tool, args, status: "done", result };
}

function parseTokens(input: string): { inputToken: string; outputToken: string; amount: number; interval: string } {
  const upper = input.toUpperCase();
  const tokens = ["USDC", "SOL", "JUP", "BONK", "WIF", "USDT"];
  const found = tokens.filter((t) => upper.includes(t));
  const inputToken = found.find((t) => /INTO|TO|BUY|FOR/.test(upper) && upper.indexOf(t) > upper.search(/INTO|TO|BUY/)) || found[1] || "USDC";
  const outputToken = found.find((t) => t !== inputToken) || "JUP";

  const amountMatch = input.match(/\$?\s*(\d+(?:\.\d+)?)/);
  const amount = amountMatch ? Number(amountMatch[1]) : 10;

  let interval = "daily";
  if (/hour/i.test(input)) interval = "hourly";
  else if (/15\s*min/i.test(input)) interval = "every_15_minutes";
  else if (/week/i.test(input)) interval = "weekly";
  else if (/day|daily/i.test(input)) interval = "daily";

  return { inputToken, outputToken, amount, interval };
}

function extractPlanId(input: string): string {
  const match = input.match(/\b([a-f0-9]{6,8})\b/i);
  return match?.[1] ?? "63309a2f";
}

export function simulateDcaAgent(command: string): SimulationResult {
  const text = command.trim();
  const lower = text.toLowerCase();

  if (/wallet|balance|status/.test(lower)) {
    return {
      actions: [
        action("a1", "get_wallet_status", {}, JSON.stringify({
          cluster: "devnet",
          pubkey: "7Hk…q4Px9mN2",
          sol_balance: 2.418,
          usdc_balance: 142.5,
          note: "Simulated devnet wallet - connect DCA_WALLET_PRIVATE_KEY for live swaps.",
        }, null, 2)),
      ],
      reply:
        "Wallet is connected on **devnet**.\n\n• Address: `7Hk…q4Px9mN2`\n• SOL: **2.418**\n• USDC: **142.50**\n\nReady to create or manage DCA plans. Not financial advice. DYOR.",
    };
  }

  if (/list.*plan|my plans|show plans|plans/.test(lower)) {
    return {
      actions: [
        action("a1", "list_dca_plans", { status: "active" }, JSON.stringify({ plans: MOCK_PLANS, count: MOCK_PLANS.length }, null, 2)),
      ],
      reply:
        "You have **2 DCA plans**:\n\n1. **USDC → JUP Daily** (`63309a2f`) - active · $10/day · 14 buys · $140 / $300 spent\n2. **SOL Micro DCA** (`f8a21bc0`) - paused · 0.05 SOL · every 15 min\n\nSay *pause plan f8a21bc0* or *execute plan 63309a2f now (dry run)* to manage them.",
    };
  }

  if (/analyze|timing|trend/.test(lower)) {
    const token = /jup|bonk|sol|wif/i.exec(text)?.[0]?.toUpperCase() ?? "JUP";
    return {
      actions: [
        action("a1", "get_token_price", { token }, JSON.stringify({ token, price_usd: token === "JUP" ? 0.548 : 0.000012, source: "simulated" }, null, 2)),
        action("a2", "analyze_dca_timing", { output_token: token, lookback_days: 7 }, JSON.stringify({
          output_token: token,
          trend_7d: "+4.2%",
          volatility: "moderate",
          dca_note: "Regular DCA smooths volatility - frequency depends on your horizon, not short-term trend.",
        }, null, 2)),
      ],
      reply:
        `**${token}** 7-day trend: **+4.2%** (simulated). Volatility is moderate.\n\nFor accumulation, **daily or weekly** DCA is usually smoother than reacting to short-term moves. Want me to set up a plan? Not financial advice. DYOR.`,
    };
  }

  if (/pause|resume|cancel/.test(lower)) {
    const planId = extractPlanId(text);
    const verb = /cancel/.test(lower) ? "cancel" : /resume/.test(lower) ? "resume" : "pause";
    return {
      actions: [
        action("a1", "get_dca_plan", { plan_id: planId }, JSON.stringify(MOCK_PLANS[0], null, 2)),
        action("a2", "update_dca_plan_status", { plan_id: planId, action: verb }, JSON.stringify({ plan_id: planId, status: verb === "pause" ? "paused" : verb === "resume" ? "active" : "cancelled" }, null, 2)),
      ],
      reply: `Plan \`${planId}\` is now **${verb === "pause" ? "paused" : verb === "resume" ? "active" : "cancelled"}**. The scheduler will ${verb === "resume" ? "resume" : "stop"} automatic buys on the next tick.`,
    };
  }

  if (/execute|run now|dry run/.test(lower)) {
    const planId = extractPlanId(text);
    const dryRun = /dry/.test(lower);
    return {
      actions: [
        action("a1", "get_dca_plan", { plan_id: planId }, JSON.stringify(MOCK_PLANS[0], null, 2)),
        action("a2", "get_jupiter_quote", { input_token: "USDC", output_token: "JUP", amount: 10, slippage_bps: 100 }, JSON.stringify({ inAmount: "10", outAmount: "18.2", priceImpactPct: "0.01", simulated: true }, null, 2)),
        action("a3", "execute_dca_now", { plan_id: planId, dry_run: dryRun }, JSON.stringify({
          plan_id: planId,
          dry_run: dryRun,
          tx: dryRun ? null : "5kF2…xR9p",
          message: dryRun ? "Dry run OK - no transaction sent." : "Buy executed on devnet (simulated).",
        }, null, 2)),
      ],
      reply: dryRun
        ? `Dry run for plan \`${planId}\`: would swap **10 USDC → ~18.2 JUP** at 1% slippage. No transaction sent.`
        : `Executed plan \`${planId}\`: **10 USDC → 18.2 JUP** (simulated devnet tx \`5kF2…xR9p\`).`,
    };
  }

  if (/history/.test(lower)) {
    const planId = extractPlanId(text);
    return {
      actions: [
        action("a1", "get_dca_history", { plan_id: planId }, JSON.stringify({
          plan_id: planId,
          executions: [
            { at: "2026-06-18T09:00:00Z", amount: 10, input_token: "USDC", output_token: "JUP", status: "success" },
            { at: "2026-06-17T09:00:00Z", amount: 10, input_token: "USDC", output_token: "JUP", status: "success" },
            { at: "2026-06-16T09:00:00Z", amount: 10, input_token: "USDC", output_token: "JUP", status: "success" },
          ],
        }, null, 2)),
      ],
      reply: `Last 3 executions for \`${planId}\` (simulated):\n\n• Jun 18 - 10 USDC → JUP ✓\n• Jun 17 - 10 USDC → JUP ✓\n• Jun 16 - 10 USDC → JUP ✓`,
    };
  }

  if (/quote|swap preview|preview/.test(lower)) {
    const { inputToken, outputToken, amount } = parseTokens(text);
    return {
      actions: [
        action("a1", "get_jupiter_quote", { input_token: inputToken, output_token: outputToken, amount, slippage_bps: 100 }, JSON.stringify({
          input_token: inputToken,
          output_token: outputToken,
          inAmount: String(amount),
          outAmount: "18.2",
          priceImpactPct: "0.02",
          simulated: true,
        }, null, 2)),
      ],
      reply: `Quote: **${amount} ${inputToken} → ~18.2 ${outputToken}** (1% slippage, simulated). Say *create a DCA plan* to schedule recurring buys.`,
    };
  }

  if (/dca|every|recurring|buy.*into|budget/.test(lower)) {
    const { inputToken, outputToken, amount, interval } = parseTokens(text);
    const budgetMatch = text.match(/budget\s*\$?(\d+)/i);
    const budget = budgetMatch ? Number(budgetMatch[1]) : 300;
    const planId = "c4e91d2a";

    return {
      actions: [
        action("a1", "get_wallet_status", {}, JSON.stringify({ cluster: "devnet", usdc_balance: 142.5 }, null, 2)),
        action("a2", "get_token_price", { token: outputToken }, JSON.stringify({ token: outputToken, price_usd: 0.548 }, null, 2)),
        action("a3", "get_jupiter_quote", { input_token: inputToken, output_token: outputToken, amount, slippage_bps: 100 }, JSON.stringify({ inAmount: String(amount), outAmount: "18.2" }, null, 2)),
        action("a4", "create_dca_plan", {
          name: `${inputToken} → ${outputToken} DCA`,
          input_token: inputToken,
          output_token: outputToken,
          amount_per_buy: amount,
          interval,
          total_budget: budget,
          start_immediately: true,
        }, JSON.stringify({
          id: planId,
          status: "active",
          next_execution_at: "2026-06-19T09:00:00Z",
          message: "Plan created (simulated). Scheduler will run buys automatically.",
        }, null, 2)),
      ],
      reply:
        `Created DCA plan \`${planId}\` (simulated):\n\n• Buy **${amount} ${inputToken} → ${outputToken}** every **${interval.replace(/_/g, " ")}**\n• Budget: **$${budget}**\n• Status: **active** · first buy scheduled\n\n⚠️ DCA does not guarantee profit. Not financial advice. DYOR.`,
    };
  }

  return {
    actions: [
      action("a1", "get_wallet_status", {}, JSON.stringify({ cluster: "devnet", ready: true }, null, 2)),
    ],
    reply:
      "I'm the **Solana DCA Agent**. Try commands like:\n\n• List my DCA plans\n• DCA $10 USDC into JUP every day, budget $300\n• Analyze JUP for DCA timing\n• Execute plan 63309a2f now (dry run)\n• Pause plan f8a21bc0",
  };
}

export const DCA_EXAMPLE_PROMPTS = [
  "List my DCA plans",
  "DCA $10 USDC into JUP every day, budget $300",
  "Analyze JUP for DCA timing",
  "Execute plan 63309a2f now (dry run)",
];

export const DCA_AGENT = {
  id: "dca",
  name: "DCA Agent",
  slug: "dca",
  tagline: "Recurring buys",
  description:
    "Set up dollar-cost averaging on Solana.",
  status: "Running" as const,
  task: "Monitoring 2 active DCA plans on devnet",
  strategy: "dca-scheduler",
  model: "llama3.1",
  cluster: "devnet",
};
