<template>
  <article class="workbench-card panel full">
    <h2 class="card-title">剧情灵感面板</h2>
    <p class="hint-text">输入创作者灵感，结合当前世界线返回下一步剧情推进建议。</p>
    <div class="field">
      <label>创作灵感</label>
      <textarea
        :value="inspirationPrompt"
        placeholder="例如：我希望主角在两难之间选择一条看似错误但更具戏剧性的道路。"
        @input="emit('update:inspirationPrompt', $event.target.value)"
      ></textarea>
    </div>
    <div class="toolbar-row">
      <button class="btn primary" :disabled="!sessionId || inspirationBusy" @click="emit('generate-inspiration')">
        {{ inspirationBusy ? "生成中..." : "生成剧情灵感" }}
      </button>
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
  margin-top: 10px;
}

.field label {
  display: block;
  margin-bottom: 6px;
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
  margin-top: 12px;
  display: flex;
}

.inspiration-board {
  margin-top: 12px;
  border: 1px solid var(--line-soft);
  background: #fffaf1;
  border-radius: 12px;
  padding: 12px;
}

.seed-title {
  font-weight: 700;
  margin: 10px 0 6px;
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
