import {
  makeExplorerAddressUrl,
  makeExplorerTxUrl,
  type AgentResult,
  type SolanaNetwork
} from "@bitagents/shared";

export function TaskResult({ result, network }: { result?: AgentResult; network?: SolanaNetwork }) {
  if (!result) {
    return <p className="font-mono text-sm text-muted-foreground">Result pending.</p>;
  }

  const net = network ?? result.network;

  return (
    <div className="space-y-5">
      {result.type === "wallet_watcher" ? <WalletWatcherView result={result} net={net} /> : null}
      {result.type === "token_research" ? <TokenResearchView result={result} /> : null}
      {result.type === "market_research" ? <MarketResearchView result={result} /> : null}
      <ComputeMetaView result={result} />
    </div>
  );
}

function WalletWatcherView({
  result,
  net
}: {
  result: Extract<AgentResult, { type: "wallet_watcher" }>;
  net: SolanaNetwork;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-3">
        <Metric label="SOL balance" value={result.solBalance.toFixed(5)} />
        <Metric label="Token accounts" value={String(result.tokenAccountsCount)} />
        <Metric label="Recent signatures" value={String(result.latestSignatures.length)} />
      </div>
      <Prose label="AI summary">{result.summary}</Prose>
      <ListBlock label="Risk / behavior notes" items={result.riskNotes} />
      <div className="border border-border bg-background/60 p-3">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          Latest signatures
        </p>
        {result.latestSignatures.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent signatures found on {net}.</p>
        ) : (
          <ul className="space-y-1.5">
            {result.latestSignatures.map((sig) => (
              <li key={sig.signature} className="flex items-center justify-between gap-2">
                <a
                  href={makeExplorerTxUrl(sig.signature, net)}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate font-mono text-xs text-signal hover:text-signal-soft"
                >
                  {sig.signature}
                </a>
                {sig.err ? <span className="font-mono text-[10px] uppercase text-danger">failed</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TokenResearchView({ result }: { result: Extract<AgentResult, { type: "token_research" }> }) {
  return (
    <div className="space-y-4">
      <Prose label="Overview">{result.overview}</Prose>
      <div className="grid gap-2 sm:grid-cols-3">
        <Metric label="Supply" value={result.onchain.supply !== null ? result.onchain.supply.toLocaleString() : "n/a"} />
        <Metric label="Decimals" value={result.onchain.decimals !== null ? String(result.onchain.decimals) : "n/a"} />
        <Metric
          label="Mint authority"
          value={result.onchain.mintAuthorityActive === null ? "n/a" : result.onchain.mintAuthorityActive ? "active" : "disabled"}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <ListBlock label="Bull case" items={result.bullCase} tone="success" />
        <ListBlock label="Bear case" items={result.bearCase} tone="danger" />
      </div>
      <ListBlock label="Risks" items={result.risks} tone="warn" />
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <Note label="Holders">{result.onchain.holdersNote}</Note>
        <Note label="Liquidity">{result.onchain.liquidityNote}</Note>
      </div>
      <Disclaimer>{result.disclaimer}</Disclaimer>
    </div>
  );
}

function MarketResearchView({ result }: { result: Extract<AgentResult, { type: "market_research" }> }) {
  return (
    <div className="space-y-4">
      <Prose label="What it means">{result.meaning}</Prose>
      <div className="grid gap-3 sm:grid-cols-2">
        <ListBlock label="Use cases" items={result.useCases} />
        <ListBlock label="Opportunities" items={result.opportunities} tone="success" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <ListBlock label="Risks" items={result.risks} tone="warn" />
        <ListBlock label="Things to monitor" items={result.thingsToMonitor} />
      </div>
      <Metric label="Heuristic sentiment (-100..100)" value={String(result.sentimentScore)} />
      <Disclaimer>{result.disclaimer}</Disclaimer>
    </div>
  );
}

function ComputeMetaView({ result }: { result: AgentResult }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 font-mono text-[11px] text-muted-foreground">
      <span>engine: {result.engine}</span>
      <span>runtime: {result.runtimeMs}ms</span>
      <span>network: {result.network}</span>
      <span className="truncate">hash: {result.resultHash.slice(0, 16)}…</span>
      <span>{new Date(result.computedAt).toLocaleString()}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border bg-surface-2 p-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-1 break-words font-display text-lg font-semibold text-foreground">{value}</p>
    </div>
  );
}

const TONES = {
  default: "text-foreground",
  success: "text-success",
  danger: "text-danger",
  warn: "text-warn"
} as const;

function ListBlock({
  label,
  items,
  tone = "default"
}: {
  label: string;
  items: string[];
  tone?: keyof typeof TONES;
}) {
  return (
    <div className="border border-border bg-background/60 p-3">
      <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <ul className="space-y-1.5 text-sm text-foreground/90">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className={TONES[tone]}>—</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Prose({ label, children }: { label: string; children: string }) {
  return (
    <div>
      <p className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="text-sm leading-relaxed text-foreground/90">{children}</p>
    </div>
  );
}

function Note({ label, children }: { label: string; children: string }) {
  return (
    <div className="border border-border bg-surface-2 p-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm text-foreground/80">{children}</p>
    </div>
  );
}

function Disclaimer({ children }: { children: string }) {
  return <p className="border-l-2 border-warn/60 pl-3 text-xs italic text-muted-foreground">{children}</p>;
}

export { makeExplorerAddressUrl };
