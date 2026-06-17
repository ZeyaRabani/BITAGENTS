import { dcaConfig } from "@/server/dca/config";
import { parseDcaPrompt } from "@/server/dca/parse";
import { assembleDcaPlan, type PlanContext } from "@/server/dca/plan";
import { resolveToken } from "@/server/dca/tokens";
import { requireString, parseNetwork } from "@/server/validation";
import type { DcaExecutionMode } from "@bitagents/shared";

export const runtime = "nodejs";

function parseExecutionMode(value: unknown): DcaExecutionMode | undefined {
  if (value === "agent_wallet" || value === "devnet_demo" || value === "jupiter_recurring") {
    return value;
  }
  return undefined;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const message = requireString(body.message, "message", 400);
    const network = parseNetwork(body.network);
    const walletAddress =
      typeof body.walletAddress === "string" && body.walletAddress.trim().length > 0
        ? body.walletAddress.trim()
        : "";
    const config = dcaConfig();

    const { fields, engine } = await parseDcaPrompt(message);

    if (!fields.outputTokenRef) {
      return Response.json({
        ok: false,
        clarification:
          "Which token should I buy? Tell me a symbol I know (like BITAGENTS, SOL, USDC) or paste a mint address.",
        engine
      });
    }

    const outputResolution = await resolveToken(fields.outputTokenRef);
    if (!outputResolution.ok) {
      const clarification =
        outputResolution.reason === "invalid_mint"
          ? `"${fields.outputTokenRef}" doesn't look like a valid Solana mint address. Please double-check it.`
          : `I don't recognize "${fields.outputTokenRef}". Paste its mint address and I'll use that exact token.`;
      return Response.json({ ok: false, clarification, engine });
    }

    const inputResolution = await resolveToken(fields.inputTokenRef ?? "SOL");
    if (!inputResolution.ok) {
      return Response.json({
        ok: false,
        clarification: `I don't recognize the token you want to spend ("${fields.inputTokenRef}"). Paste its mint address.`,
        engine
      });
    }

    const ctx: PlanContext = {
      userWallet: walletAddress,
      network,
      enableMainnetDca: config.enableMainnetDca,
      executionMode: parseExecutionMode(body.executionMode)
    };

    const assembled = assembleDcaPlan(inputResolution.token, outputResolution.token, fields, ctx);
    if (!assembled.ok) {
      return Response.json({ ok: false, clarification: assembled.clarification, engine });
    }

    return Response.json({ ok: true, plan: assembled.plan, engine, parsed: fields });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
