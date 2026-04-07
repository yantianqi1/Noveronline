import { zhCN, dateZhCN } from "naive-ui";

export const locale = zhCN;
export const dateLocale = dateZhCN;

export const themeOverrides = {
  common: {
    primaryColor: "#9B2C2C",
    primaryColorHover: "#B83A3A",
    primaryColorPressed: "#742A2A",
    primaryColorSuppl: "#C53030",

    successColor: "#38A169",
    successColorHover: "#48BB78",
    successColorPressed: "#2F855A",

    errorColor: "#E53E3E",
    errorColorHover: "#FC8181",
    errorColorPressed: "#C53030",

    warningColor: "#D69E2E",
    warningColorHover: "#ECC94B",
    warningColorPressed: "#B7791F",

    textColorBase: "#2D3748",
    textColor1: "#2D3748",
    textColor2: "#4A5568",
    textColor3: "#718096",

    dividerColor: "#E2E8F0",
    borderColor: "#E2E8F0",
    inputColor: "#FAF9F6",

    bodyColor: "#FAF9F6",
    cardColor: "#FFFFFF",
    modalColor: "#FFFFFF",
    popoverColor: "#FFFFFF",
    tableColor: "#FFFFFF",

    borderRadius: "5px",
    borderRadiusSmall: "3px",

    fontFamily: '"IBM Plex Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontFamilyMono: '"JetBrains Mono", "Courier New", monospace',
    fontSize: "13px",
    fontSizeMini: "11px",
    fontSizeTiny: "11px",
    fontSizeSmall: "12px",
    fontSizeMedium: "13px",
    fontSizeLarge: "14px",
    fontSizeHuge: "15px",

    heightTiny: "24px",
    heightSmall: "28px",
    heightMedium: "32px",
    heightLarge: "36px",

    boxShadow1: "0 2px 8px rgba(0, 0, 0, 0.04)",
    boxShadow2: "0 4px 16px rgba(0, 0, 0, 0.06)",
    boxShadow3: "0 8px 24px rgba(0, 0, 0, 0.08)",
  },
  Button: {
    borderRadiusTiny: "999px",
    borderRadiusSmall: "999px",
    borderRadiusMedium: "999px",
    borderRadiusLarge: "999px",
    fontWeight: "500",
  },
  Card: {
    borderRadius: "6px",
    paddingSmall: "10px",
    paddingMedium: "14px",
    paddingLarge: "18px",
    paddingHuge: "22px",
    borderColor: "#E2E8F0",
    boxShadow: "0 2px 8px rgba(0, 0, 0, 0.04)",
  },
  Input: {
    color: "#FAF9F6",
    colorFocus: "#FFFFFF",
    borderRadius: "5px",
    caretColor: "#9B2C2C",
    borderHover: "1px solid #9B2C2C",
    borderFocus: "1px solid #9B2C2C",
    boxShadowFocus: "0 0 0 3px rgba(155, 44, 44, 0.1)",
  },
  Select: {
    peers: {
      InternalSelection: {
        color: "#FAF9F6",
        colorActive: "#FFFFFF",
        borderRadius: "5px",
        borderHover: "1px solid #9B2C2C",
        borderFocus: "1px solid #9B2C2C",
        boxShadowFocus: "0 0 0 3px rgba(155, 44, 44, 0.1)",
        caretColor: "#9B2C2C",
      },
    },
  },
  Tag: {
    borderRadius: "999px",
  },
  Dialog: {
    borderRadius: "6px",
  },
  Notification: {
    borderRadius: "6px",
  },
  Popover: {
    borderRadius: "6px",
    boxShadow: "0 4px 16px rgba(0, 0, 0, 0.08)",
  },
  Tooltip: {
    borderRadius: "4px",
  },
  Drawer: {
    borderRadius: "0px",
  },
  Progress: {
    railColor: "#F4F1EA",
    fillColor: "#9B2C2C",
  },
  Empty: {
    textColor: "#718096",
  },
  Skeleton: {
    color: "#F4F1EA",
    colorEnd: "#E2E8F0",
  },
  Tabs: {
    tabTextColorActiveLine: "#9B2C2C",
    barColor: "#9B2C2C",
  },
  DataTable: {
    borderRadius: "6px",
  },
};
