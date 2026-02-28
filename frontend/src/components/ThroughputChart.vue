<template>
  <div class="chart-container">
    <Line v-if="chartData" :data="chartData" :options="chartOptions" />
    <div v-else class="state-container">No data</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

const props = defineProps({
  weeks: { type: Array, required: true },          // ["2026-W05", ...]
  throughput: { type: Array, required: true },      // [3, 4, 5, 3]
  cycleTimeP50: { type: Array, default: () => [] }, // [7.5, 8.0, ...]
})

const chartData = computed(() => {
  if (!props.weeks.length) return null

  return {
    labels: props.weeks,
    datasets: [
      {
        label: 'Completed Issues',
        data: props.throughput,
        borderColor: '#60a5fa',
        backgroundColor: '#60a5fa22',
        tension: 0.3,
        fill: true,
        yAxisID: 'y',
      },
      ...(props.cycleTimeP50.length
        ? [
            {
              label: 'Cycle Time p50 (days)',
              data: props.cycleTimeP50,
              borderColor: '#f97316',
              backgroundColor: 'transparent',
              tension: 0.3,
              borderDash: [4, 4],
              yAxisID: 'y2',
            },
          ]
        : []),
    ],
  }
})

const chartOptions = {
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
      mode: 'index',
      intersect: false,
    },
  },
  scales: {
    x: {
      grid: { color: '#334155' },
      ticks: { color: '#94a3b8', font: { size: 11 } },
    },
    y: {
      position: 'left',
      grid: { color: '#334155' },
      ticks: { color: '#60a5fa', font: { size: 11 } },
      title: { display: true, text: 'Issues', color: '#60a5fa', font: { size: 10 } },
    },
    y2: {
      position: 'right',
      grid: { display: false },
      ticks: { color: '#f97316', font: { size: 11 } },
      title: { display: true, text: 'Days', color: '#f97316', font: { size: 10 } },
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
