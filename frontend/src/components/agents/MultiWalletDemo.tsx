"use client";

import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";

type DemoAddressResponse = {
  user_wallet: string;
  your_deposit_address: string;
  cluster: string;
  balance_lamports: number;
  balance_sol: number;
  min_sol_to_activate_lamports: number;
  min_sol_to_activate_sol: number;
  is_active: boolean;
  max_spendable_lamports: number;
};

function shorten(address: string) {
  return `${address.slice(0, 6)}…${address.slice(-6)}`;
}

export function MultiWalletDemo() {
  const { wallet, token, busy, error, isAuthenticated } = useDcaWalletAuth();
  const [data, setData] = useState<DemoAddressResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!token) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    fetch("/api/multi-wallet-demo/address", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    })
      .then(async (res) => {
        const json = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setFetchError(json.error || json.detail || "Failed to load your deposit address.");
          setData(null);
          return;
        }
        setData(json as DemoAddressResponse);
      })
      .catch(() => {
        if (!cancelled) setFetchError("Could not reach the agents API.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, refreshTick]);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Panel title="TODAY — ONE SHARED WALLET">
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            Every single user who deposits into the DCA Agent sends funds to the
            exact same address. Nothing on-chain distinguishes one user&apos;s money
            from another&apos;s — only an internal database keeps track of who owns
            what.
          </p>
          <div className="rounded-lg border border-grid bg-black/20 px-3 py-2 font-mono text-xs">
            6uMzjzHbFTxPBXjd17AtpvP4r18UjYvS35ENxMuHhNZo
            <div className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
              same address for every user, no exceptions
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="OPERATION MULTI-WALLET — YOUR OWN WALLET">
        <div className="space-y-4 text-sm">
          <p className="text-muted-foreground">
            Connect your wallet below and sign in. You&apos;ll be shown a deposit
            address that belongs to you and only you — generated fresh, never
            shared with any other user.
          </p>

          {!wallet && (
            <div className="flex flex-col items-start gap-2">
              <WalletMultiButton className="wallet-adapter-button-trigger" />
            </div>
          )}

          {wallet && !isAuthenticated && (
            <div className="text-xs text-muted-foreground">
              {busy ? "Signing in…" : error ? `Sign-in failed: ${error}` : "Waiting for signature…"}
            </div>
          )}

          {isAuthenticated && loading && (
            <div className="text-xs text-muted-foreground">Deriving your wallet…</div>
          )}

          {isAuthenticated && fetchError && (
            <div className="text-xs text-red-400">{fetchError}</div>
          )}

          {isAuthenticated && data && (
            <div className="space-y-3">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Connected as
                </div>
                <div className="font-mono text-xs">{shorten(data.user_wallet)}</div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Your unique deposit address
                </div>
                <div className="rounded-lg border border-grid bg-black/20 px-3 py-2 font-mono text-xs break-all">
                  {data.your_deposit_address}
                </div>
                <div className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
                  cluster: {data.cluster} · belongs only to this wallet
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-grid px-3 py-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Balance
                  </div>
                  <div className="font-mono text-sm">{data.balance_sol} SOL</div>
                </div>
                <div
                  className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider ${
                    data.is_active
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-amber-500/10 text-amber-400"
                  }`}
                >
                  {data.is_active ? "active" : "needs funding"}
                </div>
              </div>

              {!data.is_active && (
                <p className="text-xs text-muted-foreground">
                  Deposit at least <span className="font-mono">{data.min_sol_to_activate_sol} SOL</span> to
                  this address to activate it — this wallet pays its own transaction
                  fees, so it needs a little SOL of its own before it can do anything.
                </p>
              )}

              <button
                type="button"
                onClick={() => setRefreshTick((n) => n + 1)}
                className="w-full rounded-lg border border-grid px-3 py-1.5 text-xs uppercase tracking-wider text-muted-foreground hover:bg-surface/60"
              >
                Refresh balance
              </button>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
