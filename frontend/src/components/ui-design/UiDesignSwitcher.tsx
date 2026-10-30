"use client";

import { UI_COLORS, UI_DESIGNS, type UiColorId } from "@/lib/uiDesigns";
import { useUiDesign } from "@/components/ui-design/UiDesignProvider";

export function UiDesignSwitcher() {
  const { designId, design, setDesignId, colorId, color, setColorId, ready } = useUiDesign();

  if (!ready) return null;

  return (
    <div
      className="ui-design-switcher fixed bottom-4 right-4 z-[80] flex max-w-[min(100vw-2rem,18rem)] flex-col items-end gap-2"
      aria-label="UI look switcher"
    >
      <div className="ui-design-switcher-label w-full border border-grid bg-surface/95 px-3 py-2 text-left shadow-lg backdrop-blur">
        <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
          Look
        </div>
        <div className="mt-0.5 text-sm font-semibold text-foreground">{design.name}</div>
        <div className="mt-0.5 text-[11px] text-muted-foreground">{design.blurb}</div>

        {designId === 5 && (
          <label className="mt-3 block">
            <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              Accent color
            </span>
            <div className="mt-1.5 flex items-center gap-2">
              <span
                className="h-4 w-4 shrink-0 rounded-sm border border-grid"
                style={{ background: color.swatch }}
                aria-hidden
              />
              <select
                value={colorId}
                onChange={(e) => setColorId(Number(e.target.value) as UiColorId)}
                className="w-full border border-grid bg-background px-2 py-1.5 font-mono text-xs text-foreground outline-none focus:border-signal"
              >
                {UI_COLORS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          </label>
        )}
      </div>

      <div className="flex w-full items-stretch gap-1 border border-grid bg-surface/95 p-1.5 shadow-xl backdrop-blur">
        {UI_DESIGNS.map((item) => {
          const active = item.id === designId;
          return (
            <button
              key={item.id}
              type="button"
              title={`${item.name} - ${item.blurb}`}
              aria-pressed={active}
              onClick={() => setDesignId(item.id)}
              className={`flex min-w-0 flex-1 items-center justify-center px-3 py-2 font-mono text-xs uppercase tracking-[0.12em] transition ${
                active
                  ? "bg-signal text-primary-foreground"
                  : "border border-grid bg-background text-muted-foreground hover:border-signal hover:text-foreground"
              }`}
            >
              {item.short}
            </button>
          );
        })}
      </div>
    </div>
  );
}
