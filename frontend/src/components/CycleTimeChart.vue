<template>
  <div class="chart-container">
    <Bar v-if="chartData" :data="chartData" :options="chartOptions" />
    <div v-else class="state-container">No data</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const props = defineProps({
  // { project_key: { cycle_time: { phase_id: { p50, p75, p90, count } } } }
  projects: { type: Object, required: true },
  phases: { type: Array, required: true },
})

const chartData = computed(() => {
  const projectKeys = Object.keys(props.projects)
  if (!projectKeys.length) return null

  // 只顯示至少有一個 project 有資料的 phase
  const activePhases = props.phases.filter((phase) =>
    projectKeys.some(
      (pk) => (props.projects[pk].cycle_time[phase.id]?.count ?? 0) > 0,
    ),
  )

  if (!activePhases.length) return null

  const datasets = activePhases.map((phase) => ({
    label: phase.label,
    data: projectKeys.map((pk) => props.projects[pk].cycle_time[phase.id]?.p50 ?? 0),
    backgroundColor: phase.color + 'cc',  // 80% opacity
    borderColor: phase.color,
    borderWidth: 1,
  }))

  return { labels: projectKeys, datasets }
})

const chartOptions = {
  indexAxis: 'y',  // 橫向條形圖
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        color: '#94a3b8',
        boxWidth: 12,
        font: { size: 11 },
      },
    },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const pk = ctx.chart.data.labels[ctx.dataIndex]
          const phase = ctx.chart.data.datasets[ctx.datasetIndex]
          // 從 props 取得當前 project + phase 的 p75/p90
          const phaseId = props.phases.find((p) => p.label === phase.label)?.id
          const stat = phaseId ? props.projects[pk]?.cycle_time?.[phaseId] : null
          const extra = stat
            ? `  p75: ${stat.p75}d  p90: ${stat.p90}d`
            : ''
          return ` ${phase.label}: ${ctx.parsed.x}d (p50)${extra}`
        },
      },
    },
  },
  scales: {
    x: {
      stacked: true,
      grid: { color: '#334155' },
      ticks: { color: '#94a3b8', font: { size: 11 } },
      title: {
        display: true,
        text: 'Days (p50)',
        color: '#94a3b8',
        font: { size: 11 },
      },
    },
    y: {
      stacked: true,
      grid: { display: false },
      ticks: { color: '#f1f5f9', font: { size: 11 } },
    },
  },
}
</script>

<style scoped>
.chart-container {
  position: relative;
  height: 200px;
}
</style>
