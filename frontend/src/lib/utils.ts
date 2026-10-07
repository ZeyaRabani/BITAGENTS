import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { type Metadata } from 'next';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function constructMetadata({
  title = 'BITAGENTS',
  description = 'The on-chain marketplace for autonomous AI agents.',
  // image = '/assets/thumbnails/thumbnail.png',
  icons = '/bit-agents-logo-transparent.png',
  noIndex = false
}: {
  title?: string;
  description?: string;
  image?: string;
  icons?: string;
  noIndex?: boolean;
} = {}): Metadata {
  return {
    title,
    description,
    openGraph: {
      title, description,
      // images: [{url: image}]
    },
    twitter: { card: 'summary_large_image', title, description, creator: '@BitAgentsApp' },
    icons,
    metadataBase: new URL('https://bitagents.app/'),
    ...(noIndex && { robots: { index: false, follow: false } }),
  };
}
