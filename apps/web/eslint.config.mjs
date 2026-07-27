import tseslint from "typescript-eslint";

/**
 * Design-token lint, deliberately narrow.
 *
 * The repo has no other lint config, so this enables exactly one local rule and
 * no preset — turning on `recommended` here would bury the design findings under
 * hundreds of unrelated warnings on day one. The parser is loaded only so JSX
 * string literals can be read.
 *
 * These checks mirror tests/design-tokens.test.mjs, which is the CI gate; this
 * config exists so a drift is flagged in the editor as it is typed rather than
 * at test time. Keep the two in sync when adding a token.
 *
 * Implemented as a local rule rather than `no-restricted-syntax` because
 * esquery's attribute-regex syntax cannot express patterns containing `[`, `]`,
 * or `/` — which every one of these needs.
 */
const DENY = [
  [/\btext-\[[0-9.]+(px|rem|em)\]/, "Off-scale font size. Use text-caption|sm|base|md|lg|xl|display|reading."],
  [/\bleading-\[[0-9.]+\]/, "Line height ships paired with each --text-* token; drop the override."],
  [/\brounded(-[a-z]{1,2})?-\[[^\]]+\]/, "Off-scale radius. Use rounded-control|panel|modal."],
  [/\brounded-(xs|sm|md|lg|xl|2xl|3xl|4xl)\b/, "Tailwind's stock radii are cleared in @theme. Use rounded-control|panel|modal."],
  [/\bshadow-\[[^\]]+\]/, "Hand-written shadow. Use shadow-hairline|lift|panel|accent|ink."],
  [/\bshadow-(2xs|xs|sm|md|lg|xl|2xl)\b/, "Tailwind's stock shadows are cleared in @theme."],
  [/\b(text|bg|border|ring|fill|stroke|from|via|to)-\[(#|rgba?\()/, "Hardcoded colour. Add a token to @theme and use it."],
  [
    /\b(text|bg|border|ring)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}\b/,
    "Stock Tailwind palette clashes with paper & vermilion. Use the semantic tokens.",
  ],
  [/\btext-muted\/[0-9]+/, "Alpha-tinted grey falls under 4.5:1 on paper. Use text-muted-soft."],
  [/\bitalic\b/, "Hanzi has no italic forms; the synthesised skew reads as a bug. Use font-serif or a weight."],
];

const designTokens = {
  rules: {
    "no-off-scale-utilities": {
      meta: {
        type: "problem",
        docs: { description: "Keep Tailwind utilities on the @theme token scale." },
        schema: [],
      },
      create(context) {
        const check = (node, text) => {
          if (typeof text !== "string") return;
          for (const [pattern, message] of DENY) {
            const match = text.match(pattern);
            if (match) {
              context.report({ node, message: `${message} (found "${match[0]}")` });
              return;
            }
          }
        };
        return {
          Literal: (node) => check(node, node.value),
          TemplateElement: (node) => check(node, node.value.raw),
        };
      },
    },
  },
};

/**
 * Inert stand-ins for the hook rules the codebase already writes
 * `eslint-disable-next-line` comments for. ESLint errors on a directive naming
 * a rule it cannot resolve, and this config intentionally does not lint hooks —
 * enabling eslint-plugin-react-hooks is worth doing, but as its own change with
 * its own findings to triage, not as a side effect of the design-token gate.
 */
const reactHooksStub = {
  rules: Object.fromEntries(
    ["exhaustive-deps", "rules-of-hooks"].map((name) => [
      name,
      { meta: { schema: [] }, create: () => ({}) },
    ]),
  ),
};

export default tseslint.config(
  { ignores: ["node_modules/**", ".next/**", ".next-dev/**", "scripts/**", "tests/**"] },
  {
    files: ["app/**/*.tsx", "components/**/*.tsx"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "design-tokens": designTokens, "react-hooks": reactHooksStub },
    rules: { "design-tokens/no-off-scale-utilities": "error" },
    linterOptions: { reportUnusedDisableDirectives: "off" },
  },
);
