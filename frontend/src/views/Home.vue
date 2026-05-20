<script setup lang="ts">
import {
  AimOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  EnvironmentOutlined,
  SendOutlined,
  SlidersOutlined,
  TeamOutlined,
  WalletOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { computed, reactive, ref } from "vue";

import LocationPickerMap from "../components/LocationPickerMap.vue";
import type { DatePlanRequestPayload, SelectedLocation } from "../types";

const emit = defineEmits<{
  startGeneration: [payload: DatePlanRequestPayload];
}>();

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const selectedLocation = ref<SelectedLocation | null>(null);

const preferenceOptions = [
  "轻松聊天",
  "拍照打卡",
  "美食探店",
  "展览电影",
  "公园散步",
  "夜景氛围",
];

const dietaryOptions = ["少辣", "不吃香菜", "清淡", "甜品", "咖啡", "不喝酒"];

const transportOptions = [
  { label: "步行 + 公共交通", value: "walking_transit" },
  { label: "主要步行", value: "walking" },
  { label: "打车优先", value: "taxi" },
];

const formState = reactive({
  date: formatDate(new Date()),
  startTime: "10:00",
  endTime: "22:00",
  travelers: 2,
  budget: 900,
  radiusMeters: 3000,
  transportMode: "walking_transit",
  preferences: ["轻松聊天", "美食探店", "夜景氛围"],
  dietaryPreferences: ["少辣"],
  notes: "希望路线不要太赶，适合第一次约会，有能自然聊天的地方。",
});

const selectedSummary = computed(() => {
  if (!selectedLocation.value) {
    return "等待选择中心点";
  }
  return selectedLocation.value.name || selectedLocation.value.address || "已选择地图点位";
});

const selectedAddress = computed(() => {
  if (!selectedLocation.value) {
    return "坐标和地址会显示在这里";
  }
  return selectedLocation.value.address || "地址待补充";
});

const radiusLabel = computed(() =>
  formState.radiusMeters >= 1000
    ? `${(formState.radiusMeters / 1000).toFixed(1)} km`
    : `${formState.radiusMeters} m`
);

const budgetLabel = computed(() => `¥${Number(formState.budget || 0).toFixed(0)}`);

function handleSubmit() {
  if (!selectedLocation.value) {
    message.warning("请先搜索或点击地图选择一个地点。");
    return;
  }

  const payload: DatePlanRequestPayload = {
    anchor: selectedLocation.value,
    date: formState.date,
    start_time: formState.startTime,
    end_time: formState.endTime,
    travelers: formState.travelers,
    budget: formState.budget,
    preferences: formState.preferences,
    dietary_preferences: formState.dietaryPreferences,
    transport_mode: formState.transportMode,
    radius_meters: formState.radiusMeters,
    special_notes: formState.notes,
  };

  emit("startGeneration", payload);
}
</script>

<template>
  <section class="home-page">
    <div class="workspace-header">
      <div class="title-stack">
        <span class="eyebrow">Date Workbench</span>
        <h1>约会一日游规划</h1>
      </div>
      <div class="current-location">
        <EnvironmentOutlined />
        <div>
          <span>当前中心点</span>
          <strong>{{ selectedSummary }}</strong>
          <small>{{ selectedAddress }}</small>
        </div>
      </div>
    </div>

    <LocationPickerMap v-model="selectedLocation" />

    <section class="planner-panel">
      <div class="panel-title">
        <div>
          <SlidersOutlined />
          <span>约会参数</span>
        </div>
        <small>{{ formState.startTime }}-{{ formState.endTime }} · {{ budgetLabel }} · {{ radiusLabel }}</small>
      </div>

      <div class="quick-grid">
        <label class="field-card">
          <span><CalendarOutlined /> 日期</span>
          <a-input v-model:value="formState.date" />
        </label>
        <label class="field-card">
          <span><ClockCircleOutlined /> 开始</span>
          <a-input v-model:value="formState.startTime" />
        </label>
        <label class="field-card">
          <span><ClockCircleOutlined /> 结束</span>
          <a-input v-model:value="formState.endTime" />
        </label>
        <label class="field-card">
          <span><TeamOutlined /> 人数</span>
          <a-input-number v-model:value="formState.travelers" :min="1" style="width: 100%" />
        </label>
        <label class="field-card">
          <span><WalletOutlined /> 预算</span>
          <a-input-number v-model:value="formState.budget" :min="0" style="width: 100%" />
        </label>
        <label class="field-card">
          <span><AimOutlined /> 半径</span>
          <a-slider
            v-model:value="formState.radiusMeters"
            :min="500"
            :max="10000"
            :step="500"
          />
          <small>{{ radiusLabel }}</small>
        </label>
      </div>

      <div class="option-grid">
        <label class="option-block">
          <span>交通方式</span>
          <a-select v-model:value="formState.transportMode" :options="transportOptions" />
        </label>
        <label class="option-block">
          <span>路线风格</span>
          <a-checkbox-group v-model:value="formState.preferences" :options="preferenceOptions" />
        </label>
        <label class="option-block">
          <span>饮食偏好</span>
          <a-checkbox-group v-model:value="formState.dietaryPreferences" :options="dietaryOptions" />
        </label>
      </div>

      <label class="note-block">
        <span>额外要求</span>
        <a-textarea
          v-model:value="formState.notes"
          :rows="3"
          placeholder="例如：不要太赶、想看夜景、晚餐想安静一点、不要安排太贵的餐厅"
        />
      </label>

      <div class="submit-bar">
        <a-button
          type="primary"
          size="large"
          :disabled="!selectedLocation"
          @click="handleSubmit"
        >
          <template #icon>
            <SendOutlined />
          </template>
          生成约会路线
        </a-button>
        <span>{{ selectedLocation ? "中心点已就绪" : "中心点未选择" }}</span>
      </div>
    </section>
  </section>
</template>

<style scoped>
.home-page {
  display: grid;
  gap: 16px;
}

.workspace-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: end;
  padding: 10px 0 0;
}

.title-stack {
  min-width: 0;
}

.eyebrow {
  color: var(--accent);
  font-size: 13px;
  font-weight: 900;
}

.workspace-header h1 {
  margin: 5px 0 0;
  color: var(--ink);
  font-size: 32px;
  line-height: 1.16;
}

.current-location {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  width: min(430px, 100%);
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: 0 12px 28px rgba(15, 32, 51, 0.05);
}

.current-location > .anticon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--accent);
}

.current-location div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.current-location span,
.current-location small {
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-location strong {
  overflow: hidden;
  color: var(--ink);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.planner-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-title {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 1px solid #e8edf2;
}

.panel-title div {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 18px;
  font-weight: 900;
}

.panel-title .anticon {
  color: var(--teal);
}

.panel-title small {
  color: var(--muted);
  line-height: 1.5;
  text-align: right;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.field-card,
.option-block,
.note-block {
  display: grid;
  min-width: 0;
  gap: 8px;
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 800;
}

.field-card {
  padding: 12px;
  border: 1px solid #e5ebf0;
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.field-card > span,
.option-block > span,
.note-block > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.field-card .anticon {
  color: var(--teal);
}

.field-card small {
  color: var(--muted);
  font-size: 12px;
}

.option-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.7fr) minmax(260px, 1fr) minmax(260px, 1fr);
  gap: 14px;
}

.option-block {
  align-content: start;
}

.option-block :deep(.ant-checkbox-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.option-block :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
  color: var(--ink-soft);
}

.note-block :deep(textarea) {
  resize: vertical;
}

.submit-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-top: 2px;
}

.submit-bar :deep(.ant-btn) {
  min-width: 178px;
  border-radius: 6px;
  font-weight: 900;
}

.submit-bar span {
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 1120px) {
  .quick-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .option-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .workspace-header,
  .panel-title,
  .submit-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .current-location {
    width: 100%;
  }

  .workspace-header h1 {
    font-size: 27px;
  }

  .quick-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .panel-title small {
    text-align: left;
  }
}

@media (max-width: 480px) {
  .quick-grid {
    grid-template-columns: 1fr;
  }
}
</style>
