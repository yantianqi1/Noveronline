import { AnimatePresence, motion } from "motion/react";

import { cn } from "@/lib/utils";
import { bindingFor, type ModuleGroup } from "@/lib/api/llm";
import type { LLMChannel, LLMModel, LLMModuleBinding } from "@/lib/api/llm-types";

import { ModuleBindingRow, type RowSaveState } from "./module-binding-row";
import type { ModelChoice } from "./model-picker";

/**
 * One capability family's module list, given the full content width. Rows are
 * readable — the module name, its current model, and the inline picker all have
 * room. On wide screens the family flows into two comfortable columns; narrower
 * screens get a single uncramped column. Only one family shows at a time (the
 * tab bar above swaps it), so nothing is ever squished.
 */
export function ModuleGroupPanel({
  group,
  bindings,
  channels,
  modelsByChannel,
  onSave,
  onReset,
  rowState,
  disabled,
}: {
  group: ModuleGroup;
  bindings: LLMModuleBinding[];
  channels: LLMChannel[];
  /** Lazily-fetched model catalogs, keyed by channel id. */
  modelsByChannel: Record<string, LLMModel[]>;
  onSave: (moduleKey: string, choice: ModelChoice) => void;
  onReset: (moduleKey: string) => void;
  rowState: (moduleKey: string) => RowSaveState;
  disabled?: boolean;
}) {
  const boundCount = group.modules.filter(
    (m) => bindingFor(m.module_key, bindings).kind !== "unbound",
  ).length;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.section
        key={group.key}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className="overflow-hidden rounded-card border border-line bg-panel shadow-[0_1px_2px_rgba(23,26,27,0.05)]"
      >
        <header className="flex items-center justify-between gap-3 border-b border-line-soft bg-paper/40 px-6 py-4">
          <div>
            <h3 className="font-serif text-[17px] font-semibold text-ink">{group.label}</h3>
            {group.hint && <p className="mt-0.5 text-[12.5px] text-muted">{group.hint}</p>}
          </div>
          <span
            className={cn(
              "shrink-0 rounded-full px-2.5 py-1 text-[12px] font-medium",
              boundCount === group.modules.length
                ? "bg-accent-wash text-accent-strong"
                : "bg-paper-deep text-muted",
            )}
          >
            已绑定 {boundCount}/{group.modules.length}
          </span>
        </header>

        <div className="grid gap-x-8 gap-y-1 p-4 sm:p-5 lg:grid-cols-2">
          {group.modules.map((mod) => {
            const state = bindingFor(mod.module_key, bindings);
            const channelId = state.kind === "unbound" ? "" : state.binding.channel_id;
            return (
              <ModuleBindingRow
                key={mod.module_key}
                module={mod}
                state={state}
                channels={channels}
                models={modelsByChannel[channelId] ?? []}
                onSave={onSave}
                onReset={onReset}
                saveState={rowState(mod.module_key)}
                disabled={disabled}
              />
            );
          })}
        </div>
      </motion.section>
    </AnimatePresence>
  );
}
