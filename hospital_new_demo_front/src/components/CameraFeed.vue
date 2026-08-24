<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: '摄像头' },
  streamUrl: { type: String, required: true },
  fallbackVideo: { type: String, default: '' },
})

// 从 .env 读取加载阈值（带默认值）：超时或连续失败后回退到本地备用视频
const CONNECT_TIMEOUT = Number(import.meta.env.VITE_CAMERA_CONNECT_TIMEOUT) || 5000
const MAX_ERRORS = Number(import.meta.env.VITE_CAMERA_MAX_ERRORS) || 3

const isConnected = ref(false)
const streamKey = ref(0)
const isLoadSuccess = ref(false)
const errorCount = ref(0)

let connectionTimeout = null
let retryTimeout = null

// 当前流URL - 只在成功连接后添加时间戳防缓存
const currentStreamUrl = computed(() => {
  if (!isConnected.value) return ''
  // 只在首次连接时添加时间戳，后续不刷新
  const separator = props.streamUrl.includes('?') ? '&' : '?'
  return `${props.streamUrl}${separator}t=${streamKey.value}`
})

// 连接实时流（挂载时自动调用 + 点击手动重试共用）
const connectStream = () => {
  if (isConnected.value) return

  // 重置状态
  errorCount.value = 0
  isLoadSuccess.value = false

  // 生成新的流Key（防止缓存）
  streamKey.value = Date.now()
  isConnected.value = true

  // 设置连接超时检测
  if (connectionTimeout) clearTimeout(connectionTimeout)
  connectionTimeout = setTimeout(() => {
    // 超时内没有成功加载，切回备用视频
    if (!isLoadSuccess.value) {
      console.log(`[${props.title}] 连接超时，切回备用视频`)
      disconnectStream()
    }
  }, CONNECT_TIMEOUT)
}

// 点击：手动重试连接（已在实时流时无效）
const handleCameraClick = () => {
  connectStream()
}

// 挂载即自动连接实时流（实时优先，失败回退本地视频）
onMounted(() => {
  connectStream()
})

// 图片加载成功
const handleImageLoad = () => {
  isLoadSuccess.value = true
  errorCount.value = 0
  if (connectionTimeout) {
    clearTimeout(connectionTimeout)
    connectionTimeout = null
  }
  console.log(`[${props.title}] 流连接成功`)
}

// 图片加载失败
const handleImageError = () => {
  errorCount.value++
  console.error(`[${props.title}] 流加载失败，错误计数: ${errorCount.value}`)
  
  // 连续失败达到阈值，断开连接
  if (errorCount.value >= MAX_ERRORS) {
    console.log(`[${props.title}] 连续失败${MAX_ERRORS}次，切回备用视频`)
    disconnectStream()
  }
}

// 断开流连接
const disconnectStream = () => {
  isConnected.value = false
  isLoadSuccess.value = false
  errorCount.value = 0
  
  if (connectionTimeout) {
    clearTimeout(connectionTimeout)
    connectionTimeout = null
  }
  if (retryTimeout) {
    clearTimeout(retryTimeout)
    retryTimeout = null
  }
}

// 备用视频加载失败
const handleVideoError = () => {
  console.error(`[${props.title}] 备用视频加载失败`)
}

// 组件卸载时清理
onUnmounted(() => {
  disconnectStream()
})

// 监听streamUrl变化，重新连接
watch(() => props.streamUrl, () => {
  if (isConnected.value) {
    // 如果已连接，重新触发连接
    disconnectStream()
    setTimeout(() => connectStream(), 100)
  }
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span class="title">{{ title }}</span>
    </div>
    <div class="panel-body camera-body" @click="handleCameraClick">
      <div class="camera-viewfinder"></div>

      <!-- 点击后显示实时流 -->
      <img
        v-show="isConnected"
        :key="streamKey"
        :src="currentStreamUrl"
        alt="Camera feed"
        class="video-feed"
        @load="handleImageLoad"
        @error="handleImageError"
      />

      <!-- 默认显示备用视频 -->
      <video
        v-show="!isConnected"
        class="video-feed"
        autoplay
        muted
        loop
        playsinline
        @error="handleVideoError"
      >
        <source :src="fallbackVideo" type="video/mp4">
      </video>

      <!-- 连接提示 -->
      <div v-if="isConnected && !isLoadSuccess" class="connecting-overlay">
        <span>正在连接...</span>
      </div>
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

.connecting-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(1, 6, 16, 0.8);
  z-index: 5;
  color: var(--theme-cyan);
  font-size: 14px;
  font-weight: 600;
}
</style>