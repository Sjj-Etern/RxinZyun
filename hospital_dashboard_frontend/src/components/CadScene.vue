<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// ============================================================================
// 从 .env 读取配置（注意用 || 兜底，避免 # 颜色值被当注释变空）
// ============================================================================
const env = (key, fallback = '') => import.meta.env[key] || fallback
const num = (key, fallback = 0) => Number(env(key, fallback))
const backendUrl = env('VITE_BACKEND_URL', 'http://localhost:8080')
const poseApi = env('VITE_ROBOT_POSE_API', '/api/v1/robot/pose')
const pollMs = num('VITE_ROBOT_POSE_POLL_MS', 500)
const failThreshold = num('VITE_ROBOT_POSE_FAIL_THRESHOLD', 5)

// ============================================================================
// 动态加载 src/map/ 下所有 png 地图
// 以后新地图文件放入 src/map/ 并运行 sync_maps.py 后，无需改此 import
// ============================================================================
const mapModules = import.meta.glob('../map/*.png', { eager: true, query: '?url', import: 'default' })

function getMapUrl(mapName) {
  if (!mapName) return ''
  return mapModules[`../map/${mapName}.png`] || ''
}

// ============================================================================
// 地图放大倍数（控制 viewBox 聚焦范围）
//   SCALE=1   → 显示全图
//   SCALE=N>1 → viewBox 缩小到全图 1/N，聚焦路径中心区域（视觉放大 N 倍）
// 注意：放大通过裁剪 viewBox 实现，不是放大 image 尺寸
//       （image 与 viewBox 同比例放大等于没放大）
// ============================================================================
const MAP_SCALE = Math.max(1, num('VITE_MAP_SCALE', 1))

// ============================================================================
// ROS 坐标换算（基于 yaml 参数，y 翻转，不乘 SCALE）
//   px = (x - ORIGIN_X) / RESOLUTION
//   py = H - (y - ORIGIN_Y) / RESOLUTION
// 坐标系由 map.yaml 自动对齐，无需手动标定
// ============================================================================
function makeRosProjector(mapName) {
  const prefix = `VITE_MAP_${mapName.toUpperCase()}`
  const H = num(`${prefix}_H`)
  const resolution = num(`${prefix}_RESOLUTION`)
  const originX = num(`${prefix}_ORIGIN_X`)
  const originY = num(`${prefix}_ORIGIN_Y`)
  return (x, y) => ({
    px: (x - originX) / resolution,
    py: H - (y - originY) / resolution,
  })
}

// 读取地图原始尺寸（不乘 SCALE）
function getMapSize(mapName) {
  const prefix = `VITE_MAP_${mapName.toUpperCase()}`
  return { w: num(`${prefix}_W`), h: num(`${prefix}_H`) }
}

// ============================================================================
// 计算聚焦 viewBox：SCALE=1 全图；SCALE>1 聚焦路径中心，宽高=全图/SCALE
// ============================================================================
function computeFocus(points, mapSize, scale) {
  if (scale <= 1) {
    return { x: 0, y: 0, w: mapSize.w, h: mapSize.h }
  }
  const xs = points.map(p => p.px)
  const ys = points.map(p => p.py)
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2
  const vbW = mapSize.w / scale
  const vbH = mapSize.h / scale
  return { x: cx - vbW / 2, y: cy - vbH / 2, w: vbW, h: vbH }
}

// 车标/轨迹尺寸补偿：放大 N 倍后视觉放大 N 倍，除以 √N 保持适中
const SCALE_COMPENSATE = Math.sqrt(MAP_SCALE)
const STROKE_W = 6 / SCALE_COMPENSATE
const CAR_R = 12 / SCALE_COMPENSATE
const RIPPLE_R = 22 / SCALE_COMPENSATE
const DASH = `${14 / SCALE_COMPENSATE} ${10 / SCALE_COMPENSATE}`

// 点列表 → SVG path d 字符串：M x,y L x,y ... Z
function toPathD(points) {
  if (!points.length) return ''
  const [first, ...rest] = points
  const d = [`M ${first.px.toFixed(1)},${first.py.toFixed(1)}`]
  rest.forEach(p => d.push(`L ${p.px.toFixed(1)},${p.py.toFixed(1)}`))
  d.push('Z')
  return d.join(' ')
}

// ============================================================================
// 通用：构建一辆车的地图数据（车1/车2 共用，消除重复）
// 预设路径点用作：演示模式 animateMotion + 灰色半透明参考线
// ============================================================================
function useCarMap(carId) {
  const mapName = env(`VITE_${carId}_MAP`)
  const mapUrl = getMapUrl(mapName)
  const hasMap = !!(mapName && mapUrl)
  const mapSize = getMapSize(mapName)
  const projector = makeRosProjector(mapName)
  const color = env(`VITE_${carId}_COLOR`, '#00f0ff')
  const duration = num(`VITE_${carId}_DURATION`, 20)

  let points = []
  if (carId === 'CAR1') {
    // HOME → 药房 → 病房送药 → 返回途经点 → 回 HOME
    points = [
      projector(num('VITE_CAR1_HOME_X'), num('VITE_CAR1_HOME_Y')),
      projector(num('VITE_CAR1_PHARMACY_X'), num('VITE_CAR1_PHARMACY_Y')),
      projector(num('VITE_CAR1_DROP_X'), num('VITE_CAR1_DROP_Y')),
      projector(num('VITE_CAR1_RETURN_X'), num('VITE_CAR1_RETURN_Y')),
      projector(num('VITE_CAR1_HOME_X'), num('VITE_CAR1_HOME_Y')),
    ]
  } else {
    // HOME → 电梯等待 → 电梯内 → 护士站 → 回 HOME
    points = [
      projector(num('VITE_CAR2_HOME_X'), num('VITE_CAR2_HOME_Y')),
      projector(num('VITE_CAR2_LIFT_WAIT_X'), num('VITE_CAR2_LIFT_WAIT_Y')),
      projector(num('VITE_CAR2_LIFT_INSIDE_X'), num('VITE_CAR2_LIFT_INSIDE_Y')),
      projector(num('VITE_CAR2_NURSE_X'), num('VITE_CAR2_NURSE_Y')),
      projector(num('VITE_CAR2_HOME_X'), num('VITE_CAR2_HOME_Y')),
    ]
  }

  const pathD = toPathD(points)
  const start = points[0]
  const focus = computeFocus(points, mapSize, MAP_SCALE)
  return { mapName, mapUrl, hasMap, mapSize, color, duration, points, pathD, start, focus, projector }
}

const car1 = useCarMap('CAR1')
const car2 = useCarMap('CAR2')

// ============================================================================
// 实时坐标状态（轮询后端 /api/v1/robot/pose）
// ============================================================================
const car1Pose = ref({ x: null, y: null, ts: null, listener_state: 'stopped' })
const car2Pose = ref({ x: null, y: null, ts: null, listener_state: 'stopped' })

// 模式：realtime（API 可用） / demo（API 不可用，降级演示）
// 每辆车显示实时车标还是灰色等待，由模板按各自坐标有无判断
const mode = ref('demo')
let failCount = 0
let pollTimer = null

async function pollPose() {
  try {
    const res = await fetch(`${backendUrl}${poseApi}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    failCount = 0
    if (data.car1) car1Pose.value = data.car1
    if (data.car2) car2Pose.value = data.car2
    // 控制台打印数据来源：real = 真实小车轨迹，mock = 后端模拟数据
    console.log(
      `[CadScene] pose 来源 → 车1: ${data.car1?.source ?? 'unknown'} (x=${data.car1?.x}, y=${data.car1?.y}) | ` +
      `车2: ${data.car2?.source ?? 'unknown'} (x=${data.car2?.x}, y=${data.car2?.y})`
    )
    // API 通则实时模式（每辆车具体显示由坐标有无决定）
    mode.value = 'realtime'
  } catch (e) {
    failCount++
    if (failCount >= failThreshold) {
      mode.value = 'demo'
      console.warn(`[CadScene] pose API 连续失败 ${failCount} 次，切到本地演示动画`)
    }
  }
}

onMounted(() => {
  pollPose()
  pollTimer = setInterval(pollPose, pollMs)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// ============================================================================
// 实时车标位置（ROS 坐标 → jpg 像素，复用 projector）
// ============================================================================
const car1Marker = computed(() => {
  if (car1Pose.value.x == null) return null
  return car1.projector(car1Pose.value.x, car1Pose.value.y)
})
const car2Marker = computed(() => {
  if (car2Pose.value.x == null) return null
  return car2.projector(car2Pose.value.x, car2Pose.value.y)
})

// 状态条：无论真实数据还是模拟数据，只要在轮询即显示"实时"
const modeText = computed(() => '● 实时')
const modeClass = computed(() => 'tag-realtime')
</script>

<template>
  <div class="cad-scene">
    <!-- 顶部状态条 -->
    <div class="status-bar">
      <span class="status-tag" :class="modeClass">{{ modeText }}</span>
    </div>

    <!-- 双车地图横向排列 -->
    <div class="map-row">
      <!-- ============ 左侧：车1 地图 ============ -->
      <div class="map-pane">
        <div class="pane-header">
          <span class="pane-title">车1 实时地图</span>
          <span class="pane-tag" :class="car1.hasMap ? 'tag-ok' : 'tag-wait'">
            {{ car1.hasMap ? `已同步 · ${car1.mapName}` : '待同步' }}
          </span>
        </div>
        <div class="pane-body">
          <svg
            v-if="car1.hasMap && car1.mapSize.w"
            class="map-svg"
            :viewBox="`${car1.focus.x} ${car1.focus.y} ${car1.focus.w} ${car1.focus.h}`"
            preserveAspectRatio="xMidYMid meet"
            xmlns="http://www.w3.org/2000/svg"
          >
            <!-- 地图底图（ROS 栅格地图，原始尺寸，viewBox 裁剪聚焦区域）-->
            <image :href="car1.mapUrl" x="0" y="0" :width="car1.mapSize.w" :height="car1.mapSize.h" />

            <!-- 灰色半透明参考路径（预设轨迹，所有模式都显示）-->
            <path :d="car1.pathD" fill="none" stroke="#4a6080"
                  :stroke-width="STROKE_W" :stroke-dasharray="DASH" opacity="0.5" />

            <!-- 实时模式（API 可用）：有坐标显示实时车标，无坐标显示灰色等待 -->
            <template v-if="mode === 'realtime'">
              <template v-if="car1Marker">
                <circle :r="RIPPLE_R" :cx="car1Marker.px" :cy="car1Marker.py" :fill="car1.color" opacity="0.25" />
                <circle :r="CAR_R" :cx="car1Marker.px" :cy="car1Marker.py" :fill="car1.color" />
              </template>
              <template v-else>
                <circle :r="RIPPLE_R" :cx="car1.start.px" :cy="car1.start.py" fill="#666" opacity="0.2" />
                <circle :r="CAR_R" :cx="car1.start.px" :cy="car1.start.py" fill="#666" />
              </template>
            </template>
            <!-- 演示模式（API 不可用）：animateMotion 沿静态路径动画 -->
            <template v-else>
              <circle :r="RIPPLE_R" :cx="car1.start.px" :cy="car1.start.py" :fill="car1.color" opacity="0.25">
                <animateMotion :dur="`${car1.duration}s`" repeatCount="1" fill="freeze" :path="car1.pathD" />
              </circle>
              <circle :r="CAR_R" :cx="car1.start.px" :cy="car1.start.py" :fill="car1.color">
                <animateMotion :dur="`${car1.duration}s`" repeatCount="1" fill="freeze" :path="car1.pathD" />
              </circle>
            </template>
          </svg>
          <div v-else class="map-placeholder">
            <div class="placeholder-text">车1 地图未同步</div>
            <div class="placeholder-hint">请运行 <code>python scripts/sync_maps.py</code></div>
          </div>
        </div>
      </div>

      <!-- ============ 右侧：车2 地图 ============ -->
      <div class="map-pane">
        <div class="pane-header">
          <span class="pane-title">车2 实时地图</span>
          <span class="pane-tag" :class="car2.hasMap ? 'tag-ok' : 'tag-wait'">
            {{ car2.hasMap ? `已同步 · ${car2.mapName}` : '待同步' }}
          </span>
        </div>
        <div class="pane-body">
          <svg
            v-if="car2.hasMap && car2.mapSize.w"
            class="map-svg"
            :viewBox="`${car2.focus.x} ${car2.focus.y} ${car2.focus.w} ${car2.focus.h}`"
            preserveAspectRatio="xMidYMid meet"
            xmlns="http://www.w3.org/2000/svg"
          >
            <image :href="car2.mapUrl" x="0" y="0" :width="car2.mapSize.w" :height="car2.mapSize.h" />

            <path :d="car2.pathD" fill="none" stroke="#4a6080"
                  :stroke-width="STROKE_W" :stroke-dasharray="DASH" opacity="0.5" />

            <template v-if="mode === 'realtime'">
              <template v-if="car2Marker">
                <circle :r="RIPPLE_R" :cx="car2Marker.px" :cy="car2Marker.py" :fill="car2.color" opacity="0.25" />
                <circle :r="CAR_R" :cx="car2Marker.px" :cy="car2Marker.py" :fill="car2.color" />
              </template>
              <template v-else>
                <circle :r="RIPPLE_R" :cx="car2.start.px" :cy="car2.start.py" fill="#666" opacity="0.2" />
                <circle :r="CAR_R" :cx="car2.start.px" :cy="car2.start.py" fill="#666" />
              </template>
            </template>
            <template v-else>
              <circle :r="RIPPLE_R" :cx="car2.start.px" :cy="car2.start.py" :fill="car2.color" opacity="0.25">
                <animateMotion :dur="`${car2.duration}s`" repeatCount="1" fill="freeze" :path="car2.pathD" />
              </circle>
              <circle :r="CAR_R" :cx="car2.start.px" :cy="car2.start.py" :fill="car2.color">
                <animateMotion :dur="`${car2.duration}s`" repeatCount="1" fill="freeze" :path="car2.pathD" />
              </circle>
            </template>
          </svg>
          <div v-else class="map-placeholder">
            <div class="placeholder-text">车2 地图未同步</div>
            <div class="placeholder-hint">请运行 <code>python scripts/sync_maps.py</code></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cad-scene {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #020712;
}
.status-bar {
  flex: 0 0 auto;
  padding: 4px 12px;
  background: #0a1525;
  border-bottom: 1px solid #1a3050;
  display: flex;
  justify-content: flex-end;
}
.status-tag {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 8px;
  font-weight: 600;
}
.tag-realtime {
  color: #6affb0;
  background: rgba(106, 255, 176, 0.1);
  border: 1px solid rgba(106, 255, 176, 0.3);
}
.tag-waiting {
  color: #ffaa6a;
  background: rgba(255, 170, 106, 0.1);
  border: 1px solid rgba(255, 170, 106, 0.3);
}
.tag-demo {
  color: #ff6a6a;
  background: rgba(255, 106, 106, 0.1);
  border: 1px solid rgba(255, 106, 106, 0.3);
}

.map-row {
  flex: 1;
  display: flex;
  gap: 4px;
  min-height: 0;
}
.map-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #0a1525;
  border: 1px solid #1a3050;
  overflow: hidden;
  min-width: 0;
}
.pane-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: linear-gradient(90deg, #0f2540, #0a1525);
  border-bottom: 1px solid #1a3050;
}
.pane-title {
  color: #5ad8ff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 1px;
}
.pane-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}
.tag-ok {
  color: #6affb0;
  background: rgba(106, 255, 176, 0.1);
  border: 1px solid rgba(106, 255, 176, 0.3);
}
.tag-wait {
  color: #ffaa6a;
  background: rgba(255, 170, 106, 0.1);
  border: 1px solid rgba(255, 170, 106, 0.3);
}
.pane-body {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.map-svg {
  display: block;
  width: 100%;
  height: 100%;
}
.map-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #4a6080;
  text-align: center;
  padding: 20px;
}
.placeholder-text {
  font-size: 18px;
  color: #6a8090;
  margin-bottom: 8px;
}
.placeholder-hint {
  font-size: 13px;
  color: #3a5070;
  line-height: 1.6;
}
.placeholder-hint code {
  background: #1a2540;
  padding: 2px 6px;
  border-radius: 3px;
  color: #5ad8ff;
}
</style>
