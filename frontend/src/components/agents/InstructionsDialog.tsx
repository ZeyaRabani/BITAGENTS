"use client";

import { useState, useEffect } from "react";

interface InstructionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instructions: string;
  onSave: (instructions: string) => void | Promise<void>;
}

export function InstructionsDialog({
  open,
  onOpenChange,
  instructions,
  onSave,
}: InstructionsDialogProps) {
  const [localInstructions, setLocalInstructions] = useState(instructions);

  useEffect(() => {
    setLocalInstructions(instructions);
  }, [instructions]);

  async function handleSave() {
    await onSave(localInstructions);
  }

  function handleClear() {
    setLocalInstructions("");
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Overlay */}
      <div 
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      
      {/* Dialog content */}
      <div className="relative z-10 w-full max-w-2xl border border-grid bg-background p-6 shadow-2xl mx-4">
        <div className="space-y-4">
          <div>
            <h2 className="font-mono text-lg font-semibold uppercase tracking-wider text-signal">
              Custom Instructions
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Add custom instructions that will be included with every message you send to this agent.
            </p>
          </div>

          <div>
            <label className="block font-mono text-xs uppercase tracking-wider text-muted-foreground mb-2">
              Instructions
            </label>
            <textarea
              value={localInstructions}
              onChange={(e) => setLocalInstructions(e.target.value)}
              placeholder="e.g. Always list DCA plans after creating them, use concise responses, prefer SOL over USDC..."
              className="w-full min-h-[200px] border border-grid bg-surface/60 px-4 py-3 text-sm leading-relaxed font-mono resize-y focus:border-signal focus:outline-none"
            />
          </div>

          <div className="border-t border-grid pt-4">
            <p className="font-mono text-xs uppercase tracking-wider text-signal mb-2">
              Usage Examples:
            </p>
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li>• "Always list DCA plans after creating or modifying them"</li>
              <li>• "Use concise responses with bullet points"</li>
              <li>• "Prefer SOL over USDC for transactions when possible"</li>
              <li>• "Show me the transaction hash for every operation"</li>
              <li>• "Always confirm before executing trades or withdrawals"</li>
            </ul>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={handleSave}
              className="flex-1 border border-signal bg-signal/10 px-4 py-2.5 font-mono text-sm uppercase tracking-wider text-signal transition hover:bg-signal/20"
            >
              Save Instructions
            </button>
            <button
              onClick={handleClear}
              className="border border-grid bg-surface px-4 py-2.5 font-mono text-sm uppercase tracking-wider text-muted-foreground transition hover:border-warn hover:text-warn"
            >
              Clear
            </button>
            <button
              onClick={() => onOpenChange(false)}
              className="border border-grid bg-surface px-4 py-2.5 font-mono text-sm uppercase tracking-wider text-muted-foreground transition hover:border-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
