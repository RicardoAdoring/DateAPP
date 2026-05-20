<script setup lang="ts">
import {
  ArrowLeftOutlined,
  CarOutlined,
  CloudOutlined,
  DownloadOutlined,
  EditOutlined,
  FileMarkdownOutlined,
  FilePdfOutlined,
  HistoryOutlined,
  OrderedListOutlined,
  SaveOutlined,
  WalletOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { computed, ref, watch } from "vue";

import AmapTripMap from "../components/AmapTripMap.vue";
import {
  fetchWeatherForecast,
  getMarkdownExportUrl,
  getPdfExportUrl,
  saveTrip,
} from "../services/api";
import type { Itinerary, MealItem, SpotItem, TripEditPayload, WeatherForecastResponse } from "../types";

const props = defineProps<{
  itinerary: Itinerary | null;
}>();

const emit = defineEmits<{
  backHome: [];
  viewHistory: [];
  updated: [itinerary: Itinerary];
  startEdit: [payload: TripEditPayload];
}>();

interface TimelineItem {
  key: string;
  kind: "activity" | "meal";
  name: string;
  startTime?: string | null;
  endTime?: string | null;
  address?: string | null;
  description?: string | null;
  estimatedCost?: number;
  imageUrl?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  poiId?: string | null;
}

const saving = ref(false);
const exportingPdf = ref(false);
const exportingMarkdown = ref(false);
const editInstruction = ref("把晚上的安排调整得更有氛围，但不要增加太多预算。");
const weatherLoading = ref(false);
const weather = ref<WeatherForecastResponse | null>(null);

function formatShortDate(dateText?: string | null): string {
  if (!dateText) {
    return "待定";
  }
  const parts = dateText.split("-");
  return parts.length === 3 ? `${parts[1]}-${parts[2]}` : dateText;
}

function itemTime(item: TimelineItem): string {
  if (item.startTime && item.endTime) {
    return `${item.startTime}-${item.endTime}`;
  }
  return item.startTime || "时间待定";
}

const firstDay = computed(() => props.itinerary?.days[0] || null);

const timelineItems = computed<TimelineItem[]>(() => {
  const day = firstDay.value;
  if (!day) {
    return [];
  }
  const spotItems: TimelineItem[] = day.spots.map((spot: SpotItem, index) => ({
    key: `spot-${index}-${spot.name}`,
    kind: "activity",
    name: spot.name,
    startTime: spot.start_time,
    endTime: spot.end_time,
    address: spot.address || spot.location,
    description: spot.description,
    estimatedCost: spot.estimated_cost,
    imageUrl: spot.image_url,
    latitude: spot.latitude,
    longitude: spot.longitude,
    poiId: spot.poi_id,
  }));
  const mealItems: TimelineItem[] = day.meals.map((meal: MealItem, index) => ({
    key: `meal-${index}-${meal.name}`,
    kind: "meal",
    name: meal.name,
    startTime: meal.start_time,
    endTime: meal.end_time,
    address: meal.address || meal.location,
    description: meal.notes,
    estimatedCost: meal.estimated_cost,
    imageUrl: meal.image_url,
    latitude: meal.latitude,
    longitude: meal.longitude,
    poiId: meal.poi_id,
  }));
  return [...spotItems, ...mealItems].sort((a, b) =>
    (a.startTime || "99:99").localeCompare(b.startTime || "99:99")
  );
});

const mapPoints = computed(() =>
  timelineItems.value
    .filter((item) => item.latitude != null && item.longitude != null)
    .map((item, index) => ({
      key: item.key,
      sequence: index + 1,
      dayIndex: 1,
      date: firstDay.value?.date || "待定",
      theme: firstDay.value?.theme || "约会路线",
      name: item.name,
      address: item.address || "地址待补充",
      latitude: item.latitude,
      longitude: item.longitude,
      poiId: item.poiId,
      imageUrl: item.imageUrl,
      description: item.description || "",
      kind: item.kind,
      startTime: item.startTime,
      endTime: item.endTime,
    }))
);

const budgetItems = computed(() => {
  const budget = props.itinerary?.budget_breakdown;
  if (!budget) {
    return [];
  }
  return [
    { label: "餐饮", value: budget.meals },
    { label: "活动", value: budget.tickets },
    { label: "交通", value: budget.transport },
    { label: "弹性", value: budget.other },
  ];
});

const routeSummary = computed(() => {
  const transports = firstDay.value?.transport || [];
  const distance = transports.reduce((sum, item) => sum + (item.distance_km || 0), 0);
  const minutes = transports.reduce((sum, item) => sum + (item.estimated_minutes || 0), 0);
  return {
    distance,
    minutes,
    count: transports.length,
  };
});

async function loadWeather() {
  if (!props.itinerary?.destination) {
    weather.value = null;
    return;
  }
  weatherLoading.value = true;
  try {
    weather.value = await fetchWeatherForecast(props.itinerary.destination);
  } catch (error) {
    console.error(error);
    weather.value = null;
  } finally {
    weatherLoading.value = false;
  }
}

watch(
  () => props.itinerary?.destination,
  () => {
    void loadWeather();
  },
  { immediate: true }
);

function buildVisibleItinerary(): Itinerary | null {
  return props.itinerary ? { ...props.itinerary } : null;
}

async function handleSave() {
  const itinerary = buildVisibleItinerary();
  if (!itinerary) {
    return;
  }
  saving.value = true;
  try {
    await saveTrip(itinerary);
    message.success("路线已保存。");
  } catch (error) {
    console.error(error);
    message.error("保存失败。");
  } finally {
    saving.value = false;
  }
}

async function openPdfExport() {
  const itinerary = buildVisibleItinerary();
  if (!itinerary) {
    return;
  }
  const exportWindow = window.open("about:blank", "_blank");
  exportingPdf.value = true;
  try {
    await saveTrip(itinerary);
    const exportUrl = getPdfExportUrl(itinerary.trip_id);
    if (exportWindow) {
      exportWindow.location.href = exportUrl;
    } else {
      window.location.href = exportUrl;
    }
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("导出 PDF 前保存失败。");
  } finally {
    exportingPdf.value = false;
  }
}

async function openMarkdownExport() {
  const itinerary = buildVisibleItinerary();
  if (!itinerary) {
    return;
  }
  const exportWindow = window.open("about:blank", "_blank");
  exportingMarkdown.value = true;
  try {
    await saveTrip(itinerary);
    const exportUrl = getMarkdownExportUrl(itinerary.trip_id);
    if (exportWindow) {
      exportWindow.location.href = exportUrl;
    } else {
      window.location.href = exportUrl;
    }
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("导出 Markdown 前保存失败。");
  } finally {
    exportingMarkdown.value = false;
  }
}

function handleEdit() {
  if (!props.itinerary || !editInstruction.value.trim()) {
    message.warning("请输入调整要求。");
    return;
  }
  emit("startEdit", {
    trip_id: props.itinerary.trip_id,
    current_itinerary: props.itinerary,
    user_instruction: editInstruction.value.trim(),
    edit_scope: "day_1",
    preserve_constraints: ["保留约会中心点", "保留预算结构", "保留一日路线"],
  });
}
</script>

<template>
  <section v-if="itinerary" class="result-page">
    <div class="action-toolbar">
      <button type="button" class="toolbar-button" @click="$emit('backHome')">
        <ArrowLeftOutlined />
        <span>返回规划</span>
      </button>
      <button type="button" class="toolbar-button toolbar-button--primary" :disabled="saving" @click="handleSave">
        <SaveOutlined />
        <span>{{ saving ? "保存中..." : "保存路线" }}</span>
      </button>
      <button type="button" class="toolbar-button" @click="$emit('viewHistory')">
        <HistoryOutlined />
        <span>历史列表</span>
      </button>
      <button type="button" class="toolbar-button" :disabled="exportingPdf" @click="openPdfExport">
        <FilePdfOutlined />
        <span>{{ exportingPdf ? "准备 PDF..." : "导出 PDF" }}</span>
      </button>
      <button type="button" class="toolbar-button" :disabled="exportingMarkdown" @click="openMarkdownExport">
        <FileMarkdownOutlined />
        <span>{{ exportingMarkdown ? "准备中..." : "导出 Markdown" }}</span>
      </button>
    </div>

    <section class="summary-band">
      <div class="summary-copy">
        <span class="eyebrow">Date Route</span>
        <h1>{{ itinerary.destination }}</h1>
        <p>{{ itinerary.summary }}</p>
      </div>
      <div class="summary-stats">
        <div>
          <strong>¥{{ itinerary.estimated_budget.toFixed(0) }}</strong>
          <span>预计预算</span>
        </div>
        <div>
          <strong>{{ timelineItems.length }}</strong>
          <span>停靠点</span>
        </div>
        <div>
          <strong>{{ routeSummary.distance.toFixed(1) }} km</strong>
          <span>{{ routeSummary.minutes || "待估" }} 分钟</span>
        </div>
      </div>
    </section>

    <section class="map-section">
      <AmapTripMap :points="mapPoints" />
    </section>

    <section class="content-grid">
      <div class="panel panel--wide">
        <div class="panel-title">
          <div>
            <OrderedListOutlined />
            <span>一日时间线</span>
          </div>
          <small>{{ formatShortDate(firstDay?.date) }} · {{ firstDay?.theme || "约会路线" }}</small>
        </div>
        <div class="timeline">
          <article v-for="(item, index) in timelineItems" :key="item.key" class="timeline-item">
            <div class="timeline-index">{{ index + 1 }}</div>
            <div class="timeline-time">{{ itemTime(item) }}</div>
            <div class="timeline-body">
              <div class="timeline-head">
                <strong>{{ item.name }}</strong>
                <span>{{ item.kind === "meal" ? "餐饮" : "活动" }}</span>
              </div>
              <p>{{ item.description || "暂无说明" }}</p>
              <small>{{ item.address || "地址待补充" }}</small>
            </div>
            <div class="timeline-cost">¥{{ (item.estimatedCost || 0).toFixed(0) }}</div>
          </article>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <div>
            <WalletOutlined />
            <span>预算拆分</span>
          </div>
        </div>
        <div class="budget-list">
          <div v-for="item in budgetItems" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>¥{{ item.value.toFixed(0) }}</strong>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <div>
            <CarOutlined />
            <span>路线交通</span>
          </div>
          <small>{{ routeSummary.count }} 段</small>
        </div>
        <div class="transport-list">
          <div v-for="(item, index) in firstDay?.transport || []" :key="`${item.from_place}-${item.to_place}-${index}`">
            <strong>{{ item.from_place }} → {{ item.to_place }}</strong>
            <span>
              {{ item.mode }} ·
              {{ item.distance_km != null ? `${item.distance_km.toFixed(1)} km` : "距离待估" }} ·
              {{ item.duration || "耗时待估" }}
            </span>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <div>
            <CloudOutlined />
            <span>天气参考</span>
          </div>
        </div>
        <div v-if="weatherLoading" class="muted">正在加载天气...</div>
        <div v-else-if="weather?.days?.length" class="weather-list">
          <div v-for="day in weather.days.slice(0, 3)" :key="`${day.date}-${day.week}`">
            <strong>{{ formatShortDate(day.date) }}</strong>
            <span>{{ day.day_weather || "未知" }} / {{ day.day_temp || "-" }}°</span>
          </div>
        </div>
        <div v-else class="muted">暂无天气数据。</div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <div>
            <EditOutlined />
            <span>智能调整</span>
          </div>
        </div>
        <a-textarea v-model:value="editInstruction" :rows="4" />
        <a-button type="primary" class="edit-button" @click="handleEdit">
          <template #icon>
            <EditOutlined />
          </template>
          调整路线
        </a-button>
      </div>

      <div class="panel panel--wide">
        <div class="panel-title">
          <div>
            <DownloadOutlined />
            <span>提示与来源</span>
          </div>
        </div>
        <ul class="tips">
          <li v-for="tip in itinerary.tips" :key="tip">{{ tip }}</li>
        </ul>
        <div v-if="itinerary.source_links?.length" class="source-list">
          <a
            v-for="source in itinerary.source_links"
            :key="`${source.title}-${source.url}`"
            :href="source.url || '#'"
            target="_blank"
            rel="noreferrer"
          >
            {{ source.title }}
          </a>
        </div>
      </div>
    </section>
  </section>

  <section v-else class="empty-state">
    <div>
      <h2>还没有路线</h2>
      <p>先回到规划页选择一个地点，再生成约会一日游安排。</p>
      <button type="button" @click="$emit('backHome')">
        <ArrowLeftOutlined />
        <span>返回规划</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.result-page {
  display: grid;
  gap: 16px;
}

.action-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 28px rgba(15, 32, 51, 0.06);
}

.toolbar-button,
.empty-state button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 9px 12px;
  background: var(--surface);
  color: var(--ink);
  font-weight: 850;
  cursor: pointer;
}

.toolbar-button--primary {
  border-color: var(--accent);
  background: var(--accent);
  color: #ffffff;
}

.toolbar-button:disabled {
  opacity: 0.62;
  cursor: wait;
}

.summary-band,
.panel,
.map-section,
.empty-state > div {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.summary-band {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 390px);
  gap: 22px;
  align-items: stretch;
  padding: 20px;
}

.summary-copy {
  min-width: 0;
}

.eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 900;
}

.summary-band h1 {
  margin: 6px 0 10px;
  color: var(--ink);
  font-size: 30px;
  line-height: 1.18;
}

.summary-band p {
  max-width: 760px;
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.75;
}

.summary-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-stats div {
  display: grid;
  align-content: center;
  gap: 5px;
  padding: 12px;
  border: 1px solid #e5ebf0;
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.summary-stats strong {
  overflow: hidden;
  color: var(--teal);
  font-size: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-stats span {
  color: var(--muted);
  font-size: 12px;
}

.map-section {
  min-height: 430px;
  padding: 10px;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 16px;
}

.panel--wide {
  grid-column: 1 / -1;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8edf2;
}

.panel-title div {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 17px;
  font-weight: 900;
}

.panel-title .anticon {
  color: var(--teal);
}

.panel-title small,
.muted {
  color: var(--muted);
}

.timeline {
  display: grid;
  gap: 9px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 34px 116px minmax(0, 1fr) 72px;
  gap: 12px;
  align-items: start;
  padding: 12px;
  border: 1px solid #e5ebf0;
  border-radius: var(--radius);
  background: #fbfcfd;
}

.timeline-index {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 900;
}

.timeline-time {
  color: var(--teal);
  font-weight: 900;
  line-height: 1.5;
}

.timeline-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.timeline-head strong {
  color: var(--ink);
  font-size: 16px;
}

.timeline-head span {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 850;
}

.timeline-body p {
  margin: 0 0 6px;
  color: var(--ink-soft);
  line-height: 1.65;
}

.timeline-body small {
  color: var(--muted);
}

.timeline-cost {
  color: var(--ink);
  font-weight: 900;
  text-align: right;
}

.budget-list,
.transport-list,
.weather-list {
  display: grid;
  gap: 8px;
}

.budget-list div,
.transport-list div,
.weather-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #edf1f5;
  color: var(--ink-soft);
}

.transport-list div {
  display: grid;
  justify-content: stretch;
}

.budget-list strong,
.transport-list strong,
.weather-list strong {
  color: var(--ink);
}

.edit-button {
  justify-self: start;
  border-radius: 6px;
  font-weight: 900;
}

.tips {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: var(--ink-soft);
  line-height: 1.7;
}

.source-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-list a {
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--teal);
  text-decoration: none;
  font-size: 13px;
  font-weight: 800;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 360px;
}

.empty-state > div {
  display: grid;
  justify-items: center;
  max-width: 480px;
  gap: 12px;
  padding: 28px;
  text-align: center;
}

.empty-state h2 {
  margin: 0;
  color: var(--ink);
}

.empty-state p {
  margin: 0;
  color: var(--muted);
}

@media (max-width: 980px) {
  .summary-band,
  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .timeline-item {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .timeline-time,
  .timeline-body,
  .timeline-cost {
    grid-column: 2;
  }

  .timeline-cost {
    text-align: left;
  }

  .summary-stats {
    grid-template-columns: 1fr;
  }
}
</style>
