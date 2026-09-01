<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'

// 从环境变量读取配置
const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'
const POLL_INTERVAL = parseInt(import.meta.env.VITE_POLL_INTERVAL_MONITOR || '5000')
const PRESCRIPTION_LIMIT = parseInt(import.meta.env.VITE_PRESCRIPTION_LIMIT_MONITOR || '30')

const items = ref([])
const stats = ref({ total: 0, pending: 0, approved: 0, dispensed: 0 })
const loading = ref(true)
const error = ref('')
let pollTimer = null

const fetchData = async () => {
  try {
    const [itemsRes, statsRes] = await Promise.all([
      fetch(`${backendUrl}/api/v1/prescriptions/items/latest?limit=${PRESCRIPTION_LIMIT}`),
      fetch(`${backendUrl}/api/v1/prescriptions/stats`),
    ])
    // 503 错误（数据库连接失败）不清空已有数据
    if (itemsRes.ok) {
      const data = await itemsRes.json()
      items.value = data.list || []
    } else if (itemsRes.status === 503) {
      console.warn('HIS 数据库暂时不可用，保留已有药品数据')
      return
    }
    if (statsRes.ok) {
      const data = await statsRes.json()
      stats.value = data
    } else if (statsRes.status === 503) {
      console.warn('HIS 数据库暂时不可用，保留已有统计数据')
      return
    }
    error.value = ''
    loading.value = false
  } catch (e) {
    console.error('PrescriptionMonitor fetch error:', e)
    // 网络错误不清空已有数据
    if (items.value.length === 0) {
      error.value = '数据获取失败'
    }
    loading.value = false
  }
}

onMounted(() => {
  fetchData()
  pollTimer = setInterval(fetchData, POLL_INTERVAL)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// 按处方 ID 分组药品明细并按状态及时间排序
const groupedByPrescription = computed(() => {
  const groups = {}
  for (const item of items.value) {
    const pid = item.prescription_id
    if (!groups[pid]) {
      groups[pid] = {
        prescription_id: pid,
        prescription_code: item.prescription_code || '',
        patient_name: item.patient_name || '未知患者',
        doctor_name: item.doctor_name || '系统医生',
        status: item.prescription_status,
        created_at: item.created_at,
        items: [],
      }
    }
    groups[pid].items.push(item)
  }
  return Object.values(groups).sort((a, b) => {
    if (a.status === 'pending' && b.status !== 'pending') return -1
    if (a.status !== 'pending' && b.status === 'pending') return 1
    if (a.status === 'approved' && b.status !== 'approved' && b.status !== 'pending') return -1
    if (a.status !== 'approved' && a.status !== 'pending' && b.status === 'approved') return 1
    return new Date(b.created_at) - new Date(a.created_at)
  })
})

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 圆环图计算
const pendingPercent = computed(() => {
  if (stats.value.total === 0) return 0
  return (stats.value.pending / stats.value.total) * 100
})
const dispensedPercent = computed(() => {
  if (stats.value.total === 0) return 0
  return (stats.value.dispensed / stats.value.total) * 100
})
</script>

<template>
  <div class="right-panel-wrapper panel">
    <div class="panel-header">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="header-svg">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.109A11.386 11.386 0 0 1 10.089 20.8a11.383 11.383 0 0 1-4.966-1.564V19.13M21 15.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM6 18.303V19.13m4.5-3.13h-4.5m4.5 0A4.125 4.125 0 0 0 3 15.75m12 0v-.003c0-1.113-.285-2.16-.786-3.07M3 15.75a3 3 0 1 1 6 0 3 3 0 0 1-6 0Zm9.458-10.223a3 3 0 1 1-5.714 0 3 3 0 0 1 5.714 0ZM21 12.75a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0ZM2.25 12.75a2.25 2.25 0 1 1 4.5 0 2.25 2.25 0 0 1-4.5 0Z" />
      </svg>
      <span class="title">处方实时队列</span>
      <span class="flow-count sync">HIS 实时同步</span>
    </div>

    <div class="panel-body">
      <!-- KPI 横向铺开 -->
      <div class="kpi-horizontal-row">
        <div class="kpi-card warning">
          <div class="kpi-info">
            <span class="kpi-label">排队待配</span>
            <span class="kpi-val">{{ stats.pending || 0 }}</span>
          </div>
        </div>
        <div class="kpi-card success">
          <div class="kpi-info">
            <span class="kpi-label">已配发</span>
            <span class="kpi-val">{{ stats.dispensed || 0 }}</span>
          </div>
        </div>
        <div class="kpi-card info">
          <div class="kpi-info">
            <span class="kpi-label">今日总额</span>
            <span class="kpi-val">{{ stats.total || 0 }}</span>
          </div>
        </div>
      </div>

      <!-- 左右分栏布局 -->
      <div class="queue-content-split">
        <!-- 左侧患者卡片滚动区域 -->
        <div class="queue-scroll-list">
          <div 
            v-for="group in groupedByPrescription" 
            :key="group.prescription_id"
            class="patient-card"
            :class="{ 'pending-card': group.status === 'pending', 'completed-card': group.status === 'approved' || group.status === 'dispensed' }"
          >
            <div class="card-row-top">
              <span class="patient-name">{{ group.patient_name }}</span>
              <span class="patient-time">{{ formatTime(group.created_at) }} · {{ group.prescription_code || '#' + group.prescription_id }}</span>
            </div>
            <div class="card-row-bottom">
              <div class="medicine-tags">
                <span 
                  v-for="item in group.items" 
                  :key="item.id" 
                  class="medicine-tag"
                >
                  {{ item.medicine_name }} <span class="tag-qty">x{{ item.quantity }}</span>
                </span>
              </div>
              <span 
                class="status-tag"
                :class="{ 'completed': group.status === 'approved' || group.status === 'dispensed', 'pending': group.status === 'pending' }"
              >
                {{ group.status === 'approved' ? '已配发' : group.status === 'dispensed' ? '已取药' : group.status === 'rejected' ? '已拒绝' : '准备中' }}
              </span>
            </div>
          </div>
          
          <div v-if="!groupedByPrescription.length" class="empty-state">
            <span>暂无患者数据</span>
          </div>
        </div>

        <!-- 右侧圆环图表区域 -->
        <div class="donut-chart-panel">
          <svg class="donut-chart" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="15.9155" fill="none" stroke="rgba(255, 255, 255, 0.05)" stroke-width="3"></circle>
            <circle cx="18" cy="18" r="15.9155" fill="none" stroke="var(--theme-orange)" stroke-width="3.2" :stroke-dasharray="`${pendingPercent} ${100 - pendingPercent}`" stroke-dashoffset="25" class="donut-segment"></circle>
            <circle cx="18" cy="18" r="15.9155" fill="none" stroke="var(--theme-green)" stroke-width="3.2" :stroke-dasharray="`${dispensedPercent} ${100 - dispensedPercent}`" :stroke-dashoffset="25 - pendingPercent" class="donut-segment"></circle>
            <g class="donut-text">
              <text x="50%" y="46%" class="chart-num">{{ stats.total || 0 }}</text>
              <text x="50%" y="71%" class="chart-label">总数</text>
            </g>
          </svg>
          <div class="donut-legend">
            <div class="legend-item">
              <div class="legend-label-group">
                <span class="dot warning"></span>
                <span>待配</span>
              </div>
              <span class="legend-val">{{ stats.pending || 0 }}</span>
            </div>
            <div class="legend-item">
              <div class="legend-label-group">
                <span class="dot success"></span>
                <span>已配</span>
              </div>
              <span class="legend-val">{{ stats.dispensed || 0 }}</span>
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

.panel-body { 
  flex: 1; overflow: hidden; position: relative; min-height: 0; display: flex; flex-direction: column; 
}

/* KPI 横向铺开 */
.kpi-horizontal-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px 14px 0 14px;
  flex-shrink: 0;
}

.kpi-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(5, 15, 35, 0.4);
  border: 1px solid #053b68;
  border-radius: 0;
}
.kpi-card.warning { border-left: 3px solid var(--theme-orange); }
.kpi-card.success { border-left: 3px solid var(--theme-green); }
.kpi-card.info { border-left: 3px solid var(--theme-cyan); }

.kpi-info { display: flex; flex-direction: column; }
.kpi-label { font-size: 14px; color: var(--text-sub); }
.kpi-val { font-size: 27px; font-weight: 700; font-family: 'Rajdhani', sans-serif; }
.kpi-card.warning .kpi-val { color: var(--theme-orange); }
.kpi-card.success .kpi-val { color: var(--theme-green); }
.kpi-card.info .kpi-val { color: var(--theme-cyan); }

/* 左右分栏 */
.queue-content-split {
  flex: 1;
  display: grid;
  grid-template-columns: 1.75fr 1.25fr;
  gap: 12px;
  min-height: 0;
  padding: 12px 14px 14px 14px;
}

.queue-scroll-list {
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.queue-scroll-list::-webkit-scrollbar { width: 3px; }
.queue-scroll-list::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.2); }
.queue-scroll-list::-webkit-scrollbar-thumb { background: var(--theme-cyan); }

/* 患者卡片 */
.patient-card {
  border: 1px solid #053b68;
  background: rgba(5, 15, 32, 0.5);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-radius: 0;
  flex-shrink: 0;
}
.patient-card.pending-card { border-left: 3px solid var(--theme-orange); }
.patient-card.completed-card { opacity: 0.4; }

.card-row-top { display: flex; justify-content: space-between; align-items: center; }
.patient-name { font-size: 18px; font-weight: 900; color: #ffffff; }
.patient-time { font-size: 14px; color: var(--text-sub); font-family: 'Share Tech Mono', monospace; }

.card-row-bottom { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.medicine-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.medicine-tag {
  background: rgba(0,0,0,0.3); color: var(--text-sub); padding: 3px 7px; border-radius: 0; font-size: 13px;
  border: 1px solid rgba(255, 255, 255, 0.03);
}
.tag-qty { color: var(--theme-cyan); font-weight: bold; margin-left: 2px; }

.status-tag { padding: 4px 7px; border-radius: 0; font-size: 12px; font-weight: 700; background: rgba(0, 0, 0, 0.2); color: var(--text-muted); }
.status-tag.completed { background: rgba(0, 255, 102, 0.1); color: var(--theme-green); border: 1px solid rgba(0, 255, 102, 0.2); }
.status-tag.pending { background: rgba(255, 115, 0, 0.1); color: var(--theme-orange); border: 1px solid rgba(255, 115, 0, 0.2); }

.empty-state {
  padding: 30px;
  text-align: center;
  color: var(--text-sub);
  font-size: 14px;
}

/* 圆环统计 */
.donut-chart-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(5, 15, 35, 0.2);
  border: 1px solid #053b68;
  padding: 12px;
}

.donut-chart {
  width: 70px; height: 70px; transform: rotate(-90deg);
}
.donut-segment { transition: stroke-dashoffset 0.3s; }
.donut-text { transform: rotate(90deg); transform-origin: 50% 50%; text-anchor: middle; }
.chart-num { font-family: 'Rajdhani', sans-serif; font-size: 10px; font-weight: bold; fill: var(--text-main); }
.chart-label { font-family: 'Outfit', sans-serif; font-size: 3.5px; fill: var(--text-sub); font-weight: bold; letter-spacing: 0.5px; }

.donut-legend { display: flex; flex-direction: column; gap: 6px; margin-top: 14px; width: 100%; padding: 0 8px; font-family: 'Outfit', sans-serif; }
.legend-item { display: flex; align-items: center; justify-content: space-between; font-size: 14px; color: var(--text-sub); font-weight: bold; }
.legend-label-group { display: flex; align-items: center; gap: 6px; }
.legend-item .dot { width: 6px; height: 6px; border-radius: 50%; }
.legend-item .dot.warning { background: var(--theme-orange); }
.legend-item .dot.success { background: var(--theme-green); }
.legend-val { color: #ffffff; font-family: 'Rajdhani', sans-serif; font-size: 16px; }
</style>
