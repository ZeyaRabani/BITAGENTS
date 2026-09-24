"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  fetchAgentBuilderHistory,
  fetchAgentDraftState,
  sendBuilderMessage,
  type AgentChecklist,
} from "@/lib/launchpadBuilderClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const STARTER_PROMPTS = [
  "I want an agent that watches whale wallets and alerts me on big moves",
  "I want an agent that researches a token before I buy it",
  "I want an agent that DCAs into SOL every day automatically",
];

const MARKDOWN_LINK = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function renderLineWithLinks(line: string, key: number) {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let linkIndex = 0;
  MARKDOWN_LINK.lastIndex = 0;
  while ((match = MARKDOWN_LINK.exec(line))) {
    if (match.index > lastIndex) parts.push(line.slice(lastIndex, match.index));
    const isTelegram = /t\.me\//.test(match[2]);
    parts.push(
      <a
        key={`${key}-link-${linkIndex++}`}
        href={match[2]}
        target="_blank"
        rel="noreferrer"
        className={
          isTelegram
            ? "mx-0.5 inline-flex items-center gap-1 border border-signal bg-signal/10 px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-signal hover:bg-signal/20"
            : "text-signal underline underline-offset-2 hover:opacity-80"
        }
      >
        {match[1]}
      </a>
    );
    lastIndex = MARKDOWN_LINK.lastIndex;
  }
  if (lastIndex < line.length) parts.push(line.slice(lastIndex));
  return parts;
}

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {renderLineWithLinks(line, i)}
    </p>
  ));
}

const CHECKLIST_ITEMS: { key: keyof AgentChecklist | "fields"; label: string }[] = [
  { key: "fields", label: "Name, category, description & system prompt" },
  { key: "notification_set", label: "Notification destination set" },
  { key: "notification_verified", label: "Notification verified (test confirmed)" },
  { key: "watch_configured", label: "Watch configured (what it actually checks)" },
];

function ChecklistSidebar({ checklist, loading }: { checklist: AgentChecklist | null; loading: boolean }) {
  return (
    <div className="border border-grid bg-surface/40 p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Launch checklist
      </div>
      {loading && !checklist ? (
        <p className="mt-3 text-xs text-muted-foreground">Waiting for the first message…</p>
      ) : !checklist ? (
        <p className="mt-3 text-xs text-muted-foreground">Nothing started yet.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {CHECKLIST_ITEMS.map((item) => {
            const done =
              item.key === "fields" ? checklist.fields_complete : Boolean(checklist[item.key as keyof AgentChecklist]);
            return (
              <li key={item.label} className="flex items-start gap-2 text-xs leading-relaxed">
                <span className={done ? "text-signal" : "text-muted-foreground/50"}>{done ? "✓" : "○"}</span>
                <span className={done ? "text-foreground" : "text-muted-foreground"}>{item.label}</span>
              </li>
            );
          })}
        </ul>
      )}
      {checklist?.watch_type && (
        <p className="mt-3 border-t border-grid pt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          Type: {checklist.watch_type.replace("_", " ")}
        </p>
      )}
      {checklist?.launched && (
        <p className="mt-3 border-t border-grid pt-3 text-xs text-signal">This agent is already live.</p>
      )}
    </div>
  );
}

export function AgentBuilderChat({ resumeAgentId }: { resumeAgentId?: string }) {
  const router = useRouter();
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [agentId, setAgentId] = useState<string | undefined>(resumeAgentId);
  const [checklist, setChecklist] = useState<AgentChecklist | null>(null);
  const [resuming, setResuming] = useState(Boolean(resumeAgentId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justLaunched, setJustLaunched] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!resumeAgentId || !token) return;
    let cancelled = false;
    (async () => {
      const [history, draft] = await Promise.all([
        fetchAgentBuilderHistory(resumeAgentId, token),
        fetchAgentDraftState(resumeAgentId, token),
      ]);
      if (cancelled) return;
      if (history.session_id) setSessionId(history.session_id);
      setMessages(
        history.messages.map((m, i) => ({
          id: `resume-${i}`,
          role: m.role === "user" ? "user" : "assistant",
          content: m.content,
        }))
      );
      if (draft) setChecklist(draft.checklist);
      setResuming(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [resumeAgentId, token]);

  async function refreshChecklist(id: string) {
    if (!token) return;
    const draft = await fetchAgentDraftState(id, token);
    if (draft) setChecklist(draft.checklist);
  }

  async function runMessage(text: string) {
    if (!token || !text.trim()) return;
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text.trim() }]);

    try {
      const res = await sendBuilderMessage(text.trim(), token, sessionId);
      setSessionId(res.session_id);
      if (res.agent_id) {
        setAgentId(res.agent_id);
        void refreshChecklist(res.agent_id);
      }
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", content: res.reply }]);
      const launched = res.actions?.some(
        (a) => a.tool === "finalize_and_launch" && a.result?.includes('"ok": true')
      );
      if (launched) {
        setJustLaunched(true);
        setTimeout(() => router.push("/launch"), 2500);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  function submitInput() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runMessage(text);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submitInput();
  }

  return (
    <div className="space-y-6">
      {!publicKey && (
        <div className="flex flex-col items-start gap-3 border border-grid bg-surface/40 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">Connect your wallet to start building an agent.</p>
          <WalletMultiButton className="wallet-adapter-button-trigger!" />
        </div>
      )}

      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to continue.
        </div>
      )}

      {justLaunched && (
        <div className="border border-signal bg-surface/60 px-4 py-3 font-mono text-xs text-signal">
          Agent launched — entering its 24h private testing window. Redirecting to the launchpad…
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_260px]">
      <Panel title="Build your agent">
        {resuming ? (
          <p className="py-6 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
            Loading this draft…
          </p>
        ) : (
        <>
        <div className="flex max-h-125 flex-col gap-4 overflow-y-auto pr-1">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm leading-relaxed text-muted-foreground">
                Describe what you want your agent to do — in your own words. I'll ask follow-up
                questions and write the actual instructions it runs on.
              </p>
              <div className="flex flex-col gap-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={!token || busy}
                    onClick={() => void runMessage(prompt)}
                    className="border border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground transition hover:border-signal/40 hover:text-foreground disabled:opacity-40"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`rounded border px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "border-grid bg-surface/60 text-foreground"
                  : "border-signal/30 bg-surface/30 text-muted-foreground"
              }`}
            >
              <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                {msg.role === "user" ? "You" : "Agent Builder"}
              </div>
              <div className="space-y-1">{formatReply(msg.content)}</div>
            </div>
          ))}
          {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Thinking…</div>}
          <div ref={chatEndRef} />
        </div>

        {error && (
          <div className="mt-4 border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            {error}
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitInput();
                }
              }}
              placeholder={
                isAuthenticated
                  ? "Tell it what you want to build… (Shift+Enter for a new line)"
                  : "Connect wallet and sign in to chat"
              }
              disabled={!token || busy}
              rows={1}
              className="max-h-40 min-h-[42px] flex-1 resize-y border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!token || busy || !input.trim()}
              className="self-start border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </form>
        </>
        )}
      </Panel>
      <ChecklistSidebar checklist={checklist} loading={resuming || (!checklist && (busy || messages.length > 0))} />
      </div>
    </div>
  );
}
