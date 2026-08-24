<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

// 从环境变量读取配置
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'
const POLL_INTERVAL = parseInt(import.meta.env.VITE_POLL_INTERVAL_PROGRESS || '5000')
const PRESCRIPTION_LIMIT = parseInt(import.meta.env.VITE_PRESCRIPTION_LIMIT_PROGRESS || '20')

// 处方进度条数据列表
const prescriptions = ref([])
const loading = ref(false)
const error = ref('')

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

// 获取节点状态对应的CSS类
const getStepClass = (step) => {
  return {
    'completed': step.status === 'completed',
    'active': step.status === 'active',
    'pending': step.status === 'pending',
  }
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

        <!-- 处方进度条列表 -->
        <div v-if="prescriptions.length > 0" class="prescription-list">
          <div
            v-for="presc in prescriptions"
            :key="presc.prescription_id"
            class="prescription-row"
          >
            <!-- 左侧：处方码 -->
            <div class="presc-info">
              <span class="presc-code">{{ presc.prescription_code || '*' + presc.prescription_id }}</span>
              <span class="presc-patient">{{ presc.patient_name || '-' }}</span>
            </div>

            <!-- 右侧：4节点进度条 -->
            <div class="presc-steps-wrapper">
              <div class="steps">
                <!-- 进度条背景线 -->
                <div class="steps-progress" :style="{ width: presc.progress + '%' }"></div>

                <!-- 4个节点 -->
                <div
                  v-for="step in presc.steps"
                  :key="step.id"
                  class="step-item"
                  :class="getStepClass(step)"
                >
                  <div class="step-num">{{ step.id }}</div>
                  <div class="step-content">
                    <span class="step-title">{{ step.name }}</span>
                    <span v-if="step.desc" class="step-desc">{{ step.desc }}</span>
                  </div>
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

/* 处方列表 */
.prescription-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 药品追踪行 */
.prescription-row {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  background: var(--bg-panel-sub); border-radius: 0;
  border: var(--panel-border);
  flex-shrink: 0;
}

.presc-info { 
  display: flex; flex-direction: column; gap: 2px; min-width: 60px; 
}
.presc-code { 
  font-family: 'Share Tech Mono', monospace; font-size: 12px; font-weight: 700; color: var(--theme-cyan); 
}
.presc-patient { 
  font-size: 16px; font-weight: 700; color: #ffffff; 
}

.presc-steps-wrapper { 
  flex: 1; min-width: 0; 
}

/* 进度线 */
.steps { 
  display: flex; align-items: flex-start; justify-content: space-between; width: 100%; position: relative; 
}
.steps::before { 
  content: ''; position: absolute; top: 10px; left: 8px; right: 8px; height: 1.5px; background: rgba(255,255,255,0.08); z-index: 1; 
}
.steps-progress { 
  position: absolute; top: 10px; left: 8px; height: 1.5px; background: var(--theme-cyan); z-index: 1; 
}

.step-item { 
  display: flex; flex-direction: column; align-items: center; position: relative; z-index: 2; flex: 1; 
}
.step-item.pending { 
  opacity: 0.3; 
}
.step-num {
  width: 20px; height: 20px; border-radius: 50%; background: #020712;
  border: 1.5px solid var(--text-muted); color: var(--text-sub);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; font-family: 'Share Tech Mono', monospace;
}
.step-item.completed .step-num { 
  background: var(--theme-green); border-color: var(--theme-green); color: #020712; 
}
.step-item.active .step-num { 
  background: var(--theme-cyan); border-color: var(--theme-cyan); color: #020712; box-shadow: 0 0 8px rgba(0,240,255,0.5); 
}

.step-content { 
  margin-top: 4px; text-align: center; 
}
.step-title { 
  display: block; font-size: 11px; color: var(--text-sub); 
}
.step-desc { 
  display: block; font-size: 9px; color: var(--theme-cyan); font-weight: 700; margin-top: 1px; 
}
.step-item.active .step-title { 
  color: var(--theme-cyan); 
}
.step-item.completed .step-title { 
  color: var(--text-main); 
}
</style>