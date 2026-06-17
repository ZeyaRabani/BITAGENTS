#!/usr/bin/env node
// Local DCA scheduler worker.
//
// Polls the cron endpoint every few seconds so Devnet Demo plans (and the
// experimental agent-wallet mode) advance while developing locally. In
// production, a Vercel Cron hits /api/cron/dca instead — see README.
//
//   BASE_URL    where the Next app is running (default http://localhost:3000)
//   CRON_SECRET optional; sent as Authorization: Bearer <secret>
//   INTERVAL_MS poll interval in ms (default 10000)

const baseUrl = (process.env.BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const secret = process.env.CRON_SECRET;
const intervalMs = Number(process.env.INTERVAL_MS ?? 10_000);
const url = `${baseUrl}/api/cron/dca`;

async function tick() {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: secret ? { Authorization: `Bearer ${secret}` } : {}
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      console.error(`[dca:worker] ${response.status}`, payload);
      return;
    }
    const processed = payload.processed ?? 0;
    if (processed > 0) {
      console.log(`[dca:worker] processed ${processed} order(s) at ${new Date().toISOString()}`);
    }
  } catch (error) {
    console.error("[dca:worker] request failed:", error instanceof Error ? error.message : error);
  }
}

console.log(`[dca:worker] polling ${url} every ${intervalMs}ms (Ctrl+C to stop)`);
await tick();
setInterval(tick, intervalMs);
