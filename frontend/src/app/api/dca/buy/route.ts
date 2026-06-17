import { WSOL_MINT, rawAmountToUiAmount, uiAmountToRawAmount } from "@bitagents/shared";
import { dcaConfig } from "@/server/dca/config";
import { buildSwapTransaction, fetchRawQuote } from "@/server/dca/jupiter";
import { resolveToken } from "@/server/dca/tokens";
import { parseNetwork, requirePublicKey } from "@/server/validation";

export const runtime = "nodejs";

// One-time market buy via Jupiter's regular Swap API. Unlike the Recurring API
// there is no ~50 USDC per-order minimum, so a small buy (e.g. 0.01 SOL of
// BITAGENTS) goes through. Returns an unsigned base64 transaction the user
// signs and sends from their own wallet — no custody, no integrator fee.
export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const walletAddress = requirePublicKey(body.walletAddress, "wallet address");
    const network = parseNetwork(body.network);

    const amountUi = Number(body.amountUi);
    if (!Number.isFinite(amountUi) || amountUi <= 0) {
      return Response.json({ ok: false, error: "Enter an amount greater than zero." });
    }

    const rawSlippage = Number(body.slippageBps);
    const slippageBps = Number.isFinite(rawSlippage)
      ? Math.min(5000, Math.max(10, Math.round(rawSlippage)))
      : 100;

    // Jupiter only routes mainnet liquidity; there is no devnet swap market.
    if (network !== "mainnet") {
      return Response.json({
        ok: false,
        error: "One-time buys run on mainnet. Switch to Mainnet Safe Mode to buy real tokens."
      });
    }

    const outputRef =
      typeof body.outputMint === "string" && body.outputMint.trim().length > 0
        ? body.outputMint.trim()
        : "";
    if (!outputRef) {
      return Response.json({ ok: false, error: "Which token should I buy?" });
    }
    const inputRef =
      typeof body.inputMint === "string" && body.inputMint.trim().length > 0
        ? body.inputMint.trim()
        : WSOL_MINT;

    const [outputResolution, inputResolution] = await Promise.all([
      resolveToken(outputRef),
      resolveToken(inputRef)
    ]);
    if (!outputResolution.ok) {
      return Response.json({ ok: false, error: `I couldn't resolve the token "${outputRef}".` });
    }
    if (!inputResolution.ok) {
      return Response.json({ ok: false, error: `I couldn't resolve the token you want to spend ("${inputRef}").` });
    }

    const inputToken = inputResolution.token;
    const outputToken = outputResolution.token;
    const rawIn = uiAmountToRawAmount(amountUi, inputToken.decimals);
    const config = dcaConfig();

    const quote = await fetchRawQuote(inputToken.mint, outputToken.mint, rawIn, slippageBps, config);
    const outAmountRaw = quote && typeof quote.outAmount === "string" ? Number(quote.outAmount) : NaN;
    if (!quote || !Number.isFinite(outAmountRaw) || outAmountRaw <= 0) {
      return Response.json({
        ok: false,
        error: "No swap route found for that token and amount. Try a slightly larger amount."
      });
    }

    const built = await buildSwapTransaction(quote, walletAddress, config);
    if (!built) {
      return Response.json({
        ok: false,
        error: "Could not build the swap transaction. Please try again in a moment."
      });
    }

    const priceImpactPct =
      typeof quote.priceImpactPct === "string" || typeof quote.priceImpactPct === "number"
        ? Number(quote.priceImpactPct)
        : null;

    return Response.json({
      ok: true,
      transaction: built.swapTransaction,
      lastValidBlockHeight: built.lastValidBlockHeight,
      quote: {
        inputSymbol: inputToken.symbol,
        outputSymbol: outputToken.symbol,
        inputMint: inputToken.mint,
        outputMint: outputToken.mint,
        inputAmountUi: amountUi,
        outputAmountUi: rawAmountToUiAmount(outAmountRaw, outputToken.decimals),
        priceImpactPct: priceImpactPct != null && Number.isFinite(priceImpactPct) ? priceImpactPct : null,
        slippageBps
      }
    });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
