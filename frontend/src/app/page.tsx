import React from 'react';
import { Hero } from '@/components/home/Hero';
import { TrendingAgents } from '@/components/home/TrendingAgents';
import { HowItWorks } from '@/components/home/HowItWorks';
import { Platform } from '@/components/home/Platform';
import { Footer } from '@/components/home/Footer';

export default function page() {
  return (
    <div>
      <main>
        <Hero />
        <TrendingAgents />
        <HowItWorks />
        <Platform />
      </main>
      <Footer />
    </div>
  )
}
