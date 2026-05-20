<script setup lang="ts">
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CompassOutlined,
  LoadingOutlined,
  NodeIndexOutlined,
  OrderedListOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons-vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { streamDatePlan, streamTripEdit } from "../services/api";
import type {
  DatePlanRequestPayload,
  Itinerary,
  PlanningStreamEvent,
  PlanStreamRun,
  TripEditPayload,
} from "../types";

const props = defineProps<{
  run: PlanStreamRun | null;
}>();

const emit = defineEmits<{
  ready: [itinerary: Itinerary];
  completed: [itinerary: Itinerary];
  backHome: [];
  backResult: [];
}>();

const events = ref<PlanningStreamEvent[]>([]);
const planItems = ref<PlanningStreamEvent[]>([]);
const routeItems = ref<PlanningStreamEvent[]>([]);
const finalItinerary = ref<Itinerary | null>(null);
const running = ref(false);
const errorMessage = ref("");

let controller: AbortController | null = null;

const statusText = computed(() => {
  if (errorMessage.value) {
    return "执行失败";
  }
  if (finalItinerary.value) {
    return "已完成";
  }
  return running.value ? "生成中" : "等待开始";
});

const eventIconMap = {
  stage: CompassOutlined,
  thought: ThunderboltOutlined,
  plan_item: OrderedListOutlined,
  route: NodeIndexOutlined,
  complete: CheckCircleOutlined,
  error: ClockCircleOutlined,
};

function eventIcon(type: PlanningStreamEvent["type"]) {
  return eventIconMap[type] || ClockCircleOutlined;
}

function eventClass(type: PlanningStreamEvent["type"]) {
  return `stream-event stream-event--${type}`;
}

function eventDataText(event: PlanningStreamEvent, key: string): string {
  const value = event.data?.[key];
  return value == null ? "" : String(value);
}

function eventCost(event: PlanningStreamEvent): string {
  const value = event.data?.estimated_cost;
  const numeric = Number(value || 0);
  return `¥${numeric.toFixed(0)}`;
}

function handleEvent(event: PlanningStreamEvent) {
  events.value.push(event);
  if (event.type === "plan_item") {
    planItems.value.push(event);
  }
  if (event.type === "route") {
    routeItems.value.push(event);
  }
  if (event.type === "complete" && event.itinerary) {
    finalItinerary.value = event.itinerary;
  }
  if (event.type === "error") {
    errorMessage.value = event.content || event.title || "执行失败";
  }
}

async function startStream(run: PlanStreamRun) {
  controller?.abort();
  controller = new AbortController();
  events.value = [];
  planItems.value = [];
  routeItems.value = [];
  finalItinerary.value = null;
  errorMessage.value = "";
  running.value = true;

  try {
    const itinerary =
      run.mode === "generate"
        ? await streamDatePlan(
            run.payload as DatePlanRequestPayload,
            handleEvent,
            controller.signal
          )
        : await streamTripEdit(
            run.payload as TripEditPayload,
            handleEvent,
            controller.signal
          );
    finalItinerary.value = itinerary;
    emit("ready", itinerary);
  } catch (error) {
    if (controller.signal.aborted) {
      return;
    }
    const message = error instanceof Error ? error.message : "流式任务失败";
    errorMessage.value = message;
    if (!events.value.some((event) => event.type === "error")) {
      events.value.push({
        type: "error",
        title: "执行失败",
        content: message,
      });
    }
  } finally {
    running.value = false;
  }
}

watch(
  () => props.run?.id,
  () => {
    if (props.run) {
      void startStream(props.run);
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  controller?.abort();
});
</script>

<template>
  <section v-if="run" class="stream-page">
    <div class="stream-header">
      <div>
        <span class="eyebrow">{{ run.mode === "generate" ? "Generate" : "Refine" }}</span>
        <h1>{{ run.title }}</h1>
        <p>{{ run.subtitle }}</p>
      </div>
      <div class="status-card" :class="{ 'status-card--done': finalItinerary, 'status-card--error': errorMessage }">
        <LoadingOutlined v-if="running" />
        <CheckCircleOutlined v-else-if="finalItinerary" />
        <ClockCircleOutlined v-else />
        <span>{{ statusText }}</span>
      </div>
    </div>

    <div class="stream-layout">
      <section class="stream-console">
        <div class="panel-title">
          <div>
            <ThunderboltOutlined />
            <span>Agent 思考</span>
          </div>
          <small>{{ events.length }} 条事件</small>
        </div>

        <div class="event-list">
          <article
            v-for="(event, index) in events"
            :key="`${event.type}-${index}-${event.title}`"
            :class="eventClass(event.type)"
          >
            <span class="event-icon">
              <component :is="eventIcon(event.type)" />
            </span>
            <div>
              <strong>{{ event.title || "处理中" }}</strong>
              <p>{{ event.content }}</p>
            </div>
          </article>
        </div>
      </section>

      <section class="stream-preview">
        <div class="panel-title">
          <div>
            <OrderedListOutlined />
            <span>安排输出</span>
          </div>
          <small>{{ planItems.length }} 个节点</small>
        </div>

        <div v-if="planItems.length" class="plan-list">
          <article
            v-for="(item, index) in planItems"
            :key="`${item.title}-${index}`"
            class="plan-item"
          >
            <div class="plan-index">{{ index + 1 }}</div>
            <div class="plan-copy">
              <span>{{ eventDataText(item, "start_time") }}-{{ eventDataText(item, "end_time") }}</span>
              <strong>{{ item.title }}</strong>
              <p>{{ item.content }}</p>
              <small>{{ eventDataText(item, "address") || "地址待补充" }}</small>
            </div>
            <em>{{ eventCost(item) }}</em>
          </article>
        </div>
        <div v-else class="stream-empty">
          <LoadingOutlined v-if="running" />
          <ClockCircleOutlined v-else />
          <span>等待安排输出</span>
        </div>

        <div v-if="routeItems.length" class="route-output">
          <div class="route-title">
            <NodeIndexOutlined />
            <span>路线段</span>
          </div>
          <div v-for="(item, index) in routeItems" :key="`${item.title}-${index}`">
            <strong>{{ item.title }}</strong>
            <span>{{ item.content }}</span>
          </div>
        </div>

        <div class="stream-actions">
          <button type="button" class="secondary-button" @click="run.mode === 'edit' ? $emit('backResult') : $emit('backHome')">
            <ArrowLeftOutlined />
            <span>{{ run.mode === "edit" ? "返回结果" : "返回规划" }}</span>
          </button>
          <button
            type="button"
            class="primary-button"
            :disabled="!finalItinerary"
            @click="finalItinerary && $emit('completed', finalItinerary)"
          >
            <CheckCircleOutlined />
            <span>查看完整结果</span>
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.stream-page {
  display: grid;
  gap: 16px;
}

.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 18px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.eyebrow {
  color: var(--accent);
  font-size: 13px;
  font-weight: 900;
}

.stream-header h1 {
  margin: 5px 0 6px;
  color: var(--ink);
  font-size: 30px;
  line-height: 1.18;
}

.stream-header p {
  margin: 0;
  color: var(--muted);
}

.status-card {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 116px;
  justify-content: center;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface-muted);
  color: var(--teal);
  font-weight: 900;
}

.status-card--done {
  background: var(--teal-soft);
}

.status-card--error {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.stream-layout {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
  gap: 16px;
}

.stream-console,
.stream-preview {
  display: grid;
  align-content: start;
  gap: 14px;
  min-height: 560px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.panel-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid #e8edf2;
}

.panel-title div,
.route-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 17px;
  font-weight: 900;
}

.panel-title .anticon,
.route-title .anticon {
  color: var(--teal);
}

.panel-title small {
  color: var(--muted);
}

.event-list {
  display: grid;
  gap: 9px;
  max-height: 660px;
  overflow: auto;
  padding-right: 2px;
}

.stream-event {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  padding: 11px;
  border: 1px solid #e5ebf0;
  border-radius: var(--radius);
  background: #fbfcfd;
}

.stream-event--thought {
  border-color: rgba(15, 118, 110, 0.24);
  background: var(--teal-soft);
}

.stream-event--plan_item {
  border-color: rgba(221, 91, 79, 0.24);
  background: var(--surface-warm);
}

.stream-event--complete {
  border-color: rgba(15, 118, 110, 0.4);
}

.stream-event--error {
  border-color: rgba(221, 91, 79, 0.45);
  background: var(--accent-soft);
}

.event-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
  background: var(--surface);
  color: var(--teal);
}

.stream-event strong {
  color: var(--ink);
}

.stream-event p {
  margin: 4px 0 0;
  color: var(--ink-soft);
  line-height: 1.65;
}

.plan-list {
  display: grid;
  gap: 10px;
}

.plan-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 60px;
  gap: 11px;
  padding: 12px;
  border: 1px solid #e5ebf0;
  border-radius: var(--radius);
  background: #fbfcfd;
}

.plan-index {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--teal-soft);
  color: var(--teal);
  font-weight: 900;
}

.plan-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.plan-copy span,
.plan-copy small {
  color: var(--muted);
  font-size: 12px;
}

.plan-copy strong {
  overflow: hidden;
  color: var(--ink);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-copy p {
  margin: 0;
  color: var(--ink-soft);
  line-height: 1.6;
}

.plan-item em {
  color: var(--ink);
  font-style: normal;
  font-weight: 900;
  text-align: right;
}

.stream-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 180px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  color: var(--muted);
}

.route-output {
  display: grid;
  gap: 8px;
  padding-top: 4px;
}

.route-output > div:not(.route-title) {
  display: grid;
  gap: 4px;
  padding: 10px 0;
  border-bottom: 1px solid #edf1f5;
}

.route-output strong {
  color: var(--ink);
}

.route-output span {
  color: var(--muted);
}

.stream-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 2px;
}

.primary-button,
.secondary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  padding: 10px 14px;
  background: var(--surface);
  color: var(--ink);
  font-weight: 900;
  cursor: pointer;
}

.primary-button {
  border-color: var(--accent);
  background: var(--accent);
  color: #ffffff;
}

.primary-button:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

@media (max-width: 980px) {
  .stream-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .stream-header,
  .stream-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .plan-item {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .plan-item em {
    grid-column: 2;
    text-align: left;
  }
}
</style>
