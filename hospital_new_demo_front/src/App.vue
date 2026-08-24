<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import CameraFeed from './components/CameraFeed.vue'
import PrescriptionProgress from './components/PrescriptionProgress.vue'
import PrescriptionMonitor from './components/PrescriptionMonitor.vue'
import layoutImg from './jpg/布局图.jpg'

// 从环境变量读取配置
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'

// 温湿度数据
const temperature = ref(24.5)
const humidity = ref(60)
let sensorTimer = null

// 获取传感器数据
const fetchSensorData = async () => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/sensors/temp-humidity`)
    if (response.ok) {
      const data = await response.json()
      temperature.value = data.temperature
      humidity.value = data.humidity
      console.log(`[传感器] 获取成功: 温度=${data.temperature}°C, 湿度=${data.humidity}%`)
    } else {
      console.warn('[传感器] API返回错误，使用备用数据')
    }
  } catch (error) {
    console.warn('[传感器] 获取失败，使用备用数据:', error.message)
  }
}

// 三个摄像头流地址
const camera1Url = `${BACKEND_URL}${import.meta.env.VITE_CAMERA1_PATH || '/api/v1/camera/opencv'}`
const camera2Url = `${BACKEND_URL}${import.meta.env.VITE_CAMERA2_PATH || '/api/v1/camera/robot'}`
const camera3Url = `${BACKEND_URL}${import.meta.env.VITE_CAMERA3_PATH || '/api/v1/camera/robot2'}`

// 三个摄像头备用视频
const camera1Fallback = import.meta.env.VITE_FALLBACK_VIDEO1 || '/videos/camera.mp4'
const camera2Fallback = import.meta.env.VITE_FALLBACK_VIDEO2 || '/videos/car_new.mp4'
const camera3Fallback = import.meta.env.VITE_FALLBACK_VIDEO3 || '/videos/car_old.mp4'

// 时钟
const currentTime = ref('')
const currentDate = ref('')
const currentWeek = ref('')
const updateTime = () => {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  currentTime.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  currentDate.value = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`
  currentWeek.value = ['星期日','星期一','星期二','星期三','星期四','星期五','星期六'][now.getDay()]
}

let timer = null
onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
  
  fetchSensorData()
  sensorTimer = setInterval(fetchSensorData, 5000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (sensorTimer) clearInterval(sensorTimer)
})
</script>

<template>
  <div class="app-root">
    <div class="bg-decorator"></div>

    <div class="dashboard">
    <!-- Header -->
    <header class="header">
      <div class="header-title-area">
        <div class="header-title">智能药房<span class="highlight">运维管理中心大屏</span></div>
        <div class="header-subtitle">Smart Pharmacy O&M Management Center</div>
      </div>
      
      <!-- 贯穿分割光轨 -->
      <div class="header-divider-wrapper">
        <svg class="header-divider" viewBox="0 0 1920 20" preserveAspectRatio="none">
          <path d="M 0,5 L 500,5 L 515,15 L 555,15 L 570,5 L 1920,5" fill="none" stroke="#00f0ff" stroke-width="2" />
          <circle cx="535" cy="15" r="3.5" fill="#00f0ff" />
        </svg>
      </div>

      <div class="header-right">
        <div class="clock-section">
          <div class="clock-time">{{ currentTime }}</div>
          <div class="clock-date">
            <span>{{ currentDate }}</span>
            <span style="margin-left: 6px;">{{ currentWeek }}</span>
          </div>
        </div>
        <div class="divider-vertical"></div>
        <div class="weather-section">
          <div class="weather-item">
            <svg class="header-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            <span class="value">{{ temperature }}℃</span>
          </div>
          <div class="weather-item">
            <svg class="header-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a8 8 0 008-8c0-4.418-8-12-8-12s-8 7.582-8 12a8 8 0 008 8z" />
            </svg>
            <span class="value">{{ humidity }}%</span>
          </div>
        </div>
      </div>
    </header>

    <!-- 左右分栏布局 2:1 -->
    <div class="content">
      <!-- 左栏 -->
      <div class="left-col">
        <div class="top-panels">
          <!-- 三个摄像头面板 -->
          <CameraFeed title="机器人导航 (POV 1)" :stream-url="camera2Url" :fallback-video="camera2Fallback" />
          <CameraFeed title="走廊监控" :stream-url="camera1Url" :fallback-video="camera1Fallback" />
          <CameraFeed title="机器人导航 (POV 2)" :stream-url="camera3Url" :fallback-video="camera3Fallback" />
        </div>

        <!-- 下方医院实时场景图 -->
        <div class="scene-wrapper">
          <div class="panel" style="height: 100%;">
            <div class="panel-header"><span class="title">医院实时场景图</span></div>
            <div class="panel-body">
              <div class="scene-container">
                <img :src="layoutImg" class="scene-image" alt="医院实时场景布局图" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏 - 药品追踪 + 处方队列 -->
      <div class="right-col">
        <PrescriptionProgress />
        <PrescriptionMonitor />
      </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-root {
  width: 100vw;
  height: 100vh;
  position: relative;
}

/* 经典大屏暗色网格背景 */
.bg-decorator {
  position: fixed; inset: 0; z-index: 0;
  background-image: 
    radial-gradient(circle at 50% 30%, #031630 0%, #010611 100%),
    linear-gradient(rgba(0, 240, 255, 0.012) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.012) 1px, transparent 1px);
  background-size: 100% 100%, 40px 40px, 40px 40px;
}

.dashboard {
  position: relative; z-index: 1;
  display: flex; flex-direction: column;
  height: 100vh; padding: var(--gap-outer); gap: 8px;
}

/* 头部 */
.header {
  flex-shrink: 0; height: 84px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0; background: transparent; 
  position: relative;
}

.header-title-area {
  display: flex; flex-direction: column; justify-content: center;
  transform: translateY(-5px); 
}
.header-title {
  font-size: 34px; font-weight: 900; letter-spacing: 4px;
  color: #ffffff;
  display: flex; gap: 8px;
  font-family: 'Noto Sans SC', sans-serif;
}
.header-title .highlight {
  color: #00f0ff;
  background: linear-gradient(180deg, #00f0ff 0%, #00a2ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.4);
}
.header-subtitle {
  font-size: 13.5px; font-family: 'Rajdhani', sans-serif;
  color: var(--theme-cyan);
  letter-spacing: 2px;
  text-transform: uppercase;
  font-weight: 700;
  margin-top: 2px;
}

/* 青色光轨分割线 */
.header-divider-wrapper {
  position: absolute; bottom: 0; left: 0; right: 0; height: 20px;
}
.header-divider {
  width: 100%; height: 100%;
  filter: drop-shadow(0 0 4px var(--theme-cyan));
}

.header-right {
  display: flex; align-items: center; gap: 24px;
  transform: translateY(-5px); 
}

/* 时钟与日期 */
.clock-section {
  display: flex; flex-direction: column; align-items: flex-end;
}
.clock-time {
  font-size: 32px; font-weight: normal; color: #ffffff; line-height: 1;
  font-family: 'Share Tech Mono', monospace;
  letter-spacing: 1px;
  text-shadow: 0 0 8px rgba(255, 255, 255, 0.25);
}
.clock-date {
  font-size: 13px; color: var(--text-sub); margin-top: 5px;
  font-family: 'Outfit', sans-serif;
  font-weight: 500;
}
.divider-vertical {
  width: 1px; height: 36px; background: rgba(255, 255, 255, 0.15);
}
.weather-section {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.weather-item {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 22px;
}
.weather-item .header-icon {
  width: 16px;
  height: 16px;
  min-width: 16px;
  color: var(--theme-cyan);
  filter: drop-shadow(0 0 3px rgba(0, 240, 255, 0.5));
}
.weather-item .value {
  font-size: 15px;
  font-weight: bold;
  color: #ffffff;
  font-family: 'Outfit', sans-serif;
  min-width: 50px;
  text-align: right;
}

/* 左右分栏布局 2:1 */
.content {
  flex: 1; display: grid;
  grid-template-columns: 2fr 1fr; 
  gap: var(--gap-inner); min-height: 0;
  margin-top: 10px;
}

.left-col { display: flex; flex-direction: column; gap: var(--gap-inner); min-height: 0; }
.top-panels { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gap-inner); flex-shrink: 0; height: 32%; min-height: 0; }
.scene-wrapper { flex: 1; min-height: 0; }
.right-col { display: flex; flex-direction: column; gap: var(--gap-inner); min-height: 0; }

/* 硬朗直角面板 */
.panel {
  background: var(--bg-panel);
  border-radius: 0; 
  border: var(--panel-border);
  display: flex; flex-direction: column; overflow: hidden;
  position: relative;
}

/* 左上角青色大屏角标 */
.panel::before {
  content: ''; position: absolute; top: -1px; left: -1px;
  width: 12px; height: 12px;
  border-left: 2px solid var(--theme-cyan);
  border-top: 2px solid var(--theme-cyan);
  pointer-events: none; z-index: 10;
}

/* 面板头部 */
.panel-header {
  height: 38px; padding: 0 16px; flex-shrink: 0;
  display: flex; align-items: center; gap: 8px;
  border-bottom: var(--panel-border); 
  border-left: 3px solid var(--theme-cyan); 
  background: rgba(0, 240, 255, 0.02);
}
.panel-header .title { 
  font-size: 15px; font-weight: 700; color: #ffffff;
  line-height: 1.1;
  font-family: 'Noto Sans SC', sans-serif;
  letter-spacing: 0.5px;
}
.panel-body { flex: 1; overflow: hidden; position: relative; min-height: 0; display: flex; flex-direction: column; }

/* 实时场景图 */
.scene-container {
  width: 100%; height: 100%;
  background: #020712;
  position: relative;
  background-image:
    linear-gradient(rgba(0, 240, 255, 0.07) 1.5px, transparent 1.5px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.07) 1.5px, transparent 1.5px);
  background-size: 30px 30px;
  display: flex; align-items: center; justify-content: center;
}
.scene-image {
  width: 100%; height: 100%;
  object-fit: cover;
}
</style>