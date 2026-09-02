import React from 'react';
import { Hero } from '@/components/home/Hero';
import { PlatformMetrics } from '@/components/home/PlatformMetrics';
import { TrendingAgents } from '@/components/home/TrendingAgents';
import { Product } from '@/components/home/Product';
import { HowItWorks } from '@/components/home/HowItWorks';
import { TokenUtility } from '@/components/home/TokenUtility';
import { Platform } from '@/components/home/Platform';
import { Footer } from '@/components/home/Footer';

export default function page() {
  return (
    <div>
      <main>
        <Hero />
        <PlatformMetrics />
        <TrendingAgents />
        <Product />
        <HowItWorks />
        <TokenUtility />
        <Platform />
      </main>
      <Footer />
    </div>
  )
}
