import { AppShell } from "@/components/AppShell";
import { DefiAgentConsole } from "@/components/agents/DefiAgentConsole";
import { getDefiAgentConfig, type DefiAgentSlug } from "@/lib/defiAgentsConfig";
import { notFound } from "next/navigation";

export function DefiAgentPage({ slug }: { slug: DefiAgentSlug }) {
  const config = getDefiAgentConfig(slug);
  if (!config) notFound();

  return (
    <AppShell title={config.name}>
      <DefiAgentConsole config={config} />
    </AppShell>
  );
}
