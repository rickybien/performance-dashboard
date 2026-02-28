<template>
  <div>
    <div v-if="loading" class="state-container">載入中…</div>
    <div v-else-if="error" class="state-container" style="color: #f87171">
      載入失敗：{{ error }}
    </div>

    <template v-else-if="data">
      <div class="page-header">
        <h1>Team Comparison</h1>
        <p class="page-subtitle">Compare cycle time across teams</p>
      </div>

      <!-- Team Multi-Select -->
      <section class="card selector-card">
        <h3>Select Teams (max 4)</h3>
        <div class="checkbox-group">
          <label
            v-for="(team, teamId) in data.teams"
            :key="teamId"
            class="checkbox-label"
            :class="{ disabled: !selectedTeamIds.includes(teamId) && selectedTeamIds.length >= 4 }"
          >
            <input
              type="checkbox"
              :value="teamId"
              v-model="selectedTeamIds"
              :disabled="!selectedTeamIds.includes(teamId) && selectedTeamIds.length >= 4"
            />
            {{ team.name }}
          </label>
        </div>
      </section>

      <!-- Grouped Bar Chart -->
      <section class="card chart-section">
        <h3>Cycle Time by Phase (p50, days)</h3>
        <div class="chart-wrapper">
          <Bar :data="chartData" :options="chartOptions" />
        </div>
      </section>

      <!-- Summary Table -->
      <section class="card table-section">
        <h3>Summary Comparison</h3>
        <div class="table-wrapper">
          <table class="summary-table">
            <thead>
              <tr>
                <th>Team</th>
                <th>Total Cycle Time p50</th>
                <th>Throughput (30d)</th>
                <th>PRs Merged</th>
                <th>PR Pickup p50</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="teamId in selectedTeamIds" :key="teamId">
                <td>
                  <span
                    class="team-badge"
                    :style="{ background: teamColor(teamId) + '33', color: teamColor(teamId) }"
                  >
                    {{ data.teams[teamId]?.name ?? teamId }}
                  </span>
                </td>
                <td>{{ formatDays(data.teams[teamId]?.aggregated.cycle_time.total?.p50) }}</td>
                <td>{{ data.teams[teamId]?.aggregated.throughput.completed_issues ?? '—' }}</td>
                <td>{{ data.teams[teamId]?.aggregated.pr_metrics?.total_prs_merged ?? '—' }}</td>
                <td>{{ formatHours(data.teams[teamId]?.aggregated.pr_metrics?.pickup_hours?.p50) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { useMetrics } from '../composables/useMetrics.js'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const { data, loading, error } = useMetrics()

const PALETTE = ['#60a5fa', '#34d399', '#f97316', '#a78bfa']

// 預設選前兩個 team
const selectedTeamIds = ref([])

// 當資料載入後初始化選擇
import { watch } from 'vue'
watch(
  data,
  (val) => {
    if (val && selectedTeamIds.value.length === 0) {
      const ids = Object.keys(val.teams)
      selectedTeamIds.value = ids.slice(0, 2)
    }
  },
  { immediate: true },
)

function teamColor(teamId) {
  if (!data.value) return PALETTE[0]
  const ids = Object.keys(data.value.teams)
  const idx = ids.indexOf(teamId)
  return PALETTE[idx % PALETTE.length]
}

const chartData = computed(() => {
  if (!data.value) return { labels: [], datasets: [] }

  const phases = data.value.meta.phases
  const labels = phases.map((p) => p.label)

  const datasets = selectedTeamIds.value.map((teamId, i) => {
    const team = data.value.teams[teamId]
    const ct = team?.aggregated.cycle_time ?? {}
    const values = phases.map((p) => ct[p.id]?.p50 ?? 0)

    return {
      label: team?.name ?? teamId,
      data: values,
      backgroundColor: PALETTE[i % PALETTE.length] + 'cc',
      borderColor: PALETTE[i % PALETTE.length],
      borderWidth: 1,
      borderRadius: 3,
    }
  })

  return { labels, datasets }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: {
        color: '#94a3b8',
        font: { size: 12 },
      },
    },
    tooltip: {
      callbacks: {
        label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}d`,
      },
    },
  },
  scales: {
    x: {
      ticks: { color: '#94a3b8', font: { size: 11 } },
      grid: { color: '#334155' },
    },
    y: {
      ticks: { color: '#94a3b8', font: { size: 11 } },
      grid: { color: '#334155' },
      title: {
        display: true,
        text: 'Days (p50)',
        color: '#94a3b8',
        font: { size: 11 },
      },
    },
  },
}

function formatDays(val) {
  return val != null ? val + 'd' : '—'
}

function formatHours(val) {
  return val != null ? val + 'h' : '—'
}
</script>

<style scoped>
.page-header {
  margin-bottom: 1.25rem;
}

.page-subtitle {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.selector-card {
  margin-bottom: 1rem;
}

.selector-card h3 {
  margin-bottom: 0.75rem;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
}

.checkbox-label.disabled {
  color: var(--text-muted);
  cursor: not-allowed;
}

.checkbox-label input[type='checkbox'] {
  accent-color: var(--accent);
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.checkbox-label.disabled input[type='checkbox'] {
  cursor: not-allowed;
}

.chart-section {
  margin-bottom: 1rem;
}

.chart-section h3 {
  margin-bottom: 1rem;
}

.chart-wrapper {
  height: 300px;
  position: relative;
}

.table-section h3 {
  margin-bottom: 1rem;
}

.table-wrapper {
  overflow-x: auto;
}

.summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.summary-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border);
}

.summary-table td {
  padding: 0.6rem 0.75rem;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-light);
  font-variant-numeric: tabular-nums;
}

.summary-table tbody tr:last-child td {
  border-bottom: none;
}

.team-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.8125rem;
}
</style>
