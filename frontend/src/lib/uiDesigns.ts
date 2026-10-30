export const UI_DESIGN_IDS = [1, 5] as const;
export type UiDesignId = (typeof UI_DESIGN_IDS)[number];

export const UI_DESIGN_STORAGE_KEY = "bitagents-ui-design";

export type UiDesignMeta = {
  id: UiDesignId;
  name: string;
  blurb: string;
  /** Short label for the switcher chip */
  short: string;
};

export const UI_DESIGNS: UiDesignMeta[] = [
  {
    id: 1,
    name: "Default",
    short: "Default",
    blurb: "Original dark + coral",
  },
  {
    id: 5,
    name: "Graphite",
    short: "Graphite",
    blurb: "Neutral dark UI",
  },
];

export function isUiDesignId(value: unknown): value is UiDesignId {
  return UI_DESIGN_IDS.includes(Number(value) as UiDesignId);
}

export function parseUiDesignId(value: unknown, fallback: UiDesignId = 1): UiDesignId {
  const n = Number(value);
  return isUiDesignId(n) ? n : fallback;
}

/** Color packs for Graphite. Layout stays the same. */
export const UI_COLOR_STORAGE_KEY = "bitagents-ui-color";

export const UI_COLOR_IDS = [1, 2, 3, 4, 5] as const;
export type UiColorId = (typeof UI_COLOR_IDS)[number];

export type UiColorMeta = {
  id: UiColorId;
  name: string;
  /** Accent preview swatch */
  swatch: string;
};

export const UI_COLORS: UiColorMeta[] = [
  { id: 1, name: "Coral", swatch: "#ff7a59" },
  { id: 2, name: "Amber", swatch: "#e8a317" },
  { id: 3, name: "Sky", swatch: "#5b9fd4" },
  { id: 4, name: "Mint", swatch: "#3ecf8e" },
  { id: 5, name: "Copper", swatch: "#c87a3a" },
];

export function isUiColorId(value: unknown): value is UiColorId {
  return UI_COLOR_IDS.includes(Number(value) as UiColorId);
}

export function parseUiColorId(value: unknown, fallback: UiColorId = 1): UiColorId {
  const n = Number(value);
  return isUiColorId(n) ? n : fallback;
}
