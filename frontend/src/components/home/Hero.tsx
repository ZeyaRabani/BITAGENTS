"use client";

import type { ReactNode } from "react";
import { useUiDesign } from "@/components/ui-design/UiDesignProvider";

/** Same clear product story on every look - only layout changes. */
const HEADLINE = (
  <>
    Use and Create
    <br />
    <span className="text-signal">Agents on Solana</span>
  </>
);

const SUB =
  "1. Pick an agent  ·  2. Connect your wallet  ·  3. Fund it and go live";

function Ctas({ center = false }: { center?: boolean }) {
  return (
    <div
      id="hero-cta"
      className={`ui-hero-cta mt-10 flex flex-wrap items-center gap-3 ${center ? "justify-center" : ""}`}
    >
      <a href="/agents" className="ui-cta-primary group">
        Browse Agents <span className="transition group-hover:translate-x-0.5">→</span>
      </a>
      <a href="/agents/launch" className="ui-cta-secondary">
        Create Your Own
      </a>
    </div>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <div className="ui-hero-badge">{children}</div>;
}

function Brand() {
  return <p className="mt-5 font-display text-3xl tracking-tight text-signal sm:text-4xl">BITAGENTS</p>;
}

function Steps({ className = "" }: { className?: string }) {
  return (
    <p className={`mt-6 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg ${className}`}>
      {SUB}
    </p>
  );
}

export function Hero() {
  const { designId } = useUiDesign();

  if (designId === 5) {
    return (
      <section id="top" className="ui-hero relative overflow-hidden">
        
        <div className='hidden md:block absolute top-1/4 left-1/3 w-160 h-96 bg-primary/10 rounded-full blur-3xl z-[-1]' />
        {/* <div className='hidden md:block absolute bottom-1/4 right-1/4 w-80 h-80 bg-accent/5 rounded-full blur-3xl z-[-1]' /> */}

        <div className="ui-hero-inner mx-auto w-full max-w-6xl px-6 py-20 md:py-24">
          <div className="flex flex-col items-center justify-center">
            <h1 className="mt-4 font-display text-5xl font-bold leading-[0.95] tracking-tight sm:text-6xl md:text-7xl text-center">
              {HEADLINE}
            </h1>
            {/* <Steps /> */}
            <Ctas />
          </div>
        </div>
      </section>
    );
  }

  // Default - centered original composition
  return (
    <section id="top" className="ui-hero relative overflow-hidden">
      <div className="ui-hero-inner mx-auto max-w-4xl px-6 pb-24 pt-20 text-center md:pb-28 md:pt-24">
        <p className="mt-6 font-display text-3xl tracking-tight text-signal sm:text-4xl">BITAGENTS</p>
        <h1 className="mx-auto mt-4 font-display text-5xl font-bold leading-[0.95] tracking-tight sm:text-6xl md:text-7xl">
          {HEADLINE}
        </h1>
        <Steps className="mx-auto" />
        <Ctas center />
      </div>
    </section>
  );
}
