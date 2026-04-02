<template>
  <div v-if="visible" class="preset-editor-overlay" @click.self="$emit('close')">
    <div class="preset-editor-modal">
      <div class="preset-editor-header">
        <h3>{{ isNew ? '新建写作预设' : '编辑写作预设' }}</h3>
        <button class="preset-close-btn" @click="$emit('close')">×</button>
      </div>
      <div class="preset-editor-body">
        <div class="preset-field">
          <label>预设名称</label>
          <input v-model="form.name" placeholder="如：仙侠凝练风" />
        </div>
        <div class="preset-field">
          <label>说明</label>
          <input v-model="form.description" placeholder="简要说明此预设的风格特点" />
        </div>
        <div class="preset-field">
          <label>写作提示词 (System Prompt)</label>
          <textarea
            v-model="form.system_prompt"
            rows="12"
            placeholder="输入写作层的系统提示词..."
          ></textarea>
        </div>
      </div>
      <div class="preset-editor-footer">
        <button class="preset-btn preset-btn--cancel" @click="$emit('close')">取消</button>
        <button class="preset-btn preset-btn--save" @click="handleSave">保存</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  preset: { type: Object, default: null },
});

const emit = defineEmits(["save", "close"]);

const isNew = ref(true);
const form = ref({ name: "", description: "", system_prompt: "" });

watch(
  () => props.preset,
  (val) => {
    if (val) {
      isNew.value = false;
      form.value = {
        name: val.name || "",
        description: val.description || "",
        system_prompt: val.system_prompt || "",
      };
    } else {
      isNew.value = true;
      form.value = { name: "", description: "", system_prompt: "" };
    }
  },
  { immediate: true }
);

function handleSave() {
  if (!form.value.name.trim()) return;
  if (!form.value.system_prompt.trim()) return;
  emit("save", {
    ...form.value,
    preset_id: props.preset?.preset_id || null,
  });
}
</script>

<style scoped>
.preset-editor-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.preset-editor-modal {
  background: #fff;
  border-radius: 8px;
  width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}
.preset-editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}
.preset-editor-header h3 { margin: 0; font-size: 16px; }
.preset-close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
}
.preset-editor-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.preset-field {
  margin-bottom: 16px;
}
.preset-field label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #333;
}
.preset-field input,
.preset-field textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
  font-family: inherit;
}
.preset-field textarea {
  resize: vertical;
  min-height: 200px;
  line-height: 1.6;
}
.preset-field input:focus,
.preset-field textarea:focus {
  outline: none;
  border-color: #409eff;
}
.preset-editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #eee;
}
.preset-btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: 1px solid #ddd;
}
.preset-btn--cancel { background: #fff; color: #666; }
.preset-btn--save { background: #409eff; color: #fff; border-color: #409eff; }
.preset-btn--save:hover { background: #66b1ff; }
</style>
