import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { FibOhlcConsole } from "@/components/agents/FibOhlcConsole";

export const metadata: Metadata = {
  title: "Fibonacci OHLC Agent - BIT Agents",
  description: "Paper Fibonacci daily OHLC strategy with chat, setups, and backtests.",
};

export default function FibOhlcPage() {
  return (
    <AppShell title="Fibonacci OHLC Agent">
      <FibOhlcConsole />
    </AppShell>
  );
}
