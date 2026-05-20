<script setup lang="ts">
import {
  CalendarOutlined,
  CompassOutlined,
  HistoryOutlined,
  OrderedListOutlined,
} from "@ant-design/icons-vue";
import { ref } from "vue";

import type { DatePlanRequestPayload, Itinerary, PlanStreamRun, TripEditPayload } from "./types";
import History from "./views/History.vue";
import Home from "./views/Home.vue";
import Result from "./views/Result.vue";
import StreamingPlanner from "./views/StreamingPlanner.vue";

const currentView = ref<"home" | "result" | "history" | "stream">("home");
const latestItinerary = ref<Itinerary | null>(null);
const streamRun = ref<PlanStreamRun | null>(null);
let streamRunId = 0;

function openTrip(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function updateCurrentItinerary(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function startGeneration(payload: DatePlanRequestPayload) {
  streamRun.value = {
    id: ++streamRunId,
    mode: "generate",
    payload,
    title: "正在生成约会路线",
    subtitle: `${payload.start_time}-${payload.end_time} · ${payload.travelers} 人 · ¥${payload.budget}`,
  };
  currentView.value = "stream";
}

function startEdit(payload: TripEditPayload) {
  streamRun.value = {
    id: ++streamRunId,
    mode: "edit",
    payload,
    title: "正在调整约会路线",
    subtitle: payload.user_instruction,
  };
  currentView.value = "stream";
}

function markStreamReady(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
}

function completeStream(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-lockup">
        <span class="brand-mark">
          <CompassOutlined />
        </span>
        <div>
          <span class="brand-kicker">DateApp</span>
          <strong>恋爱约会规划 Agent</strong>
        </div>
      </div>

      <nav class="topbar-tabs" aria-label="主导航">
        <button
          :class="['topbar-tab', { 'topbar-tab--active': currentView === 'home' }]"
          type="button"
          @click="currentView = 'home'"
        >
          <CalendarOutlined />
          <span>规划</span>
        </button>
        <button
          :class="[
            'topbar-tab',
            { 'topbar-tab--active': currentView === 'result' },
            { 'topbar-tab--disabled': !latestItinerary }
          ]"
          type="button"
          :disabled="!latestItinerary"
          @click="currentView = 'result'"
        >
          <OrderedListOutlined />
          <span>结果</span>
        </button>
        <button
          :class="['topbar-tab', { 'topbar-tab--active': currentView === 'history' }]"
          type="button"
          @click="currentView = 'history'"
        >
          <HistoryOutlined />
          <span>历史</span>
        </button>
      </nav>
    </header>

    <main class="page-content">
      <Home v-if="currentView === 'home'" @start-generation="startGeneration" />
      <Result
        v-else-if="currentView === 'result'"
        :itinerary="latestItinerary"
        @back-home="currentView = 'home'"
        @view-history="currentView = 'history'"
        @updated="updateCurrentItinerary"
        @start-edit="startEdit"
      />
      <StreamingPlanner
        v-else-if="currentView === 'stream'"
        :key="streamRun?.id"
        :run="streamRun"
        @ready="markStreamReady"
        @completed="completeStream"
        @back-home="currentView = 'home'"
        @back-result="currentView = latestItinerary ? 'result' : 'home'"
      />
      <History v-else :active="currentView === 'history'" @open-trip="openTrip" />
    </main>
  </div>
</template>

<style scoped>
:global(:root) {
  --bg: #f3f6f8;
  --bg-grid: rgba(22, 35, 54, 0.045);
  --surface: #ffffff;
  --surface-muted: #f8fafb;
  --surface-warm: #fff7f3;
  --ink: #102033;
  --ink-soft: #324456;
  --muted: #667789;
  --line: #dce3ea;
  --line-strong: #cbd5df;
  --accent: #dd5b4f;
  --accent-strong: #c9483f;
  --accent-soft: #fff0ec;
  --teal: #0f766e;
  --teal-soft: #e8f5f3;
  --amber: #b7791f;
  --radius: 8px;
  --shadow: 0 18px 42px rgba(15, 32, 51, 0.08);
}

:global(body) {
  margin: 0;
  min-width: 320px;
  background:
    linear-gradient(90deg, var(--bg-grid) 1px, transparent 1px),
    linear-gradient(180deg, #fbfcfd 0%, var(--bg) 42%, #edf2f5 100%);
  background-size: 32px 32px, auto;
  color: var(--ink);
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
}

:global(*) {
  box-sizing: border-box;
}

:global(button),
:global(input),
:global(textarea),
:global(select) {
  font: inherit;
}

:global(.ant-input),
:global(.ant-input-number),
:global(.ant-select-selector),
:global(.ant-input-affix-wrapper) {
  border-radius: 6px !important;
  border-color: var(--line-strong) !important;
}

:global(.ant-input:focus),
:global(.ant-input-focused),
:global(.ant-input-number-focused),
:global(.ant-select-focused .ant-select-selector),
:global(.ant-input-affix-wrapper-focused) {
  border-color: var(--teal) !important;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.14) !important;
}

:global(.ant-btn-primary:not(:disabled)) {
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: none;
}

:global(.ant-btn-primary:not(:disabled):hover) {
  border-color: var(--accent-strong) !important;
  background: var(--accent-strong) !important;
}

:global(.ant-checkbox-checked .ant-checkbox-inner) {
  border-color: var(--teal);
  background-color: var(--teal);
}

:global(.ant-checkbox-wrapper:hover .ant-checkbox-inner),
:global(.ant-checkbox:hover .ant-checkbox-inner) {
  border-color: var(--teal) !important;
}

:global(.ant-slider-track) {
  background-color: var(--teal) !important;
}

:global(.ant-slider-handle::after) {
  box-shadow: 0 0 0 2px var(--teal) !important;
}

.app-shell {
  min-height: 100vh;
  padding: 18px 22px 52px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
  max-width: 1360px;
  margin: 0 auto 18px;
  padding: 12px;
  border: 1px solid rgba(203, 213, 223, 0.82);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 10px 28px rgba(15, 32, 51, 0.06);
  backdrop-filter: blur(14px);
}

.brand-lockup {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 11px;
}

.brand-mark {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: var(--teal-soft);
  color: var(--teal);
  font-size: 19px;
}

.brand-lockup > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.brand-kicker {
  color: var(--accent);
  font-size: 12px;
  font-weight: 900;
}

.topbar strong {
  overflow: hidden;
  color: var(--ink);
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.topbar-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-width: 82px;
  border: none;
  border-radius: 6px;
  padding: 8px 12px;
  background: transparent;
  color: var(--muted);
  font-weight: 800;
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.topbar-tab:hover:not(:disabled) {
  background: #eef3f6;
  color: var(--ink);
}

.topbar-tab--active,
.topbar-tab--active:hover:not(:disabled) {
  background: var(--ink);
  color: #ffffff;
}

.topbar-tab--disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.page-content {
  max-width: 1360px;
  margin: 0 auto;
}

@media (max-width: 720px) {
  .app-shell {
    padding: 12px 10px 34px;
  }

  .topbar {
    align-items: stretch;
    flex-direction: column;
  }

  .topbar-tabs {
    width: 100%;
  }

  .topbar-tab {
    flex: 1;
    min-width: 0;
  }
}
</style>
