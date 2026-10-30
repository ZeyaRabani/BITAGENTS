import React from 'react';
import { Hero } from '@/components/home/Hero';
import { Ticker } from '@/components/home/Ticker';
import { HowItWorks } from '@/components/home/HowItWorks';
import { Platform } from '@/components/home/Platform';
import { Footer } from '@/components/home/Footer';

export default function page() {
  return (
    <div className="ui-design-page">
      <main>
        <Hero />
        <Ticker />
        <HowItWorks />
        <Platform />
      </main>
      <Footer />
    </div>
  )
}
