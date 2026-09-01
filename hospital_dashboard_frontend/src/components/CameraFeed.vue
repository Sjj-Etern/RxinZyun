<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: '摄像头' },
  streamUrl: { type: String, required: true },
  fallbackVideo: { type: String, default: '' },
})

// 从 .env 读取加载阈值（带默认值）
const CONNECT_TIMEOUT = Number(import.meta.env.VITE_CAMERA_CONNECT_TIMEOUT) || 5000
// 探测失败后的静默重试间隔（毫秒）：摄像头恢复后自动切回实时流
const RETRY_INTERVAL = 10000

// 播放模式：video = 备用视频（默认，永远有画面）；live = 实时流
const mode = ref('video')
const streamKey = ref(0)

let probeTimer = null   // 探测超时计时器
let retryTimer = null   // 周期重试计时器
let disposed = false

// 当前实时流 URL（带时间戳防缓存）。隐藏探测与展示复用同一个 img，避免建立两条流连接。
const streamUrl = computed(() => {
  const separator = props.streamUrl.includes('?') ? '&' : '?'
  return `${props.streamUrl}${separator}t=${streamKey.value}`
})

// 静默探测实时流：隐藏 img 尝试加载，首帧到达 = 摄像头在线。
// 探测成功后直接显示同一条连接，避免 ROS/Flask 服务被双连接占用。
const startProbe = () => {
  if (disposed) return
  stopTimers()
  streamKey.value = Date.now()
  probeTimer = setTimeout(() => {
    // 超时未收到首帧：保持备用视频，安排下次静默重试
    scheduleRetry()
  }, CONNECT_TIMEOUT)
}

const stopTimers = () => {
  if (probeTimer) { clearTimeout(probeTimer); probeTimer = null }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
}

const scheduleRetry = () => {
  if (disposed) return
  stopTimers()
  retryTimer = setTimeout(() => startProbe(), RETRY_INTERVAL)
}

// 探测成功：无感切换到实时流
const handleProbeLoad = () => {
  if (disposed) return
  stopTimers()
  mode.value = 'live'
  console.log(`[${props.title}] 实时流已接通`)
}

// 流请求失败或中断：静默保持/切回备用视频，并恢复探测。
const handleStreamError = () => {
  if (mode.value === 'live') {
    mode.value = 'video'
    console.log(`[${props.title}] 实时流中断，已无缝切回备用画面`)
  }
  scheduleRetry()
}

onMounted(() => {
  // 默认播放备用视频，同时后台静默探测实时流
  startProbe()
})

onUnmounted(() => {
  disposed = true
  stopTimers()
})

// 监听streamUrl变化，重新探测
watch(() => props.streamUrl, () => {
  mode.value = 'video'
  startProbe()
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span class="title">{{ title }}</span>
    </div>
    <div class="panel-body camera-body">
      <div class="camera-viewfinder"></div>

      <!-- 实时流：探测成功后显示同一条连接；中断即切回备用视频 -->
      <img
        :key="streamKey"
        :src="streamUrl"
        alt=""
        class="video-feed live-stream"
        :class="{ 'live-stream--hidden': mode !== 'live' }"
        @load="handleProbeLoad"
        @error="handleStreamError"
      />

      <!-- 备用视频（默认画面，循环播放，永远有内容） -->
      <video
        v-show="mode !== 'live'"
        class="video-feed"
        autoplay
        muted
        loop
        playsinline
      >
        <source :src="fallbackVideo" type="video/mp4">
      </video>

    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--bg-panel);
  border-radius: 0;
  border: var(--panel-border);
  display: flex; flex-direction: column; overflow: hidden;
  position: relative;
  height: 100%;
}

.panel::before {
  content: ''; position: absolute; top: -1px; left: -1px;
  width: 12px; height: 12px;
  border-left: 2px solid var(--theme-cyan);
  border-top: 2px solid var(--theme-cyan);
  pointer-events: none; z-index: 10;
}

.panel-header {
  height: 44px; padding: 0 16px; flex-shrink: 0;
  display: flex; align-items: center; gap: 8px;
  border-bottom: var(--panel-border);
  border-left: 3px solid var(--theme-cyan);
  background: rgba(0, 240, 255, 0.02);
}
.panel-header .title {
  font-size: 18px; font-weight: 700; color: #ffffff;
  line-height: 1.1;
  font-family: 'Noto Sans SC', sans-serif;
  letter-spacing: 0.5px;
}

.camera-body {
  background: #010610;
  position: relative;
  flex: 1;
  min-height: 0;
  cursor: pointer;
}

.camera-body::before {
  content: ''; position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.006) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.006) 1px, transparent 1px);
  background-size: 8px 8px;
  pointer-events: none; z-index: 1;
}

.camera-body::after {
  content: ''; position: absolute; left: 0; width: 100%; height: 2px;
  background: linear-gradient(90deg, transparent, rgba(0, 240, 255, 0.2), transparent);
  animation: laser-sweep 4s linear infinite;
  pointer-events: none; z-index: 4;
}
@keyframes laser-sweep {
  0% { top: 0; }
  100% { top: 100%; }
}

.camera-viewfinder {
  position: absolute; inset: 10px; pointer-events: none; z-index: 3;
  border: 1px solid rgba(255, 255, 255, 0.02);
}
.camera-viewfinder::before, .camera-viewfinder::after {
  content: ''; position: absolute; width: 8px; height: 8px; border-color: rgba(0, 240, 255, 0.3); border-style: solid;
}
.camera-viewfinder::before { top: -1px; left: -1px; border-width: 1.5px 0 0 1.5px; }
.camera-viewfinder::after { bottom: -1px; right: -1px; border-width: 0 1.5px 1.5px 0; }

.video-feed {
  width: 100%;
  height: 100%;
  object-fit: cover;
  position: relative;
  z-index: 2;
}
.live-stream--hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
</style>
