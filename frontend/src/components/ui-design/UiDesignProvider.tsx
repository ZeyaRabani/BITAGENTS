"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { UI_COLORS, UI_DESIGNS, type UiColorId, type UiColorMeta, type UiDesignId, type UiDesignMeta } from "@/lib/uiDesigns";

type UiDesignContextValue = {
  designId: UiDesignId;
  design: UiDesignMeta;
  colorId: UiColorId;
  color: UiColorMeta;
  ready: boolean;
};

const LOCKED_DESIGN: UiDesignId = 5;
const LOCKED_COLOR: UiColorId = 1;

const UiDesignContext = createContext<UiDesignContextValue | null>(null);

export function UiDesignProvider({ children }: { children: ReactNode }) {
  const value = useMemo<UiDesignContextValue>(
    () => ({
      designId: LOCKED_DESIGN,
      design: UI_DESIGNS.find((item) => item.id === LOCKED_DESIGN) ?? UI_DESIGNS[0],
      colorId: LOCKED_COLOR,
      color: UI_COLORS.find((item) => item.id === LOCKED_COLOR) ?? UI_COLORS[0],
      ready: true,
    }),
    []
  );

  return <UiDesignContext.Provider value={value}>{children}</UiDesignContext.Provider>;
}

export function useUiDesign() {
  const ctx = useContext(UiDesignContext);
  if (!ctx) {
    throw new Error("useUiDesign must be used within UiDesignProvider");
  }
  return ctx;
}
