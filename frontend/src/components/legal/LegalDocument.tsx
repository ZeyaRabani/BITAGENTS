import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { LEGAL_LINKS } from "@/lib/legal";

type Section = {
  title: string;
  body: string[];
};

export function LegalDocument({
  title,
  subtitle,
  updated,
  sections,
}: {
  title: string;
  subtitle: string;
  updated: string;
  sections: Section[];
}) {
  return (
    <AppShell title={title} subtitle={subtitle}>
      <p className="mb-8 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        Last updated · {updated}
      </p>

      <div className="max-w-3xl space-y-8">
        {sections.map((section) => (
          <section key={section.title}>
            <h2 className="font-display text-xl font-bold">{section.title}</h2>
            <div className="mt-3 space-y-3 text-sm leading-relaxed text-muted-foreground">
              {section.body.map((paragraph) => (
                <p key={paragraph.slice(0, 40)}>{paragraph}</p>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="mt-12 flex flex-wrap gap-4 pt-6 font-mono text-[11px] uppercase tracking-[0.14em]">
        <Link href={LEGAL_LINKS.terms} className="text-muted-foreground transition hover:text-signal">
          Terms
        </Link>
        <Link href={LEGAL_LINKS.privacy} className="text-muted-foreground transition hover:text-signal">
          Privacy
        </Link>
        <Link
          href={LEGAL_LINKS.riskDisclaimer}
          className="text-muted-foreground transition hover:text-signal"
        >
          Risk disclaimer
        </Link>
      </div>
    </AppShell>
  );
}
