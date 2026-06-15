import type { AgentResult } from "@bitagents/shared";

export function TaskResult({ result }: { result?: AgentResult }) {
  if (!result) {
    return <p className="text-sm text-muted-foreground">Result pending.</p>;
  }

  if (result.type === "wallet_watcher") {
    return (
      <div className="space-y-3 text-sm">
        <Metric label="SOL balance" value={result.solBalance.toFixed(5)} />
        <Metric label="Token accounts" value={String(result.tokenAccountsCount)} />
        <p className="text-muted-foreground">{result.summary}</p>
        <div className="rounded-md border border-line bg-ink/60 p-3">
          <p className="mb-2 font-bold text-foreground">Latest signatures</p>
          <div className="space-y-2">
            {result.latestSignatures.length === 0 ? (
              <p className="text-muted-foreground">No recent signatures found on devnet.</p>
            ) : (
              result.latestSignatures.map((sig) => (
                <p key={sig.signature} className="break-all font-mono text-xs text-muted-foreground">
                  {sig.signature}
                </p>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  if (result.type === "research") {
    return (
      <div className="space-y-3 text-sm">
        <p className="font-bold text-foreground">{result.structuredSummary.headline}</p>
        <p className="text-muted-foreground">{result.structuredSummary.marketContext}</p>
        <p className="text-muted-foreground">{result.structuredSummary.technicalAngle}</p>
        <div className="grid gap-2 sm:grid-cols-3">
          <Metric label="Words" value={String(result.wordCount)} />
          <Metric label="Unique terms" value={String(result.uniqueTermCount)} />
          <Metric label="Sentiment" value={String(result.sentimentScore)} />
        </div>
        <div className="rounded-md border border-line bg-ink/60 p-3">
          <p className="font-bold text-foreground">Risks</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
            {result.structuredSummary.risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="grid gap-2 sm:grid-cols-3">
        <Metric label="Matrix" value={`${result.size}x${result.size}`} />
        <Metric label="Runtime" value={`${result.runtimeMs.toFixed(1)} ms`} />
        <Metric label="Checksum" value={result.checksum.toFixed(4)} />
      </div>
      <p className="break-all rounded-md border border-line bg-ink/60 p-3 font-mono text-xs text-muted-foreground">
        {result.resultHash}
      </p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-panel/70 p-3">
      <p className="text-xs font-bold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-base font-black text-foreground">{value}</p>
    </div>
  );
}
