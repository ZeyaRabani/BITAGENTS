import "./globals.css";
import "@solana/wallet-adapter-react-ui/styles.css";
import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { SolanaProviders } from "@/components/SolanaProviders";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "BITAGENTS — Create DCA bots with AI",
  description:
    "Tell BITAGENTS what token to buy, how much to spend, and how often. The DCA Agent turns your message into a recurring on-chain buy plan you confirm. Mainnet Safe Mode via Jupiter Recurring; Devnet Demo Mode for simulation.",
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
