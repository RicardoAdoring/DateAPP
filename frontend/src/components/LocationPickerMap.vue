<script setup lang="ts">
import {
  AimOutlined,
  EnvironmentOutlined,
  LoadingOutlined,
  PushpinOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { reverseGeocodeLocation, searchLocations } from "../services/api";
import type { LocationCandidate, SelectedLocation } from "../types";

const props = defineProps<{
  modelValue: SelectedLocation | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: SelectedLocation | null];
}>();

declare global {
  interface Window {
    AMap?: any;
    _AMapSecurityConfig?: {
      securityJsCode?: string;
    };
  }
}

const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = ref<any>(null);
const marker = ref<any>(null);
const loadError = ref("");
const keyword = ref("上海外滩");
const city = ref("");
const candidates = ref<LocationCandidate[]>([]);
const searching = ref(false);
const resolving = ref(false);
const hasSearched = ref(false);

const amapKey = import.meta.env.VITE_AMAP_JS_KEY;
const amapSecurityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE;

const selectedTitle = computed(() => {
  const selected = props.modelValue;
  if (!selected) {
    return "尚未选择地点";
  }
  return selected.name || selected.address || "已选择地图点位";
});

const selectedSubtitle = computed(() => {
  const selected = props.modelValue;
  if (!selected) {
    return "等待中心点";
  }
  return selected.address || `${selected.longitude.toFixed(6)}, ${selected.latitude.toFixed(6)}`;
});

function toSelectedLocation(candidate: LocationCandidate): SelectedLocation | null {
  if (candidate.latitude == null || candidate.longitude == null) {
    return null;
  }
  return {
    name: candidate.name,
    address: candidate.address,
    province: candidate.province,
    city: candidate.city,
    district: candidate.district,
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    poi_id: candidate.poi_id,
  };
}

function formatDistance(distance?: number | null): string {
  if (distance == null) {
    return "";
  }
  return distance >= 1000 ? `${(distance / 1000).toFixed(1)} km` : `${distance.toFixed(0)} m`;
}

function ensureMapScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (amapSecurityJsCode) {
      window._AMapSecurityConfig = {
        securityJsCode: amapSecurityJsCode,
      };
    }

    if (window.AMap) {
      resolve();
      return;
    }

    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[data-amap-loader="true"]'
    );
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("AMap load failed")), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(amapKey)}`;
    script.async = true;
    script.defer = true;
    script.dataset.amapLoader = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("AMap load failed"));
    document.head.appendChild(script);
  });
}

function clearMarker() {
  if (mapInstance.value && marker.value) {
    mapInstance.value.remove(marker.value);
  }
  marker.value = null;
}

function placeMarker(location: SelectedLocation, shouldCenter = true) {
  if (!window.AMap || !mapInstance.value) {
    return;
  }
  clearMarker();
  const position: [number, number] = [location.longitude, location.latitude];
  marker.value = new window.AMap.Marker({
    position,
    title: location.name || location.address || "selected",
    offset: new window.AMap.Pixel(-17, -38),
    content: `
      <div class="date-anchor-marker">
        <span></span>
      </div>
    `,
  });
  mapInstance.value.add(marker.value);
  if (shouldCenter) {
    mapInstance.value.setZoomAndCenter(15, position);
  }
}

async function initMap() {
  if (!amapKey) {
    loadError.value = "未配置前端高德 JavaScript Key，仍可使用文本搜索。";
    return;
  }
  if (!mapContainer.value) {
    return;
  }
  try {
    await ensureMapScript();
    if (!window.AMap) {
      loadError.value = "高德地图对象初始化失败。";
      return;
    }
    mapInstance.value = new window.AMap.Map(mapContainer.value, {
      zoom: 12,
      resizeEnable: true,
      viewMode: "2D",
      mapStyle: "amap://styles/macaron",
      center: props.modelValue
        ? [props.modelValue.longitude, props.modelValue.latitude]
        : [121.4737, 31.2304],
    });
    mapInstance.value.on("click", (event: any) => {
      const lnglat = event.lnglat;
      if (!lnglat) {
        return;
      }
      void selectMapPoint(lnglat.getLng(), lnglat.getLat());
    });
    if (props.modelValue) {
      placeMarker(props.modelValue, false);
    }
  } catch (error) {
    console.error(error);
    loadError.value = "地图加载失败，请检查高德前端 Key 或网络环境。";
  }
}

async function handleSearch() {
  const value = keyword.value.trim();
  if (!value) {
    message.warning("请输入地点或地址");
    return;
  }
  searching.value = true;
  hasSearched.value = true;
  try {
    candidates.value = await searchLocations(value, city.value.trim() || undefined, 8);
    if (!candidates.value.length) {
      message.warning("没有找到匹配地点，可以换个关键词试试。");
    }
  } catch (error) {
    console.error(error);
    message.error("地点搜索失败，请确认后端高德 MCP 服务可用。");
  } finally {
    searching.value = false;
  }
}

function selectCandidate(candidate: LocationCandidate) {
  const location = toSelectedLocation(candidate);
  if (!location) {
    message.warning("这个候选地点暂时没有坐标，请选择其他结果。");
    return;
  }
  emit("update:modelValue", location);
  placeMarker(location);
}

async function selectMapPoint(longitude: number, latitude: number) {
  resolving.value = true;
  try {
    const location = await reverseGeocodeLocation(longitude, latitude);
    emit("update:modelValue", location);
    placeMarker(location);
  } catch (error) {
    console.error(error);
    message.error("地图点位解析失败，请确认后端高德 MCP 服务可用。");
  } finally {
    resolving.value = false;
  }
}

onMounted(() => {
  void initMap();
});

watch(
  () => props.modelValue,
  (value) => {
    if (value && mapInstance.value) {
      placeMarker(value);
    }
  }
);

onBeforeUnmount(() => {
  clearMarker();
  if (mapInstance.value) {
    mapInstance.value.destroy();
    mapInstance.value = null;
  }
});
</script>

<template>
  <section class="location-picker">
    <div class="location-picker__tools">
      <div class="tool-heading">
        <div>
          <EnvironmentOutlined />
          <span>中心点</span>
        </div>
        <small>{{ candidates.length ? `${candidates.length} 个候选` : "地图选点" }}</small>
      </div>

      <div class="field-grid">
        <label class="field field--keyword">
          <span>地点或地址</span>
          <a-input
            v-model:value="keyword"
            placeholder="商圈、地标、餐厅或完整地址"
            @press-enter="handleSearch"
          />
        </label>
        <label class="field field--city">
          <span>城市</span>
          <a-input v-model:value="city" placeholder="可选" @press-enter="handleSearch" />
        </label>
        <a-button type="primary" :loading="searching" class="search-button" @click="handleSearch">
          <template #icon>
            <SearchOutlined />
          </template>
          搜索
        </a-button>
      </div>

      <div class="selected-strip" :class="{ 'selected-strip--active': modelValue }">
        <span class="pin-icon">
          <PushpinOutlined />
        </span>
        <div>
          <strong>{{ selectedTitle }}</strong>
          <span>{{ selectedSubtitle }}</span>
          <small v-if="modelValue">
            {{ modelValue.longitude.toFixed(6) }}, {{ modelValue.latitude.toFixed(6) }}
          </small>
        </div>
      </div>

      <div v-if="candidates.length" class="candidate-list">
        <button
          v-for="candidate in candidates"
          :key="candidate.poi_id || `${candidate.name}-${candidate.address}`"
          type="button"
          class="candidate-item"
          @click="selectCandidate(candidate)"
        >
          <span class="candidate-icon"><AimOutlined /></span>
          <span class="candidate-copy">
            <strong>{{ candidate.name }}</strong>
            <small>{{ candidate.address || candidate.type || "地址待补充" }}</small>
            <em v-if="candidate.district || candidate.distance_meters">
              {{ candidate.district || candidate.city }}
              <template v-if="formatDistance(candidate.distance_meters)">
                · {{ formatDistance(candidate.distance_meters) }}
              </template>
            </em>
          </span>
        </button>
      </div>

      <div v-else class="candidate-empty">
        <LoadingOutlined v-if="searching" />
        <SearchOutlined v-else />
        <span>{{ hasSearched ? "暂无候选地点" : "等待地点候选" }}</span>
      </div>
    </div>

    <div class="map-shell">
      <div v-if="loadError" class="map-state">{{ loadError }}</div>
      <div v-else ref="mapContainer" class="map-canvas"></div>
      <div v-if="resolving" class="map-badge">正在解析地址...</div>
    </div>
  </section>
</template>

<style scoped>
.location-picker {
  display: grid;
  grid-template-columns: minmax(330px, 390px) minmax(0, 1fr);
  min-height: 560px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.location-picker__tools {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 16px;
  border-right: 1px solid var(--line);
  background:
    linear-gradient(180deg, #fbfcfd 0%, var(--surface-muted) 100%);
}

.tool-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.tool-heading div {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 17px;
  font-weight: 900;
}

.tool-heading .anticon {
  color: var(--accent);
}

.tool-heading small {
  color: var(--muted);
  font-size: 12px;
}

.field-grid {
  display: grid;
  grid-template-columns: 1fr 110px;
  gap: 10px;
  align-items: end;
}

.field {
  display: grid;
  min-width: 0;
  gap: 6px;
  color: var(--ink-soft);
  font-size: 13px;
  font-weight: 800;
}

.search-button {
  grid-column: 1 / -1;
  height: 38px;
  border-radius: 6px;
  font-weight: 900;
}

.selected-strip {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}

.selected-strip--active {
  border-color: rgba(15, 118, 110, 0.35);
  background: linear-gradient(180deg, #ffffff 0%, var(--teal-soft) 100%);
}

.pin-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--accent);
}

.selected-strip div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.selected-strip strong,
.selected-strip span,
.selected-strip small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-strip strong {
  color: var(--ink);
}

.selected-strip span,
.selected-strip small {
  color: var(--muted);
  font-size: 12px;
}

.candidate-list {
  display: grid;
  gap: 8px;
  max-height: 300px;
  overflow: auto;
  padding-right: 2px;
}

.candidate-item {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  width: 100%;
  padding: 11px;
  border: 1px solid #e4eaf0;
  border-radius: var(--radius);
  background: var(--surface);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.candidate-item:hover {
  border-color: var(--accent);
  box-shadow: 0 10px 24px rgba(15, 32, 51, 0.08);
  transform: translateY(-1px);
}

.candidate-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: var(--surface-warm);
  color: var(--accent);
}

.candidate-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.candidate-copy strong,
.candidate-copy small,
.candidate-copy em {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.candidate-copy strong {
  color: var(--ink);
  font-weight: 900;
}

.candidate-copy small,
.candidate-copy em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.candidate-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 116px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  color: var(--muted);
  background: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}

.map-shell {
  position: relative;
  min-height: 560px;
  background: #e8eef3;
}

.map-canvas,
.map-state {
  width: 100%;
  height: 100%;
  min-height: 560px;
}

.map-state {
  display: grid;
  place-items: center;
  padding: 24px;
  color: var(--muted);
  text-align: center;
}

.map-badge {
  position: absolute;
  right: 16px;
  top: 16px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(16, 32, 51, 0.82);
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
}

:global(.date-anchor-marker) {
  position: relative;
  width: 34px;
  height: 34px;
  border: 3px solid #ffffff;
  border-radius: 50% 50% 50% 8px;
  background: var(--accent);
  box-shadow: 0 12px 24px rgba(16, 32, 51, 0.22);
  transform: rotate(-45deg);
}

:global(.date-anchor-marker span) {
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  background: #ffffff;
}

@media (max-width: 980px) {
  .location-picker {
    grid-template-columns: 1fr;
  }

  .location-picker__tools {
    border-right: none;
    border-bottom: 1px solid var(--line);
  }

  .candidate-list {
    max-height: 230px;
  }
}

@media (max-width: 560px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
