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

onMounted(() => {
  fetchProgress()
  timer = setInterval(fetchProgress, POLL_INTERVAL)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
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
</script>

<template>
  <div class="right-panel-wrapper panel">
    <div class="panel-header">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="header-svg">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75c.621 0 1.125.504 1.125 1.125v12.75c0 .621-.504 1.125-1.125 1.125H5.625a1.125 1.125 0 0 1-1.125-1.125V5.625c0-.621.504-1.125 1.125-1.125Z" />
      </svg>
      <span class="title">药品实时追踪</span>
      <span class="flow-count">{{ prescriptions.length }} 案运行中</span>
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

        <!-- 处方选择器（横向药丸） -->
        <div v-if="prescriptions.length > 0" class="presc-tabs">
          <button
            v-for="presc in prescriptions"
            :key="presc.prescription_id"
            class="presc-tab"
            :class="{ selected: selectedPresc && presc.prescription_code === selectedPresc.prescription_code }"
            @click="selectPresc(presc)"
          >
            <span class="tab-code">{{ presc.prescription_code || '*' + presc.prescription_id }}</span>
            <span class="tab-patient">{{ presc.patient_name || '-' }}</span>
          </button>
        </div>

        <!-- ===== 竖向 15 节点时间线 ===== -->
        <div v-if="selectedPresc" class="timeline">
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
    </div>
  </div>
</template>

<style scoped>
.right-panel-wrapper {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
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
.header-svg { width: 16px; height: 16px; color: var(--theme-cyan); }

.flow-count {
  margin-left: auto; font-size: 11px; font-weight: 700;
  background: var(--theme-cyan); color: #020712;
  padding: 2px 6px; border-radius: 0;
  font-family: 'Rajdhani', sans-serif;
}

.panel-body {
  flex: 1; overflow: hidden; position: relative; min-height: 0; display: flex; flex-direction: column;
}

.scroll-container {
  width: 100%; height: 100%; padding: 12px;
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
  font-size: 14px;
}

.error-state {
  color: var(--theme-orange);
}

/* ===== 处方选择器 ===== */
.presc-tabs {
  display: flex; gap: 8px; overflow-x: auto; flex-shrink: 0;
  padding-bottom: 4px;
}
.presc-tabs::-webkit-scrollbar { height: 3px; }
.presc-tabs::-webkit-scrollbar-thumb { background: var(--theme-cyan); }

.presc-tab {
  flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-start; gap: 1px;
  padding: 5px 10px; cursor: pointer;
  background: var(--bg-panel-sub); border: var(--panel-border);
  border-left: 2px solid transparent;
  transition: border-color 0.2s, background 0.2s;
}
.presc-tab:hover { border-left-color: var(--theme-cyan); }
.presc-tab.selected {
  border-left-color: var(--theme-cyan);
  background: rgba(0, 240, 255, 0.06);
}
.tab-code {
  font-family: 'Share Tech Mono', monospace; font-size: 10px; font-weight: 700;
  color: var(--theme-cyan);
}
.tab-patient { font-size: 12px; font-weight: 700; color: #ffffff; }

/* ===== 竖向 15 节点时间线 ===== */
.timeline {
  display: flex; flex-direction: column; gap: 10px; flex-shrink: 0;
}

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
  font-size: 12px; font-weight: 700; color: var(--text-main);
  letter-spacing: 1px;
}
.phase-badge {
  font-size: 10px; font-weight: 700; font-family: 'Rajdhani', sans-serif;
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
  font-size: 12px; font-weight: 700; color: var(--text-sub);
}
.tl-node.active .tl-title { color: var(--theme-cyan); }
.tl-node.completed .tl-title { color: var(--text-main); }

.tl-time {
  font-family: 'Share Tech Mono', monospace; font-size: 10px;
  color: var(--text-muted); flex-shrink: 0;
}
.tl-node.active .tl-time { color: var(--theme-cyan); }

.tl-desc {
  display: block; font-size: 10px; color: var(--theme-cyan);
  font-weight: 700; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

</style>
