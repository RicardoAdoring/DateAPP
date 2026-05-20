<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

interface TripMapPoint {
  key: string;
  sequence?: number;
  dayIndex: number;
  date: string;
  theme: string;
  name: string;
  address: string;
  latitude: number | null | undefined;
  longitude: number | null | undefined;
  poiId?: string | null | undefined;
  imageUrl?: string | null;
  description: string;
  kind?: string;
  startTime?: string | null;
  endTime?: string | null;
}

const props = defineProps<{
  points: TripMapPoint[];
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
const markerList = ref<any[]>([]);
const routeLine = ref<any>(null);
const loadError = ref("");

const amapKey = import.meta.env.VITE_AMAP_JS_KEY;
const amapSecurityJsCode = import.meta.env.VITE_AMAP_SECURITY_JS_CODE;

const validPoints = computed(() =>
  props.points
    .filter((point) => point.longitude != null && point.latitude != null)
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0))
);

function escapeHtml(value: string | null | undefined): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function clearOverlays() {
  if (!mapInstance.value) {
    return;
  }
  markerList.value.forEach((marker) => mapInstance.value.remove(marker));
  markerList.value = [];
  if (routeLine.value) {
    mapInstance.value.remove(routeLine.value);
    routeLine.value = null;
  }
}

function renderMarkers() {
  if (!window.AMap || !mapInstance.value) {
    return;
  }
  clearOverlays();

  const bounds: [number, number][] = [];
  const routePath: [number, number][] = [];
  validPoints.value.forEach((point, index) => {
    const position: [number, number] = [point.longitude as number, point.latitude as number];
    const sequence = point.sequence || index + 1;
    bounds.push(position);
    routePath.push(position);

    const marker = new window.AMap.Marker({
      position,
      title: point.name,
      offset: new window.AMap.Pixel(-16, -34),
      content: `
        <div class="date-map-marker">
          <span>${sequence}</span>
        </div>
      `,
      zIndex: 120 + sequence,
    });

    const infoWindow = new window.AMap.InfoWindow({
      offset: new window.AMap.Pixel(0, -34),
      content: `
        <div style="max-width:260px;padding:4px 2px;line-height:1.65;font-family:Microsoft YaHei, sans-serif;">
          <strong>${escapeHtml(point.name)}</strong><br/>
          <span>${escapeHtml(point.startTime || "")}${point.endTime ? `-${escapeHtml(point.endTime)}` : ""}</span><br/>
          <span>${escapeHtml(point.address)}</span><br/>
          <small>${escapeHtml(point.description)}</small>
        </div>
      `,
    });

    marker.on("click", () => {
      infoWindow.open(mapInstance.value, position);
    });

    mapInstance.value.add(marker);
    markerList.value.push(marker);
  });

  if (routePath.length >= 2) {
    routeLine.value = new window.AMap.Polyline({
      path: routePath,
      strokeColor: "#0f766e",
      strokeWeight: 4,
      strokeOpacity: 0.85,
      strokeStyle: "dashed",
      strokeDasharray: [10, 7],
      lineJoin: "round",
      lineCap: "round",
      showDir: true,
      dirColor: "#e95454",
      dirSize: 8,
      zIndex: 60,
    });
    mapInstance.value.add(routeLine.value);
  }

  if (bounds.length === 1) {
    mapInstance.value.setZoomAndCenter(15, bounds[0]);
  } else if (bounds.length > 1) {
    mapInstance.value.setFitView(markerList.value, false, [64, 64, 64, 64]);
  }
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

async function initMap() {
  if (!amapKey) {
    loadError.value = "未配置前端高德 JavaScript Key。";
    return;
  }
  if (!mapContainer.value) {
    return;
  }
  try {
    loadError.value = "";
    await ensureMapScript();
    if (!window.AMap) {
      loadError.value = "高德地图初始化失败。";
      return;
    }
    mapInstance.value = new window.AMap.Map(mapContainer.value, {
      zoom: 12,
      resizeEnable: true,
      viewMode: "2D",
      mapStyle: "amap://styles/macaron",
    });
    renderMarkers();
  } catch (error) {
    console.error(error);
    loadError.value = "地图加载失败，请检查前端高德 Key 或网络环境。";
  }
}

onMounted(() => {
  void initMap();
});

watch(validPoints, () => {
  if (mapInstance.value) {
    renderMarkers();
  }
});

onBeforeUnmount(() => {
  clearOverlays();
  if (mapInstance.value) {
    mapInstance.value.destroy();
    mapInstance.value = null;
  }
});
</script>

<template>
  <div class="trip-map">
    <div v-if="loadError" class="trip-map__placeholder">
      <strong>地图暂未启用</strong>
      <span>{{ loadError }}</span>
    </div>
    <div v-else-if="validPoints.length === 0" class="trip-map__placeholder">
      <strong>暂无可展示点位</strong>
      <span>当前路线还没有带经纬度的地点。</span>
    </div>
    <div v-else ref="mapContainer" class="trip-map__canvas"></div>
  </div>
</template>

<style scoped>
.trip-map {
  min-height: 406px;
  height: 100%;
}

.trip-map__canvas,
.trip-map__placeholder {
  width: 100%;
  height: 100%;
  min-height: 406px;
  border-radius: 8px;
}

.trip-map__placeholder {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  padding: 20px;
  background: #eef2f6;
  color: #475569;
  text-align: center;
}

.trip-map__placeholder span {
  color: #64748b;
  line-height: 1.6;
}

:global(.date-map-marker) {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 3px solid #ffffff;
  border-radius: 50%;
  background: #e95454;
  color: #ffffff;
  font-family: "Microsoft YaHei", sans-serif;
  font-size: 14px;
  font-weight: 900;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.22);
}
</style>
