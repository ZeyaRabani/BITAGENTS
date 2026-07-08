"use client";

import { useCallback, useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import bs58 from "bs58";

type AuthSession = {
  token: string;
  user_wallet: string;
  expires_at: string;
};

function storageKey(wallet: string) {
  return `custom_auth_${wallet}`;
}

function getStoredAuth(wallet: string): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(storageKey(wallet));
}

function storeAuth(wallet: string, token: string) {
  sessionStorage.setItem(storageKey(wallet), token);
}

function clearAuth(wallet: string) {
  sessionStorage.removeItem(storageKey(wallet));
}

async function fetchChallenge(userWallet: string) {
  const params = new URLSearchParams({ user_wallet: userWallet });
  const res = await fetch(`/api/agents/custom/auth/challenge?${params}`, {
    cache: "no-store",
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error ?? "Auth challenge failed");
  }
  return data as { user_wallet: string; message: string; nonce: string; expires_at: string };
}

async function verifyAuth(body: {
  user_wallet: string;
  message: string;
  signature: string;
}): Promise<AuthSession> {
  const res = await fetch("/api/agents/custom/auth/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : data.error ?? "Wallet sign-in failed");
  }
  return data as AuthSession;
}

async function fetchMe(token: string) {
  const res = await fetch("/api/agents/custom/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as { user_wallet: string; expires_at: string };
}

export function useCustomAgentWalletAuth() {
  const { publicKey, signMessage, connected } = useWallet();
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wallet = publicKey?.toBase58() ?? null;

  const signIn = useCallback(async () => {
    if (!wallet || !signMessage) {
      setToken(null);
      setError("Wallet must support message signing.");
      return null;
    }

    setBusy(true);
    setError(null);

    try {
      const cached = getStoredAuth(wallet);
      if (cached) {
        const me = await fetchMe(cached);
        if (me?.user_wallet === wallet) {
          setToken(cached);
          return cached;
        }
        clearAuth(wallet);
      }

      const challenge = await fetchChallenge(wallet);
      const messageBytes = new TextEncoder().encode(challenge.message);
      const signatureBytes = await signMessage(messageBytes);
      const session = await verifyAuth({
        user_wallet: wallet,
        message: challenge.message,
        signature: bs58.encode(signatureBytes),
      });

      storeAuth(wallet, session.token);
      setToken(session.token);
      return session.token;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Wallet sign-in failed";
      setError(message);
      setToken(null);
      return null;
    } finally {
      setBusy(false);
    }
  }, [wallet, signMessage]);

  useEffect(() => {
    if (!connected || !wallet) {
      setToken(null);
      setError(null);
      return;
    }
    void signIn();
  }, [connected, wallet, signIn]);

  useEffect(() => {
    if (!connected && wallet) {
      clearAuth(wallet);
    }
  }, [connected, wallet]);

  return {
    wallet,
    token,
    busy,
    error,
    isAuthenticated: Boolean(token),
    signIn,
  };
}
