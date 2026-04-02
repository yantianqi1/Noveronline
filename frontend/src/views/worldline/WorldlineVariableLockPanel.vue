<template>
  <section v-if="worldVariables.length" class="panel-section lock-section">
    <div class="section-head">
      <div>
        <p class="section-index mono">{{ sectionIndex }}</p>
        <h3 class="section-title">变量锁定</h3>
      </div>
      <p class="section-copy">锁定的变量将作为约束条件传入下一轮自动演化，LLM 在生成候选事件时会遵守这些不变量。</p>
    </div>

    <div class="lock-summary">
      <span class="lock-count mono">{{ lockedCount }} / {{ worldVariables.length }} 已锁定</span>
      <div class="lock-batch">
        <button
          class="btn btn-sm"
          type="button"
          :disabled="lockedCount === worldVariables.length"
          @click="emit('lock-all')"
        >
          全部锁定
        </button>
        <button
          class="btn btn-sm"
          type="button"
          :disabled="lockedCount === 0"
          @click="emit('unlock-all')"
        >
          全部解锁
        </button>
      </div>
    </div>

    <div class="lock-list">
      <article
        v-for="variable in worldVariables"
        :key="variable.variable_id"
        class="lock-card"
        :class="{ locked: isLocked(variable.variable_id) }"
      >
        <button
          class="lock-toggle"
          type="button"
          :title="isLocked(variable.variable_id) ? '解锁此变量' : '锁定此变量'"
          :aria-label="isLocked(variable.variable_id) ? '解锁此变量' : '锁定此变量'"
          @click="emit('toggle-lock', variable.variable_id)"
        >
          <span v-if="isLocked(variable.variable_id)" class="lock-icon locked-icon">&#x1F512;</span>
          <span v-else class="lock-icon unlocked-icon">&#x1F513;</span>
        </button>
        <div class="lock-body">
          <strong class="lock-name">{{ variable.name }}</strong>
          <p class="lock-desc">{{ variable.description }}</p>
          <div class="lock-meta">
            <span v-if="variable.impact_axis" class="lock-axis mono">{{ variable.impact_axis }}</span>
            <span class="lock-source mono">{{ sourceLabel(variable.source) }}</span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const SOURCE_LABELS = {
  user: "用户注入",
  system: "系统生成",
  llm: "LLM 推导",
};

const props = defineProps({
  sectionIndex: { type: String, default: "03 / 变量锁定" },
  worldVariables: { type: Array, default: () => [] },
  lockedVariableIds: { type: Set, default: () => new Set() },
});

const emit = defineEmits(["toggle-lock", "lock-all", "unlock-all"]);

const lockedCount = computed(() => {
  let count = 0;
  for (const variable of props.worldVariables) {
    if (props.lockedVariableIds.has(variable.variable_id)) {
      count += 1;
    }
  }
  return count;
});

function isLocked(variableId) {
  return props.lockedVariableIds.has(variableId);
}

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source || "未知";
}
</script>

<style scoped src="./WorldlineVariableLockPanel.css"></style>
