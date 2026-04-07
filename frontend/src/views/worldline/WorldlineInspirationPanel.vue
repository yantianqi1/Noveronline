<template>
  <article class="workbench-card panel full">
    <h2 class="card-title">剧情灵感面板</h2>
    <p class="hint-text">输入创作者灵感，结合当前世界线返回下一步剧情推进建议。</p>
    <div class="field">
      <label>创作灵感</label>
      <n-input
        type="textarea"
        :value="inspirationPrompt"
        placeholder="例如：我希望主角在两难之间选择一条看似错误但更具戏剧性的道路。"
        :rows="4"
        @update:value="emit('update:inspirationPrompt', $event)"
      />
    </div>
    <div class="toolbar-row">
      <n-button type="primary" :disabled="!sessionId || inspirationBusy" :loading="inspirationBusy" @click="emit('generate-inspiration')">
        生成剧情灵感
      </n-button>
    </div>

    <div v-if="inspirationResult" class="inspiration-board">
      <div class="seed-title">总览</div>
      <p>{{ inspirationResult.overview || "暂无总览" }}</p>

      <div class="seed-title">下一步剧情</div>
      <div class="suggestion-item" v-for="(item, idx) in inspirationResult.next_beats || []" :key="`beat_${idx}`">
        {{ idx + 1 }}. {{ item }}
      </div>

      <div class="seed-title">冲突升级建议</div>
      <div class="suggestion-item" v-for="(item, idx) in inspirationResult.conflict_upgrades || []" :key="`conflict_${idx}`">
        {{ idx + 1 }}. {{ item }}
      </div>
    </div>
    <p class="feedback error" v-if="inspirationError">{{ inspirationError }}</p>
  </article>
</template>

<script setup>
import { NButton, NInput } from "naive-ui";

const props = defineProps({
  sessionId: String,
  inspirationPrompt: String,
  inspirationResult: Object,
  inspirationError: String,
  inspirationBusy: Boolean,
});

const emit = defineEmits(["update:inspirationPrompt", "generate-inspiration"]);
</script>

<style scoped>
.field {
  margin-top: 8px;
}

.field label {
  display: block;
  margin-bottom: 4px;
}

.field textarea {
  width: 100%;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 10px;
  font-family: var(--body-font);
  background: #fffdf7;
  min-height: 96px;
}

.toolbar-row {
  margin-top: 8px;
  display: flex;
}

.inspiration-board {
  margin-top: 8px;
  border: 1px solid var(--line-soft);
  background: #fffaf1;
  border-radius: 8px;
  padding: 10px;
}

.seed-title {
  font-weight: 700;
  margin: 8px 0 4px;
}

.suggestion-item {
  border-top: 1px dashed var(--line-soft);
  padding: 7px 0;
}

.suggestion-item:first-of-type {
  border-top: none;
}

.feedback.error {
  margin-top: 12px;
  color: #9b4326;
}
</style>
