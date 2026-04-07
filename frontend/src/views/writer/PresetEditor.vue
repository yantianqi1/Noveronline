<template>
  <n-modal
    :show="visible"
    preset="card"
    :title="isNew ? '新建写作预设' : '编辑写作预设'"
    style="width: 600px; max-width: 90vw"
    :mask-closable="true"
    @update:show="val => { if (!val) $emit('close') }"
  >
    <div class="preset-editor-body">
      <div class="preset-field">
        <label>预设名称</label>
        <n-input v-model:value="form.name" placeholder="如：仙侠凝练风" />
      </div>
      <div class="preset-field">
        <label>说明</label>
        <n-input v-model:value="form.description" placeholder="简要说明此预设的风格特点" />
      </div>
      <div class="preset-field">
        <label>写作提示词 (System Prompt)</label>
        <n-input
          v-model:value="form.system_prompt"
          type="textarea"
          :rows="12"
          placeholder="输入写作层的系统提示词..."
        />
      </div>
    </div>
    <template #footer>
      <div class="preset-editor-footer">
        <n-button @click="$emit('close')">取消</n-button>
        <n-button type="primary" @click="handleSave">保存</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, watch } from "vue";
import { NModal, NInput, NButton } from "naive-ui";

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
.preset-editor-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.preset-field label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 500;
  color: #333;
}
.preset-editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
