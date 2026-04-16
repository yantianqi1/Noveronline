type PercentSize = `${number}%`;

interface PanelLayout {
  readonly defaultSize: PercentSize;
  readonly minSize: PercentSize;
  readonly maxSize?: PercentSize;
}

interface WorldlineLayoutMode {
  readonly panels: {
    readonly left: PanelLayout;
    readonly center: PanelLayout;
    readonly right: PanelLayout;
  };
}

export const WORLDLINE_PANEL_LAYOUT = {
  expanded: {
    panels: {
      left: { defaultSize: "32%", minSize: "20%", maxSize: "60%" },
      center: { defaultSize: "34%", minSize: "24%" },
      right: { defaultSize: "34%", minSize: "24%" },
    },
  },
  collapsed: {
    panels: {
      left: { defaultSize: "3%", minSize: "3%", maxSize: "8%" },
      center: { defaultSize: "43%", minSize: "28%" },
      right: { defaultSize: "54%", minSize: "30%" },
    },
  },
} as const satisfies Record<string, WorldlineLayoutMode>;
