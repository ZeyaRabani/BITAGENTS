import { PageShell } from "@/components/primitives";
import { ProviderMarketplace } from "@/components/ProviderMarketplace";

export default function ComputePage() {
  return (
    <PageShell
      eyebrow="Compute marketplace"
      title="Compute providers"
      description="Register a compute profile, sign a message to prove wallet ownership, and appear in the marketplace. Tasks route to an online provider, with BITAGENTS Local Compute as the fallback."
    >
      <ProviderMarketplace />
    </PageShell>
  );
}
