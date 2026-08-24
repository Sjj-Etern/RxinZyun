<script setup>
import { ref, computed } from 'vue'

// ============================================================================
// 车标位置（手动）
// 当前手动设定 xy 值控制车标位置；后续接入实时坐标时，
// 只需启用下方 fetchPose() 并把 pose 改为它的返回值，其余代码无需改动。
// ============================================================================
const POSE = { x: 1500, y: 1200 } // ← 手动改这里（默认地图正中）

// 坐标映射配置（来自 .env，确认实际坐标系后在 .env 统一修改）
const X_MIN = Number(import.meta.env.VITE_MAP_X_MIN ?? 0)
const X_MAX = Number(import.meta.env.VITE_MAP_X_MAX ?? 3000)
const Y_MIN = Number(import.meta.env.VITE_MAP_Y_MIN ?? 0)
const Y_MAX = Number(import.meta.env.VITE_MAP_Y_MAX ?? 2400)
const Y_AXIS = import.meta.env.VITE_MAP_Y_AXIS || 'up' // up=原点左下/y向上(翻转)；down=原点左上/y向下

// 当前车位（后续接实时坐标：把这里换成 fetchPose() 的返回）
const pose = ref({ ...POSE })

// 预留：后续接后端实时位姿时启用（取消注释并在 pose 处调用）
// async function fetchPose() {
//   const base = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'
//   const api = import.meta.env.VITE_POSE_API || '/api/v1/robot/pose'
//   const res = await fetch(`${base}${api}`)
//   if (res.ok) return await res.json() // 期望 { x, y }
//   return pose.value
// }

// xy → 地图百分比位置（车标用 HTML 覆盖层，不被 SVG 拉伸影响，始终为正圆）
const dotStyle = computed(() => {
  const { x, y } = pose.value
  const leftPct = ((x - X_MIN) / (X_MAX - X_MIN)) * 100
  const yPct = ((y - Y_MIN) / (Y_MAX - Y_MIN)) * 100
  const topPct = Y_AXIS === 'up' ? 100 - yPct : yPct
  return { left: `${leftPct}%`, top: `${topPct}%` }
})
</script>

<template>
  <div class="cad-scene">
    <!-- CAD 平面图（仅形状，拉伸铺满） -->
    <svg class="cad-svg" viewBox="0 0 3000 2400" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <!-- 房间外轮廓（贴满四边） -->
      <rect x="0" y="0" width="3000" height="2400" class="shape" />
      <!-- 左下隔间 700×400 -->
      <rect x="0" y="2000" width="700" height="400" class="shape" />
      <!-- 左内墙（竖向）位于 950mm，高 1800mm -->
      <line x1="950" y1="600" x2="950" y2="2400" class="shape" />
      <!-- 中间隔墙 140×1800 -->
      <rect x="1670" y="0" width="140" height="1800" class="shape" />
      <!-- 右下隔间 400×700 -->
      <rect x="2600" y="1700" width="400" height="700" class="shape" />
      <!-- 右上上隔间 260×400 -->
      <rect x="2740" y="0" width="260" height="400" class="shape" />
      <!-- 右上下隔间 400×400 -->
      <rect x="2600" y="400" width="400" height="400" class="shape" />
    </svg>

    <!-- 车标（固定圆点，不旋转；HTML 覆盖层，不受地图拉伸影响） -->
    <div class="car-dot" :style="dotStyle">
      <span class="car-dot-core"></span>
    </div>
  </div>
</template>

<style scoped>
.cad-scene {
  position: relative;
  width: 100%;
  height: 100%;
}

.cad-svg {
  display: block;
  width: 100%;
  height: 100%;
}

/* 所有形状：仅描边、无填充，保持屏幕级清晰并带青色辉光呼应主题 */
.shape {
  fill: none;
  stroke: #ffffff;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  filter: drop-shadow(0 0 3px rgba(0, 240, 255, 0.25));
}

/* 车标：绝对定位，translate 居中于 xy 计算出的百分比点 */
.car-dot {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 16px;
  height: 16px;
  pointer-events: none;
  z-index: 5;
}
.car-dot-core {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: #00f0ff;
  box-shadow: 0 0 8px #00f0ff, 0 0 18px rgba(0, 240, 255, 0.6);
  animation: car-pulse 1.6s ease-in-out infinite;
}
/* 涟漪外环，强化"实时"感 */
.car-dot::before {
  content: '';
  position: absolute;
  top: -6px;
  left: -6px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(0, 240, 255, 0.5);
  animation: car-ripple 1.6s ease-out infinite;
}
@keyframes car-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.82); opacity: 0.8; }
}
@keyframes car-ripple {
  0% { transform: scale(0.7); opacity: 0.8; }
  100% { transform: scale(1.9); opacity: 0; }
}
</style>
