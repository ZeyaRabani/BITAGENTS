import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { AomiTestConsole } from "@/components/agents/AomiTestConsole";
import { AOMI_TEST } from "@/lib/aomiTestConfig";

export const metadata: Metadata = {
  title: `${AOMI_TEST.name} - BIT Agents`,
  description: AOMI_TEST.description,
};

export default function AomiTestPage() {
  return (
    <AppShell title={AOMI_TEST.name} subtitle={AOMI_TEST.tagline}>
      <AomiTestConsole />
    </AppShell>
  );
}
