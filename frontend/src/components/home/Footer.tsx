import { Logo } from "@/components/Logo";

type FooterLink = {
  label: string;
  href: string;
  external?: boolean;
};

type FooterColumn = {
  title: string;
  items: FooterLink[];
};

export function Footer() {
  const cols: FooterColumn[] = [
    {
      title: "Protocol",
      items: [
        { label: "Agents", href: "/agents" },
        { label: "Analytics", href: "/analytics" },
        { label: "Gitbook", href: "https://gitbook.bitagents.app/", external: true },
        { label: "Roadmap", href: "#" },
      ],
    },
    {
      title: "Legal",
      items: [
        { label: "Terms", href: "/terms" },
        { label: "Privacy", href: "/privacy" },
        { label: "Risk disclaimer", href: "/risk-disclaimer" },
      ],
    },
    {
      title: "Community",
      items: [
        { label: "X / Twitter", href: "https://x.com/bitagentsapp", external: true },
        { label: "Telegram", href: "https://t.me/+7LRp1ZtAlt45ZjY0", external: true },
        {
          label: "EasyA Kickstart",
          href: "https://kickstart.easya.io/token/iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY",
          external: true,
        },
        { label: "GitHub", href: "https://github.com/ZeyaRabani/BITAGENTS", external: true },
      ],
    },
  ];

  return (
    <footer className="bg-background">
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-12 md:grid-cols-[1.4fr_2fr]">
          <div>
            <Logo className="h-14 w-auto" />
            <p className="mt-4 max-w-sm text-sm text-muted-foreground">
              The on-chain marketplace for autonomous AI agents. Wallet monitoring, research, automation, and on-chain workflows.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-8 md:grid-cols-3">
            {cols.map((c) => (
              <div key={c.title}>
                <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">{c.title}</div>
                <ul className="mt-4 space-y-2.5 text-sm text-muted-foreground">
                  {c.items.map((item) => (
                    <li key={item.label}>
                      <a
                        href={item.href}
                        className="transition hover:text-foreground"
                        {...(item.external
                          ? { target: "_blank", rel: "noopener noreferrer" }
                          : {})}
                      >
                        {item.label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-14 pt-6 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          <span>© 2026 BIT Agents · All rights reserved</span>
        </div>
      </div>
    </footer>
  );
}
