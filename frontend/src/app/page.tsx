import React from "react";
import { Hero } from "@/components/home/Hero";
import { Ticker } from "@/components/home/Ticker";
import { Product } from "@/components/home/Product";
import { HowItWorks } from "@/components/home/HowItWorks";
import { TokenUtility } from "@/components/home/TokenUtility";
import { Platform } from "@/components/home/Platform";
import { Footer } from "@/components/home/Footer";

export default function page() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(255,107,74,0.14),transparent_55%),linear-gradient(180deg,#05060a_0%,#0b0d14_42%,#12151f_100%)]"
      />
      <main>
        <Hero />
        <Ticker />
        <Product />
        <HowItWorks />
        <TokenUtility />
        <Platform />
      </main>
      <Footer />
    </div>
  );
}
