<script setup lang="ts">
import {
  DeleteOutlined,
  EyeOutlined,
  HistoryOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { onMounted, ref, watch } from "vue";

import { deleteTrip, getTripDetail, listTrips } from "../services/api";
import type { Itinerary, TripSummaryItem } from "../types";

const props = defineProps<{
  active: boolean;
}>();

const emit = defineEmits<{
  openTrip: [itinerary: Itinerary];
}>();

const loading = ref(false);
const items = ref<TripSummaryItem[]>([]);
const deletingTripId = ref("");

async function loadTrips() {
  loading.value = true;
  try {
    const response = await listTrips();
    items.value = response.items;
  } catch (error) {
    console.error(error);
    message.error("历史列表加载失败。");
  } finally {
    loading.value = false;
  }
}

async function openTrip(tripId: string) {
  try {
    const response = await getTripDetail(tripId);
    emit("openTrip", response.itinerary);
    message.success("已加载已保存行程。");
  } catch (error) {
    console.error(error);
    message.error("读取行程详情失败。");
  }
}

async function removeTrip(tripId: string) {
  const confirmed = window.confirm("确定要删除这条已保存行程吗？删除后无法恢复。");
  if (!confirmed) {
    return;
  }

  deletingTripId.value = tripId;
  try {
    await deleteTrip(tripId);
    items.value = items.value.filter((item) => item.trip_id !== tripId);
    message.success("行程已删除。");
  } catch (error) {
    console.error(error);
    message.error("删除行程失败。");
  } finally {
    deletingTripId.value = "";
  }
}

onMounted(() => {
  if (props.active) {
    void loadTrips();
  }
});

watch(
  () => props.active,
  (active) => {
    if (active) {
      void loadTrips();
    }
  }
);
</script>

<template>
  <section class="history-page">
    <div class="history-header">
      <div>
        <span class="eyebrow"><HistoryOutlined /> History</span>
        <h2>历史行程</h2>
      </div>
      <button class="refresh-button" type="button" @click="loadTrips">
        <ReloadOutlined />
        <span>刷新列表</span>
      </button>
    </div>

    <div v-if="loading" class="history-state">正在加载历史列表...</div>
    <div v-else-if="items.length === 0" class="history-state">还没有已保存的行程。</div>

    <div v-else class="history-grid">
      <article
        v-for="item in items"
        :key="item.trip_id"
        class="history-card"
      >
        <div class="history-card__top">
          <div>
            <strong>{{ item.destination }}</strong>
            <span>{{ item.updated_at || "未记录更新时间" }}</span>
          </div>
        </div>
        <p class="history-card__summary">{{ item.summary }}</p>
        <div class="history-card__trip-id">{{ item.trip_id }}</div>
        <div class="history-card__actions">
          <button class="history-card__button history-card__button--primary" type="button" @click="openTrip(item.trip_id)">
            <EyeOutlined />
            <span>查看详情</span>
          </button>
          <button
            class="history-card__button history-card__button--danger"
            type="button"
            :disabled="deletingTripId === item.trip_id"
            @click="removeTrip(item.trip_id)"
          >
            <DeleteOutlined />
            <span>{{ deletingTripId === item.trip_id ? "删除中..." : "删除行程" }}</span>
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.history-page {
  display: grid;
  gap: 16px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 900;
}

.history-header h2 {
  margin: 5px 0 0;
  color: var(--ink);
  font-size: 28px;
  line-height: 1.2;
}

.refresh-button,
.history-card__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 10px 13px;
  background: var(--surface);
  color: var(--ink);
  font-weight: 850;
  cursor: pointer;
}

.refresh-button:hover,
.history-card__button:hover:not(:disabled) {
  border-color: var(--teal);
  color: var(--teal);
}

.history-state {
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
  color: var(--muted);
  text-align: center;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
  gap: 16px;
}

.history-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.history-card__top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.history-card__top div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.history-card__top strong {
  overflow: hidden;
  color: var(--ink);
  font-size: 21px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-card__top span {
  color: var(--muted);
  font-size: 12px;
}

.history-card__summary {
  display: -webkit-box;
  min-height: 72px;
  margin: 0;
  overflow: hidden;
  color: var(--ink-soft);
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.history-card__trip-id {
  overflow-wrap: anywhere;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--surface-muted);
  color: var(--muted);
  font-size: 12px;
}

.history-card__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}

.history-card__button--primary {
  border-color: var(--teal);
  background: var(--teal);
  color: #ffffff;
}

.history-card__button--primary:hover:not(:disabled) {
  color: #ffffff;
}

.history-card__button--danger {
  border-color: #f4c7bd;
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.history-card__button:disabled {
  opacity: 0.62;
  cursor: wait;
}

@media (max-width: 680px) {
  .history-header {
    align-items: stretch;
    flex-direction: column;
  }

  .refresh-button {
    width: 100%;
  }

  .history-card__actions {
    grid-template-columns: 1fr;
  }
}
</style>
