"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Panel } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchVolumeCampaignExecutions,
  fetchVolumeCampaigns,
  provisionVolumeCampaign,
  updateVolumeCampaignStatus,
  type VolumeCampaignSummary,
} from "@/lib/volumePlanClient";

type CampaignStatusFilter = "all" | "active" | "provisioning" | "paused" | "failed" | "completed" | "cancelled";

function statusClass(status: string) {
  if (status === "active") return "text-signal";
  if (status === "provisioning") return "text-warn animate-pulse";
  if (status === "paused") return "text-warn";
  if (status === "failed") return "text-warn";
  if (status === "completed" || status === "cancelled") return "text-muted-foreground";
  return "text-foreground";
}

function formatTime(iso?: string | null) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function shortAddress(value?: string | null) {
  if (!value) return "-";
  if (value.length <= 12) return value;
  return `${value.slice(0, 4)}…${value.slice(-4)}`;
}

function provisionErrorMessage(campaign: VolumeCampaignSummary) {
  const err = campaign.infrastructure?.pool_creation_error;
  if (err && typeof err === "object" && "error" in err && typeof err.error === "string") {
    return err.error;
  }
  return null;
}

function CampaignExecutionsDialog({
  open,
  onOpenChange,
  campaign,
  authToken,
  cluster,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaign: VolumeCampaignSummary;
  authToken: string;
  cluster?: string;
}) {
  const [rows, setRows] = useState<
    Array<{
      at?: string;
      cycle?: number;
      buy?: { signature?: string };
      sell?: { signature?: string };
    }>
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchVolumeCampaignExecutions(campaign.id, authToken)
      .then((data) => {
        if (cancelled) return;
        setRows((data.executions ?? []) as typeof rows);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setError(err instanceof Error ? err.message : "Could not load transaction history.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, campaign.id, authToken]);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-h-[85vh] max-w-lg overflow-hidden">
        <AlertDialogHeader>
          <AlertDialogTitle>Volume cycle history</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-1 font-mono text-[11px] text-muted-foreground">
              <p>
                {campaign.name} · ID <code className="text-foreground">{campaign.id}</code>
              </p>
              <p>
                {campaign.executions_count}/{campaign.max_executions} cycles · {campaign.base_token}/
                {campaign.quote_token}
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="max-h-[50vh] space-y-2 overflow-y-auto border border-grid p-3">
          {loading && <p className="font-mono text-[11px] text-muted-foreground">Loading…</p>}
          {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
          {!loading && !error && rows.length === 0 && (
            <p className="font-mono text-[11px] text-muted-foreground">No cycles recorded yet.</p>
          )}
          {rows.map((row, index) => (
            <div
              key={`${row.at ?? index}-${index}`}
              className="flex flex-wrap items-center justify-between gap-2 border border-grid bg-background/60 px-3 py-2 font-mono text-[10px]"
            >
              <span className="text-muted-foreground">
                Cycle {row.cycle ?? index + 1} · {formatTime(row.at)}
              </span>
              <span className="flex gap-2">
                {row.buy?.signature && (
                  <a
                    href={explorerUrlForSignature(row.buy.signature, cluster)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-signal"
                  >
                    buy ↗
                  </a>
                )}
                {row.sell?.signature && (
                  <a
                    href={explorerUrlForSignature(row.sell.signature, cluster)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-signal"
                  >
                    sell ↗
                  </a>
                )}
              </span>
            </div>
          ))}
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel className="font-mono text-[11px] uppercase">Close</AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function VolumeCampaignPanel({
  authToken,
  cluster,
  refreshTick = 0,
  onCampaignChange,
}: {
  authToken: string;
  cluster?: string;
  refreshTick?: number;
  onCampaignChange?: () => void;
}) {
  const [campaigns, setCampaigns] = useState<VolumeCampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<CampaignStatusFilter>("all");
  const [historyCampaign, setHistoryCampaign] = useState<VolumeCampaignSummary | null>(null);
  const [pendingAction, setPendingAction] = useState<{
    id: string;
    action: "pause" | "resume" | "cancel";
    name: string;
  } | null>(null);

  const loadCampaigns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchVolumeCampaigns(authToken);
      setCampaigns(data.campaigns ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load campaigns");
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns, refreshTick]);

  const hasProvisioning = useMemo(
    () => campaigns.some((c) => c.status === "provisioning"),
    [campaigns]
  );

  useEffect(() => {
    if (!hasProvisioning) return;
    const timer = setInterval(() => {
      void loadCampaigns();
    }, 8000);
    return () => clearInterval(timer);
  }, [hasProvisioning, loadCampaigns]);

  const filtered = useMemo(() => {
    if (statusFilter === "all") return campaigns;
    return campaigns.filter((c) => c.status === statusFilter);
  }, [campaigns, statusFilter]);

  async function runStatusAction() {
    if (!pendingAction) return;
    setBusyId(pendingAction.id);
    try {
      await updateVolumeCampaignStatus(pendingAction.id, pendingAction.action, authToken);
      await loadCampaigns();
      onCampaignChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyId(null);
      setPendingAction(null);
    }
  }

  async function retryProvision(campaign: VolumeCampaignSummary) {
    setBusyId(campaign.id);
    setError(null);
    try {
      await provisionVolumeCampaign(campaign.id, authToken);
      await loadCampaigns();
      onCampaignChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provision retry failed");
    } finally {
      setBusyId(null);
    }
  }

  const filters: CampaignStatusFilter[] = [
    "all",
    "active",
    "provisioning",
    "paused",
    "failed",
    "completed",
    "cancelled",
  ];

  return (
    <Panel title="Volume campaigns">
      <div className="mb-4 flex flex-wrap gap-2">
        {filters.map((filter) => (
          <button
            key={filter}
            type="button"
            onClick={() => setStatusFilter(filter)}
            className={`border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition ${
              statusFilter === filter
                ? "border-signal text-signal"
                : "border-grid text-muted-foreground hover:text-foreground"
            }`}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {loading && <p className="font-mono text-[11px] text-muted-foreground">Loading campaigns…</p>}
        {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
        {!loading && filtered.length === 0 && (
          <p className="font-mono text-[11px] text-muted-foreground">
            {campaigns.length === 0
              ? "No campaigns yet. Deposit SOL + token, then create one above or via chat."
              : "No campaigns match this filter."}
          </p>
        )}

        {filtered.map((campaign) => {
          const provisionErr = provisionErrorMessage(campaign);
          return (
            <div key={campaign.id} className="border border-grid bg-background/60 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-[12px] text-foreground">{campaign.name}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    <code className="text-foreground">{campaign.id}</code> · {campaign.base_token}/
                    {campaign.quote_token} ·{" "}
                    <span className={statusClass(campaign.status)}>{campaign.status}</span>
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(campaign.status === "provisioning" || campaign.status === "failed") && (
                    <button
                      type="button"
                      className="border border-signal px-2 py-1 font-mono text-[10px] uppercase text-signal"
                      disabled={busyId === campaign.id}
                      onClick={() => void retryProvision(campaign)}
                    >
                      {busyId === campaign.id ? "Retrying…" : "Retry liquidity check"}
                    </button>
                  )}
                  {campaign.status === "active" && (
                    <button
                      type="button"
                      className="border border-grid px-2 py-1 font-mono text-[10px] uppercase"
                      disabled={busyId === campaign.id}
                      onClick={() =>
                        setPendingAction({ id: campaign.id, action: "pause", name: campaign.name })
                      }
                    >
                      Pause
                    </button>
                  )}
                  {campaign.status === "paused" && (
                    <button
                      type="button"
                      className="border border-signal px-2 py-1 font-mono text-[10px] uppercase text-signal"
                      disabled={busyId === campaign.id}
                      onClick={() =>
                        setPendingAction({ id: campaign.id, action: "resume", name: campaign.name })
                      }
                    >
                      Resume
                    </button>
                  )}
                  {(campaign.status === "active" ||
                    campaign.status === "paused" ||
                    campaign.status === "provisioning" ||
                    campaign.status === "failed") && (
                    <button
                      type="button"
                      className="border border-warn px-2 py-1 font-mono text-[10px] uppercase text-warn"
                      disabled={busyId === campaign.id}
                      onClick={() =>
                        setPendingAction({ id: campaign.id, action: "cancel", name: campaign.name })
                      }
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    type="button"
                    className="border border-grid px-2 py-1 font-mono text-[10px] uppercase"
                    onClick={() => setHistoryCampaign(campaign)}
                  >
                    History
                  </button>
                </div>
              </div>

              {campaign.status === "provisioning" && (
                <p className="mt-2 font-mono text-[10px] text-warn">
                  Checking Jupiter / Meteora liquidity… This usually completes in seconds when the pair
                  already trades.
                </p>
              )}

              {provisionErr && (campaign.status === "failed" || campaign.status === "provisioning") && (
                <div className="mt-2 border border-warn/30 bg-warn/10 px-3 py-2 font-mono text-[10px] text-warn">
                  Pool setup: {provisionErr}
                </div>
              )}

              {campaign.status === "failed" && campaign.last_error?.error && (
                <div className="mt-2 border border-warn/30 bg-warn/10 px-3 py-2 font-mono text-[10px] text-warn">
                  Stopped after {campaign.consecutive_failures ?? 3} failed attempts: {campaign.last_error.error}
                </div>
              )}

              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-[10px] sm:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">Trade / leg</dt>
                  <dd className="text-foreground">
                    {campaign.trade_amount} {campaign.quote_token}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Cycles</dt>
                  <dd className="text-foreground">
                    {campaign.executions_count}/{campaign.max_executions}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Interval</dt>
                  <dd className="text-foreground">{campaign.interval}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Meteora pool</dt>
                  <dd className="text-foreground">
                    {campaign.pool_address ? (
                      <a
                        href={`https://app.meteora.ag/dlmm/${campaign.pool_address}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="break-all text-signal"
                      >
                        {campaign.pool_address}
                      </a>
                    ) : campaign.pool_exists ? (
                      "Jupiter route"
                    ) : (
                      "pending"
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Spent</dt>
                  <dd className="text-foreground">
                    {campaign.spent_so_far} / {campaign.total_budget ?? "∞"} {campaign.quote_token}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Next run</dt>
                  <dd className="text-foreground">{formatTime(campaign.next_execution_at)}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted-foreground">Platform fee</dt>
                  <dd className="text-foreground">0.25% per buy + sell leg</dd>
                </div>
              </dl>
            </div>
          );
        })}
      </div>

      <ConfirmDialog
        open={Boolean(pendingAction)}
        onOpenChange={(open) => !open && setPendingAction(null)}
        title={`${pendingAction?.action ?? "Update"} campaign`}
        description={
          pendingAction
            ? `Apply "${pendingAction.action}" to ${pendingAction.name}?`
            : undefined
        }
        confirmLabel={pendingAction?.action ?? "Confirm"}
        onConfirm={() => void runStatusAction()}
      />

      {historyCampaign && (
        <CampaignExecutionsDialog
          open={Boolean(historyCampaign)}
          onOpenChange={(open) => !open && setHistoryCampaign(null)}
          campaign={historyCampaign}
          authToken={authToken}
          cluster={cluster}
        />
      )}
    </Panel>
  );
}
