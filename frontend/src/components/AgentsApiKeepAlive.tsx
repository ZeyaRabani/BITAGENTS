"use client";

import { useEffect } from "react";

/** Keep the Render agents API warm while any app page stays open. */
const PING_MS = 10 * 60 * 1000;

async function pingKeepAlive() {
  try {
    await fetch("/api/agents/keepalive", {
      method: "GET",
      cache: "no-store",
      keepalive: true,
    });
  } catch {
    // Ignore - cold start or offline; next tick retries.
  }
}

export function AgentsApiKeepAlive() {
  useEffect(() => {
    void pingKeepAlive();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void pingKeepAlive();
      }
    }, PING_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void pingKeepAlive();
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return null;
}
