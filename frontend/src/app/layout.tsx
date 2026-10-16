import "./globals.css";
import "@solana/wallet-adapter-react-ui/styles.css";
import { constructMetadata } from '@/lib/utils';
import dynamic from "next/dynamic";
import { Nav } from "@/components/Nav";
import { Toaster } from "@/components/ui/sonner";

const SolanaProviders = dynamic(
  () => import("@/components/SolanaProviders").then((mod) => mod.SolanaProviders),
  { ssr: false }
);

export const metadata = constructMetadata();

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-foreground">
        <SolanaProviders>
          <Nav>{children}</Nav>
        </SolanaProviders>
        <Toaster />
      </body>
    </html>
  );
}
