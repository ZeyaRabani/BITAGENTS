import "./globals.css";
import "./ui-designs.css";
import "@solana/wallet-adapter-react-ui/styles.css";
import { constructMetadata } from '@/lib/utils';
import dynamic from "next/dynamic";
import { Nav } from "@/components/Nav";
import { Toaster } from "@/components/ui/sonner";
import { UiDesignProvider } from "@/components/ui-design/UiDesignProvider";
import { UiDesignSwitcher } from "@/components/ui-design/UiDesignSwitcher";

const SolanaProviders = dynamic(
  () => import("@/components/SolanaProviders").then((mod) => mod.SolanaProviders),
  { ssr: false }
);

export const metadata = constructMetadata();

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" data-ui-design="1" data-ui-color="1">
      <body className="bg-background text-foreground">
        <UiDesignProvider>
          <SolanaProviders>
            <Nav>{children}</Nav>
          </SolanaProviders>
          <UiDesignSwitcher />
          <Toaster />
        </UiDesignProvider>
      </body>
    </html>
  );
}
