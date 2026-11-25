"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/AppShell";
import {
  BTN_PRIMARY,
  CODE_BOX,
  Field,
  LABEL,
  Notice,
  StatusBadge,
} from "@/components/agents/builder/BuilderUi";
import {
  baseName,
  builderApi,
  errorText,
  formatBytes,
  isAbort,
  shortAddress,
  type BuilderAgent,
} from "@/lib/builderClient";

const POLL_MS = 2000;

/**
 * Compile + deploy. Everything shown is read from the agent's `build` object;
 * while the server reports "building" the agent is re-fetched every 2 s.
 */
export function BuildPanel({
  agent,
  token,
  wallet,
  onAgent,
  className,
}: {
  agent: BuilderAgent;
  token: string | null;
  wallet: string | null;
  onAgent: (agent: BuilderAgent) => void;
  className?: string;
}) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);

  const building = agent.build_status === "building";
  const agentId = agent.id;

  useEffect(() => {
    if (!building) return;
    const controller = new AbortController();
    let inFlight = false;
    const timer = setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      builderApi
        .get(agentId, controller.signal)
        .then((next) => {
          setPollError(null);
          onAgent(next);
        })
        .catch((err) => {
          if (!isAbort(err)) setPollError(errorText(err));
        })
        .finally(() => {
          inFlight = false;
        });
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [building, agentId, onAgent]);

  async function compile() {
    if (!token) return;
    setStarting(true);
    setError(null);
    try {
      onAgent(await builderApi.compile(agentId, token));
    } catch (err) {
      setError(errorText(err));
      // 409 = a build is already running; pick up its real state.
      try {
        onAgent(await builderApi.get(agentId));
      } catch {
        /* the compile error above is already shown */
      }
    } finally {
      setStarting(false);
    }
  }

  const build = agent.build ?? {};
  const steps = build.steps ?? [];
  const isOwner = Boolean(wallet) && wallet === agent.owner_wallet;
  const elapsed =
    build.started_at != null && build.finished_at != null
      ? `${(build.finished_at - build.started_at).toFixed(1)} s`
      : null;

  return (
    <Panel
      title={build.hosted ? "Deploy" : "Compile and deploy"}
      action={<StatusBadge status={agent.build_status} />}
      className={className}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void compile()}
            disabled={!token || !isOwner || starting || building}
            className={BTN_PRIMARY}
          >
            {starting
              ? "Starting build…"
              : building
                ? "Building…"
                : agent.build_status === "draft"
                  ? "Compile and deploy"
                  : build.hosted
                    ? "Deploy again"
                    : "Compile again"}
          </button>
          {!token && (
            <span className="font-mono text-xs text-muted-foreground">Sign in with your wallet to deploy.</span>
          )}
          {token && !isOwner && (
            <span className="font-mono text-xs text-muted-foreground">
              Only the owner wallet {shortAddress(agent.owner_wallet)} can deploy this strategy.
            </span>
          )}
        </div>

        {error && <Notice tone="warn">{error}</Notice>}
        {pollError && <Notice tone="warn">Status refresh failed: {pollError}</Notice>}

        {agent.build_status === "draft" && steps.length === 0 && (
          <p className="font-mono text-xs text-muted-foreground">Not deployed yet.</p>
        )}

        {(build.stage || elapsed) && (
          <div className="grid gap-4 sm:grid-cols-2">
            {build.stage && !build.hosted && <Field label="Build stage">{build.stage}</Field>}
            {elapsed && !build.hosted && <Field label="Build time">{elapsed}</Field>}
          </div>
        )}

        {agent.build_status === "failed" && (
          <Notice tone="warn">{build.error ?? "The build failed and the server gave no error text."}</Notice>
        )}

        {steps.length > 0 && (
          <div className="space-y-2">
            <div className={LABEL}>Build steps</div>
            {steps.map((step, index) => (
              <details
                key={`${index}-${step.step}`}
                className="border border-grid"
                open={step.exit_code !== 0}
              >
                <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-3 px-3 py-2 font-mono text-xs">
                  <span className="text-foreground">{step.step}</span>
                  <span className="flex items-center gap-3 text-muted-foreground">
                    <span>{step.seconds} s</span>
                    <span className={step.exit_code === 0 ? "text-signal" : "text-warn"}>
                      exit {step.exit_code}
                    </span>
                  </span>
                </summary>
                <pre className={`${CODE_BOX} max-h-72 border-0 border-t`}>{step.tail || "(no output)"}</pre>
              </details>
            ))}
          </div>
        )}

        {agent.build_status === "ready" && (
          <div className="space-y-4 border-t border-grid pt-4">
            {build.hosted ? (
              <div className="space-y-2">
                <Field label="Published to Aomi app">{build.hosted.app}</Field>
                <p className="font-mono text-xs text-muted-foreground">
                  The BIT Agents agent on Aomi reads this strategy&apos;s spec by id on every run.
                </p>
              </div>
            ) : build.artifact ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Artifact">
                  <span title={build.artifact.path}>{baseName(build.artifact.path)}</span>
                </Field>
                <Field label="Size">
                  {formatBytes(build.artifact.bytes)} ({build.artifact.bytes.toLocaleString("en-US")} bytes)
                </Field>
                <div className="sm:col-span-2">
                  <Field label="SHA-256">
                    <span className="break-all">{build.artifact.sha256}</span>
                  </Field>
                </div>
              </div>
            ) : (
              <p className="font-mono text-xs text-muted-foreground">The server reported no artifact.</p>
            )}
            {build.installed ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Installed target">{build.installed.target}</Field>
                <Field label="Installed path">
                  <span className="break-all">{build.installed.path}</span>
                </Field>
              </div>
            ) : (
              build.install_note && <Notice>{build.install_note}</Notice>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
