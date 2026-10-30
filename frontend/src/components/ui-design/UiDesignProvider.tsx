"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  parseUiColorId,
  parseUiDesignId,
  UI_COLOR_STORAGE_KEY,
  UI_COLORS,
  UI_DESIGN_STORAGE_KEY,
  UI_DESIGNS,
  type UiColorId,
  type UiColorMeta,
  type UiDesignId,
  type UiDesignMeta,
} from "@/lib/uiDesigns";

type UiDesignContextValue = {
  designId: UiDesignId;
  design: UiDesignMeta;
  setDesignId: (id: UiDesignId) => void;
  colorId: UiColorId;
  color: UiColorMeta;
  setColorId: (id: UiColorId) => void;
  ready: boolean;
};

const UiDesignContext = createContext<UiDesignContextValue | null>(null);

function applyToDocument(designId: UiDesignId, colorId: UiColorId) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.uiDesign = String(designId);
  document.documentElement.dataset.uiColor = String(colorId);
  document.documentElement.classList.add("dark");
}

export function UiDesignProvider({ children }: { children: ReactNode }) {
  const [designId, setDesignIdState] = useState<UiDesignId>(1);
  const [colorId, setColorIdState] = useState<UiColorId>(1);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const nextDesign = parseUiDesignId(window.localStorage.getItem(UI_DESIGN_STORAGE_KEY), 1);
      const nextColor = parseUiColorId(window.localStorage.getItem(UI_COLOR_STORAGE_KEY), 1);
      setDesignIdState(nextDesign);
      setColorIdState(nextColor);
      applyToDocument(nextDesign, nextColor);
    } catch {
      applyToDocument(1, 1);
    } finally {
      setReady(true);
    }
  }, []);

  const setDesignId = useCallback(
    (id: UiDesignId) => {
      setDesignIdState(id);
      applyToDocument(id, colorId);
      try {
        window.localStorage.setItem(UI_DESIGN_STORAGE_KEY, String(id));
      } catch {
        // ignore
      }
    },
    [colorId]
  );

  const setColorId = useCallback(
    (id: UiColorId) => {
      setColorIdState(id);
      applyToDocument(designId, id);
      try {
        window.localStorage.setItem(UI_COLOR_STORAGE_KEY, String(id));
      } catch {
        // ignore
      }
    },
    [designId]
  );

  const value = useMemo<UiDesignContextValue>(
    () => ({
      designId,
      design: UI_DESIGNS.find((d) => d.id === designId) ?? UI_DESIGNS[0],
      setDesignId,
      colorId,
      color: UI_COLORS.find((c) => c.id === colorId) ?? UI_COLORS[0],
      setColorId,
      ready,
    }),
    [designId, setDesignId, colorId, setColorId, ready]
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
