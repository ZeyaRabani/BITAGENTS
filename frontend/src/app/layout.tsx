import "./globals.css";
import "@solana/wallet-adapter-react-ui/styles.css";
import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { SolanaProviders } from "@/components/SolanaProviders";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "BITAGENTS — Run crypto AI agents without setup",
  description:
    "Connect a Solana wallet, choose an agent, and get a real on-chain result. Wallet Watcher, Token Research, and Market Research agents with real Solana RPC compute. Devnet demo payments; mainnet read-only.",
  icons: { icon: "/bit-agents-logo-transparent.png" }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SolanaProviders>
          <Nav>{children}</Nav>
        </SolanaProviders>
        <Toaster />
      </body>
    </html>
  );
}
