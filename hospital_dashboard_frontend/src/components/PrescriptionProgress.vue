<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 从环境变量读取配置
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'
const POLL_INTERVAL = parseInt(import.meta.env.VITE_POLL_INTERVAL_PROGRESS || '5000')
const PRESCRIPTION_LIMIT = parseInt(import.meta.env.VITE_PRESCRIPTION_LIMIT_PROGRESS || '20')

// 处方进度条数据列表
const prescriptions = ref([])
const loading = ref(false)
const error = ref('')
const isExpanded = ref(false)

// 15 节点的阶段分组（竖向时间线按阶段分段展示）
const PHASES = [
  { name: '处方流转', range: [0, 5] },    // N1-N5
  { name: '跨梯运输', range: [5, 12] },    // N6-N12
  { name: '交付确认', range: [12, 15] },   // N13-N15
]

// API轮询：获取处方进度（失败时保留已有数据，不清空）
const fetchProgress = async () => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/prescriptions/progress?limit=${PRESCRIPTION_LIMIT}`)
    if (!response.ok) {
      // 503 错误（数据库连接失败）不清空已有数据
      if (response.status === 503) {
        console.warn('HIS 数据库暂时不可用，保留已有数据')
        return
      }
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const data = await response.json()
    prescriptions.value = data.list || []
    error.value = ''
  } catch (err) {
    console.error('Prescription progress fetch error:', err)
    // 网络错误不清空已有数据
    if (prescriptions.value.length === 0) {
      error.value = '数据加载失败'
    }
  }
}

let timer = null

const handleKeydown = (event) => {
  if (event.key === 'Escape' && isExpanded.value) isExpanded.value = false
}

onMounted(() => {
  fetchProgress()
  timer = setInterval(fetchProgress, POLL_INTERVAL)
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('keydown', handleKeydown)
})

// 按阶段切分时间线节点
const getPhases = (presc) => {
  const timeline = presc.timeline || []
  return PHASES.map((ph, i) => {
    const nodes = timeline.slice(ph.range[0], ph.range[1])
    const done = nodes.filter(n => n.status === 'completed').length
    return {
      key: i,
      name: ph.name,
      nodes,
      done,
      total: nodes.length,
    }
  }).filter(ph => ph.nodes.length > 0)
}

// 当前选中的处方（默认第一个进行中的，否则第一个）
const selectedCode = ref('')
const selectedPresc = computed(() => {
  if (!prescriptions.value.length) return null
  const active = prescriptions.value.find(p => p.status === 'approved')
  const target = prescriptions.value.find(p => p.prescription_code === selectedCode.value)
  return target || active || prescriptions.value[0]
})

const selectPresc = (presc) => {
  selectedCode.value = presc.prescription_code
}

const selectedIndex = computed(() => {
  if (!selectedPresc.value) return -1
  return prescriptions.value.findIndex(p => p.prescription_code === selectedPresc.value.prescription_code)
})

const selectRelative = (offset) => {
  if (!prescriptions.value.length) return
  const current = selectedIndex.value < 0 ? 0 : selectedIndex.value
  const next = Math.min(prescriptions.value.length - 1, Math.max(0, current + offset))
  selectPresc(prescriptions.value[next])
}

const openExpanded = () => {
  if (selectedPresc.value) isExpanded.value = true
}
</script>

<template>
  <div class="right-panel-wrapper panel" :class="{ 'is-expanded': isExpanded }">
    <div class="panel-header">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="header-svg">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75c.621 0 1.125.504 1.125 1.125v12.75c0 .621-.504 1.125-1.125 1.125H5.625a1.125 1.125 0 0 1-1.125-1.125V5.625c0-.621.504-1.125 1.125-1.125Z" />
      </svg>
      <span class="title">药品实时追踪</span>
      <span class="flow-count">{{ prescriptions.length }} 案运行中</span>
      <button
        v-if="selectedPresc"
        class="expand-button"
        type="button"
        :aria-label="isExpanded ? '关闭15节点放大视图' : '放大15节点视图'"
        :title="isExpanded ? '关闭（Esc）' : '点击放大15节点'"
        @click="isExpanded = !isExpanded"
      >
        <svg v-if="!isExpanded" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 8h5V3M21 8h-5V3M3 16h5v5M21 16h-5v5" />
        </svg>
        <span>{{ isExpanded ? '收起' : '放大' }}</span>
      </button>
    </div>

    <div class="panel-body">
      <div class="scroll-container">
        <!-- 空状态 -->
        <div v-if="prescriptions.length === 0 && !error" class="empty-state">
          <span>暂无进行中的处方</span>
        </div>

        <!-- 错误提示 -->
        <div v-if="error" class="error-state">
          <span>{{ error }}</span>
        </div>

        <!-- ===== 竖向 15 节点时间线 ===== -->
        <div
          v-if="selectedPresc"
          class="timeline"
          role="button"
          tabindex="0"
          :aria-label="isExpanded ? '15节点流程放大视图' : '点击放大15节点流程'"
          @click="openExpanded"
          @keydown.enter.prevent="openExpanded"
          @keydown.space.prevent="openExpanded"
        >
          <div v-if="!isExpanded" class="timeline-expand-hint">
            <span>15节点全流程</span>
            <span>点击展开</span>
          </div>
          <div
            v-for="phase in getPhases(selectedPresc)"
            :key="phase.key"
            class="phase-group"
          >
            <div class="phase-header">
              <span class="phase-name">{{ phase.name }}</span>
              <span class="phase-badge">{{ phase.done }}/{{ phase.total }}</span>
            </div>

            <div class="phase-body">
              <div
                v-for="(node, ni) in phase.nodes"
                :key="node.id"
                class="tl-node"
                :class="[node.status, { 'last-in-phase': ni === phase.nodes.length - 1 }]"
              >
                <!-- 左列：圆点 + 连接线 -->
                <div class="tl-rail">
                  <div class="tl-dot">
                    <svg v-if="node.status === 'completed'" class="dot-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  </div>
                  <div v-if="ni < phase.nodes.length - 1" class="tl-line"></div>
                </div>

                <!-- 右列：名称 + 说明 + 时间 -->
                <div class="tl-content">
                  <div class="tl-title-row">
                    <span class="tl-title">{{ node.name }}</span>
                    <span v-if="node.time" class="tl-time">{{ node.time }}</span>
                  </div>
                  <span v-if="node.desc" class="tl-desc">{{ node.desc }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>


      </div>

      <!-- 多药单切换轨道固定在面板底部，不随节点列表滚动 -->
      <div v-if="prescriptions.length > 0" class="prescription-switcher">
        <button
          class="switch-arrow"
          type="button"
          aria-label="上一张药单"
          :disabled="selectedIndex <= 0"
          @click="selectRelative(-1)"
        >‹</button>
        <div class="presc-tabs" aria-label="药单切换">
          <button
            v-for="presc in prescriptions"
            :key="presc.prescription_id"
            class="presc-tab"
            :class="{ selected: selectedPresc && presc.prescription_code === selectedPresc.prescription_code }"
            type="button"
            @click="selectPresc(presc)"
          >
            <span class="tab-patient">{{ presc.patient_name || '-' }}</span>
            <span class="tab-code">{{ presc.prescription_code || '*' + presc.prescription_id }}</span>
          </button>
        </div>
        <span class="switch-index">{{ selectedIndex + 1 }}/{{ prescriptions.length }}</span>
        <button
          class="switch-arrow"
          type="button"
          aria-label="下一张药单"
          :disabled="selectedIndex >= prescriptions.length - 1"
          @click="selectRelative(1)"
        >›</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.right-panel-wrapper {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
}
.right-panel-wrapper.is-expanded {
  position: fixed;
  inset: 22px;
  z-index: 1000;
  background: #020816;
  border-color: rgba(0, 240, 255, 0.72);
  box-shadow: 0 0 0 100vmax rgba(0, 4, 12, 0.82), 0 0 42px rgba(0, 240, 255, 0.18);
}

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
.header-svg { width: 19px; height: 19px; color: var(--theme-cyan); }

.flow-count {
  margin-left: auto; font-size: 13px; font-weight: 700;
  background: var(--theme-cyan); color: #020712;
  padding: 2px 6px; border-radius: 0;
  font-family: 'Rajdhani', sans-serif;
}

.expand-button {
  height: 30px; padding: 0 10px; border: 1px solid rgba(0, 240, 255, 0.42);
  background: rgba(0, 240, 255, 0.08); color: var(--theme-cyan);
  display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
  font: 700 13px/1 'Noto Sans SC', sans-serif;
}
.expand-button:hover,
.expand-button:focus-visible { background: rgba(0, 240, 255, 0.16); outline: 2px solid rgba(0, 240, 255, 0.34); outline-offset: 2px; }
.expand-button svg { width: 15px; height: 15px; }

.panel-body {
  flex: 1; overflow: hidden; position: relative; min-height: 0; display: flex; flex-direction: column;
}

.scroll-container {
  width: 100%; flex: 1; min-height: 0; padding: 12px;
  overflow-y: auto; display: flex; flex-direction: column; gap: 10px;
}
.scroll-container::-webkit-scrollbar { width: 4px; }
.scroll-container::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.2); }
.scroll-container::-webkit-scrollbar-thumb { background: var(--theme-cyan); }

.empty-state,
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-sub);
  font-size: 16px;
}

.error-state {
  color: var(--theme-orange);
}

/* ===== 底部药单切换轨道 ===== */
.prescription-switcher {
  flex-shrink: 0; min-height: 68px; padding: 8px 10px;
  border-top: 1px solid rgba(0, 240, 255, 0.28);
  background: linear-gradient(180deg, rgba(4, 16, 36, 0.96), rgba(2, 9, 24, 0.98));
  display: grid; grid-template-columns: 32px minmax(0, 1fr) auto 32px; gap: 8px; align-items: center;
}
.presc-tabs {
  display: flex; gap: 8px; overflow-x: auto; min-width: 0;
  padding: 2px 0 5px;
}
.presc-tabs::-webkit-scrollbar { height: 3px; }
.presc-tabs::-webkit-scrollbar-thumb { background: var(--theme-cyan); }

.presc-tab {
  flex: 0 0 min(190px, 72%); display: flex; flex-direction: column; align-items: flex-start; gap: 2px;
  padding: 7px 10px; cursor: pointer;
  background: var(--bg-panel-sub); border: var(--panel-border);
  border-bottom: 2px solid transparent;
  transition: border-color 0.2s, background 0.2s, transform 0.2s;
}
.presc-tab:hover { border-bottom-color: var(--theme-cyan); transform: translateY(-1px); }
.presc-tab:focus-visible { outline: 2px solid var(--theme-cyan); outline-offset: -2px; }
.presc-tab.selected {
  border-bottom-color: var(--theme-cyan);
  background: rgba(0, 240, 255, 0.1);
}
.tab-code {
  max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: 'Share Tech Mono', monospace; font-size: 12px; font-weight: 700;
  color: var(--text-sub);
}
.tab-patient { font-size: 15px; font-weight: 800; color: #ffffff; }
.presc-tab.selected .tab-patient,
.presc-tab.selected .tab-code { color: var(--theme-cyan); }
.switch-arrow {
  width: 32px; height: 42px; border: 1px solid rgba(0, 240, 255, 0.28);
  background: rgba(0, 240, 255, 0.06); color: var(--theme-cyan); cursor: pointer;
  font: 500 26px/1 'Rajdhani', sans-serif;
}
.switch-arrow:hover:not(:disabled),
.switch-arrow:focus-visible { background: rgba(0, 240, 255, 0.16); outline: none; }
.switch-arrow:disabled { opacity: 0.24; cursor: default; }
.switch-index {
  min-width: 38px; text-align: center; color: var(--theme-cyan);
  font: 700 14px/1 'Share Tech Mono', monospace;
}

/* ===== 竖向 15 节点时间线 ===== */
.timeline {
  display: flex; flex-direction: column; gap: 10px; flex-shrink: 0;
  cursor: zoom-in; position: relative;
  transition: background 0.2s;
}
.timeline:hover .timeline-expand-hint,
.timeline:focus-visible .timeline-expand-hint { border-color: var(--theme-cyan); background: rgba(0, 240, 255, 0.12); }
.timeline:focus-visible { outline: 2px solid rgba(0, 240, 255, 0.5); outline-offset: 3px; }
.timeline-expand-hint {
  min-height: 32px; padding: 0 10px; border: 1px dashed rgba(0, 240, 255, 0.28);
  display: flex; align-items: center; justify-content: space-between;
  color: var(--text-sub); font-size: 13px; font-weight: 700;
}
.timeline-expand-hint span:last-child { color: var(--theme-cyan); }

.phase-group {
  background: var(--bg-panel-sub); border: var(--panel-border);
}

.phase-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 12px;
  border-bottom: var(--panel-border);
  border-left: 2px solid var(--theme-cyan);
  background: rgba(0, 240, 255, 0.02);
}
.phase-name {
  font-size: 15px; font-weight: 700; color: var(--text-main);
  letter-spacing: 1px;
}
.phase-badge {
  font-size: 13px; font-weight: 700; font-family: 'Rajdhani', sans-serif;
  color: var(--theme-cyan);
}

.phase-body { padding: 8px 12px 4px; }

.tl-node {
  display: flex; gap: 10px;
}
.tl-node.pending { opacity: 0.35; }

.tl-rail {
  display: flex; flex-direction: column; align-items: center;
  width: 16px; flex-shrink: 0;
}
.tl-dot {
  width: 13px; height: 13px; border-radius: 50%;
  background: #020712; border: 1.5px solid var(--text-muted);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 2px;
  box-sizing: border-box;
}
.tl-dot .dot-check { width: 8px; height: 8px; }

.tl-line {
  width: 1.5px; flex: 1; min-height: 14px; margin: 2px 0;
  background: rgba(255, 255, 255, 0.1);
}
.tl-node.completed .tl-line {
  background: var(--theme-cyan);
}
.tl-node.last-in-phase .tl-line { display: none; }

.tl-node.completed .tl-dot {
  background: var(--theme-green); border-color: var(--theme-green); color: #020712;
}
.tl-node.active .tl-dot {
  background: var(--theme-cyan); border-color: var(--theme-cyan); color: #020712;
  box-shadow: 0 0 8px rgba(0, 240, 255, 0.6);
  animation: dot-breath 1.6s ease-in-out infinite;
}
@keyframes dot-breath {
  0%, 100% { box-shadow: 0 0 4px rgba(0, 240, 255, 0.35); }
  50% { box-shadow: 0 0 12px rgba(0, 240, 255, 0.8); }
}

.tl-content {
  flex: 1; min-width: 0; padding-bottom: 8px;
}
.tl-title-row {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
}
.tl-title {
  font-size: 15px; font-weight: 700; color: var(--text-sub);
}
.tl-node.active .tl-title { color: var(--theme-cyan); }
.tl-node.completed .tl-title { color: var(--text-main); }

.tl-time {
  font-family: 'Share Tech Mono', monospace; font-size: 12px;
  color: var(--text-muted); flex-shrink: 0;
}
.tl-node.active .tl-time { color: var(--theme-cyan); }

.tl-desc {
  display: block; font-size: 12px; color: var(--theme-cyan);
  font-weight: 700; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.is-expanded .panel-header { height: 54px; padding: 0 22px; }
.is-expanded .panel-header .title { font-size: 22px; }
.is-expanded .scroll-container { padding: 18px 20px; }
.is-expanded .timeline {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px; cursor: default; align-items: stretch; flex: 1;
}
.is-expanded .phase-group { min-height: 100%; border-color: rgba(0, 240, 255, 0.24); }
.is-expanded .phase-header { padding: 11px 16px; }
.is-expanded .phase-name { font-size: 18px; }
.is-expanded .phase-badge { font-size: 15px; }
.is-expanded .phase-body { padding: 14px 16px 8px; }
.is-expanded .tl-node { gap: 13px; }
.is-expanded .tl-rail { width: 20px; }
.is-expanded .tl-dot { width: 17px; height: 17px; }
.is-expanded .tl-dot .dot-check { width: 11px; height: 11px; }
.is-expanded .tl-content { padding-bottom: 16px; }
.is-expanded .tl-title { font-size: 17px; }
.is-expanded .tl-time { font-size: 14px; }
.is-expanded .tl-desc { font-size: 14px; margin-top: 4px; white-space: normal; line-height: 1.45; }
.is-expanded .prescription-switcher { min-height: 78px; padding: 10px 18px; }
.is-expanded .presc-tab { flex-basis: 220px; }

@media (max-width: 1100px) {
  .right-panel-wrapper.is-expanded { inset: 10px; }
  .is-expanded .timeline { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: reduce) {
  .tl-node.active .tl-dot { animation: none; }
  .presc-tab { transition: none; }
}

</style>
