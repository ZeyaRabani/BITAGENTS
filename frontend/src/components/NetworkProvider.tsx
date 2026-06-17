"use client";

import {
  isSolanaNetwork,
  networkLabel,
  type SolanaNetwork
} from "@bitagents/shared";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import { FALLBACK_CONFIG, rpcUrlFor, type PublicConfig } from "@/lib/config";

const STORAGE_KEY = "bitagents.network";

interface NetworkContextValue {
  network: SolanaNetwork;
  setNetwork: (network: SolanaNetwork) => void;
  toggleNetwork: () => void;
  label: string;
  isDevnet: boolean;
  paymentsEnabled: boolean;
  rpcUrl: string;
  config: PublicConfig;
  configLoaded: boolean;
  // DCA: mainnet "Safe Mode" is only available when the deployment enables it.
  mainnetDcaEnabled: boolean;
  dcaModeLabel: string;
}

const NetworkContext = createContext<NetworkContextValue | null>(null);

export function NetworkProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<PublicConfig>(FALLBACK_CONFIG);
  const [configLoaded, setConfigLoaded] = useState(false);
  // Start on the deployment's configured default so the first paint matches it
  // (no flash of the wrong network). A saved user choice or the live /api/config
  // response below can still override this.
  const [network, setNetworkState] = useState<SolanaNetwork>(FALLBACK_CONFIG.defaultNetwork);
  const [userPicked, setUserPicked] = useState(false);

  // Restore an explicit user choice from a previous visit.
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && isSolanaNetwork(stored)) {
      setNetworkState(stored);
      setUserPicked(true);
    }
  }, []);

  // Pull public config (treasury, RPC endpoints, default network) from the server.
  useEffect(() => {
    let active = true;
    fetch("/api/config")
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("config"))))
      .then((data: PublicConfig) => {
        if (!active) return;
        setConfig(data);
        setConfigLoaded(true);
        setNetworkState((current) => (userPicked ? current : data.defaultNetwork));
      })
      .catch(() => {
        if (active) setConfigLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [userPicked]);

  const setNetwork = useCallback((next: SolanaNetwork) => {
    setNetworkState(next);
    setUserPicked(true);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const toggleNetwork = useCallback(() => {
    setNetwork(network === "devnet" ? "mainnet" : "devnet");
  }, [network, setNetwork]);

  const value = useMemo<NetworkContextValue>(
    () => ({
      network,
      setNetwork,
      toggleNetwork,
      label: networkLabel(network),
      isDevnet: network === "devnet",
      paymentsEnabled: network === "devnet",
      rpcUrl: rpcUrlFor(config, network),
      config,
      configLoaded,
      mainnetDcaEnabled: config.enableMainnetDca,
      dcaModeLabel:
        network === "mainnet" && config.enableMainnetDca ? "Mainnet Safe Mode" : "Devnet Demo Mode"
    }),
    [network, setNetwork, toggleNetwork, config, configLoaded]
  );

  return <NetworkContext.Provider value={value}>{children}</NetworkContext.Provider>;
}

export function useNetwork(): NetworkContextValue {
  const ctx = useContext(NetworkContext);
  if (!ctx) {
    throw new Error("useNetwork must be used within a NetworkProvider");
  }
  return ctx;
}
