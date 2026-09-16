"use client";

import { useState, useEffect } from "react";

interface InstructionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instructions: string;
  onSave: (instructions: string) => void;
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

  function handleSave() {
    onSave(localInstructions);
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
          <h2 className="font-mono text-sm uppercase tracking-wider text-signal">
            Custom Instructions
          </h2>

          <div className="space-y-3 border-t border-grid pt-4">
            <div className="space-y-2 text-sm text-muted-foreground">
              <p className="leading-relaxed">
                Add custom instructions that will be included with every message you send to the
                Hedge Fund Agent. This helps personalize the agent's behavior to match your
                preferences.
              </p>
              <div className="border-l-2 border-signal/30 bg-signal/5 pl-3 py-2">
                <p className="font-mono text-xs">
                  <strong className="text-signal">Purpose:</strong> Define shortcuts, set
                  preferences, or establish patterns the agent should follow
                </p>
              </div>
              <div className="space-y-1.5 font-mono text-xs">
                <p className="text-signal">Examples:</p>
                <ul className="list-inside list-disc space-y-1 text-muted-foreground">
                  <li>
                    <span className="text-foreground">ls</span> means list all my active DCA
                    strategies
                  </li>
                  <li>
                    <span className="text-foreground">Always</span> ask for confirmation before
                    liquidating positions
                  </li>
                  <li>
                    <span className="text-foreground">Prefer</span> conservative take-profit
                    targets around 10-12%
                  </li>
                  <li>
                    <span className="text-foreground">When I say "update"</span> followed by a
                    strategy ID, show me the full strategy details
                  </li>
                </ul>
              </div>
            </div>

            <textarea
              value={localInstructions}
              onChange={(e) => setLocalInstructions(e.target.value)}
              placeholder="Enter your custom instructions here... For example: 'ls' means list all my strategies, 'Always use conservative take-profit targets', etc."
              rows={8}
              className="w-full border border-grid bg-surface/30 px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-signal/40 focus:outline-none focus:ring-1 focus:ring-signal/20"
            />

            <div className="flex justify-between gap-3 border-t border-grid pt-4">
              <button
                type="button"
                onClick={() => {
                  setLocalInstructions("");
                }}
                className="border border-grid bg-surface/40 px-4 py-2 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:border-warn/40 hover:text-warn"
              >
                Clear
              </button>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="border border-grid bg-surface/40 px-4 py-2 font-mono text-xs uppercase tracking-wider text-muted-foreground hover:border-grid hover:text-foreground"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal hover:bg-signal/20"
                >
                  Save Instructions
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
