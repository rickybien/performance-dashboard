<template>
  <div>
    <div v-if="loading" class="state-container">載入中…</div>
    <div v-else-if="error" class="state-container" style="color: #f87171">
      載入失敗：{{ error }}
    </div>

    <template v-else-if="data">
      <div class="drilldown-header">
        <router-link to="/" class="back-link">← Overview</router-link>
        <h1>{{ currentTeam?.name ?? teamId }}</h1>
      </div>

      <!-- Team / Project Selector -->
      <TeamSelector
        :teams="data.teams"
        v-model:teamId="selectedTeamId"
        v-model:projectKey="selectedProjectKey"
      />

      <div class="charts-grid">
        <!-- Cycle Time Breakdown -->
        <section class="card chart-card">
          <h3>Cycle Time Breakdown (p50)</h3>
          <p class="chart-subtitle">Stacked by phase, per project</p>
          <CycleTimeChart
            :projects="displayProjects"
            :phases="data.meta.phases"
          />
        </section>

        <!-- Throughput Trend -->
        <section class="card chart-card">
          <h3>Weekly Throughput Trend</h3>
          <p class="chart-subtitle">Completed issues + cycle time p50</p>
          <ThroughputChart
            :weeks="teamTrend?.weeks ?? []"
            :throughput="teamTrend?.throughput ?? []"
            :cycle-time-p50="teamTrend?.cycle_time_p50 ?? []"
          />
        </section>
      </div>

      <!-- Bottleneck Highlight -->
      <section v-if="bottleneck" class="card bottleneck-card">
        <h3>Bottleneck</h3>
        <p class="bottleneck-content">
          <span class="phase-badge" :style="{ background: bottleneck.color + '33', color: bottleneck.color }">
            {{ bottleneck.label }}
          </span>
          is the slowest phase with p50
          <strong>{{ bottleneck.p50 }}d</strong>
          (p85: {{ bottleneck.p85 }}d, n={{ bottleneck.count }})
        </p>
      </section>

      <!-- Bottleneck Issues -->
      <section v-if="bottleneckIssues.length" class="card" style="margin-top: 1rem">
        <h3>Slowest Issues in {{ bottleneck.label }}</h3>
        <table class="issues-table">
          <thead>
            <tr>
              <th>Issue</th>
              <th>Summary</th>
              <th>Epic</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="issue in bottleneckIssues" :key="issue.key">
              <td><a :href="issue.url" target="_blank" rel="noopener">{{ issue.key }}</a></td>
              <td class="cell-summary">{{ issue.summary }}</td>
              <td>
                <a v-if="issue.parent_key" :href="parentUrl(issue)" target="_blank" rel="noopener">
                  {{ issue.parent_summary || issue.parent_key }}
                </a>
                <span v-else class="muted">—</span>
              </td>
              <td>{{ issue.phase_duration_days }}d</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- PR Metrics -->
      <section class="card" style="margin-top: 1rem">
        <h3>PR Metrics</h3>
        <PrMetricsCard :pr-metrics="currentTeam?.aggregated.pr_metrics ?? null" />
      </section>

      <!-- Build Metrics（只在有資料時顯示） -->
      <section v-if="currentTeam?.aggregated.build_metrics" class="card" style="margin-top: 1rem">
        <h3>Build Metrics</h3>
        <BuildMetricsCard :build-metrics="currentTeam.aggregated.build_metrics" />
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useMetrics } from '../composables/useMetrics.js'
import TeamSelector from '../components/TeamSelector.vue'
import CycleTimeChart from '../components/CycleTimeChart.vue'
import ThroughputChart from '../components/ThroughputChart.vue'
import PrMetricsCard from '../components/PrMetricsCard.vue'
import BuildMetricsCard from '../components/BuildMetricsCard.vue'

const props = defineProps({
  teamId: { type: String, required: true },
})

const { data, loading, error } = useMetrics()

const selectedTeamId = ref(props.teamId)
const selectedProjectKey = ref('')

// 切換 team 時清空 project 選擇
watch(selectedTeamId, () => { selectedProjectKey.value = '' })

const currentTeam = computed(() =>
  data.value ? data.value.teams[selectedTeamId.value] : null,
)

const teamTrend = computed(() =>
  data.value ? data.value.trends[selectedTeamId.value] : null,
)

// 依選擇的 project 篩選，或顯示所有 project
const displayProjects = computed(() => {
  if (!currentTeam.value) return {}
  const projects = currentTeam.value.projects
  if (selectedProjectKey.value && projects[selectedProjectKey.value]) {
    return { [selectedProjectKey.value]: projects[selectedProjectKey.value] }
  }
  return projects
})

// 找出 p50 最高的 phase（排除 total）
const bottleneck = computed(() => {
  if (!currentTeam.value || !data.value) return null

  const ct = currentTeam.value.aggregated.cycle_time
  const phases = data.value.meta.phases

  let maxPhase = null
  let maxP50 = 0

  for (const phase of phases) {
    const stat = ct[phase.id]
    if (stat && stat.count > 0 && stat.p50 > maxP50) {
      maxP50 = stat.p50
      maxPhase = { ...phase, ...stat }
    }
  }

  return maxPhase
})

const bottleneckIssues = computed(() =>
  currentTeam.value?.aggregated.bottleneck_issues ?? [],
)

function parentUrl(issue) {
  // 從 issue.url 推導 base，替換 issue key 為 parent key
  const base = issue.url.substring(0, issue.url.lastIndexOf('/') + 1)
  return base + issue.parent_key
}
</script>

<style scoped>
.drilldown-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.back-link {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 0.875rem;
  transition: color 0.15s;
}

.back-link:hover {
  color: var(--text-primary);
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 1.25rem;
}

@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}

.chart-card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.chart-subtitle {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.bottleneck-card {
  margin-top: 1rem;
}

.bottleneck-content {
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.phase-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.8125rem;
  margin-right: 0.25rem;
}

.issues-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  margin-top: 0.75rem;
}

.issues-table th,
.issues-table td {
  padding: 0.5rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.issues-table th {
  font-weight: 600;
  color: var(--text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.issues-table a {
  color: var(--link-color, #3b82f6);
  text-decoration: none;
}

.issues-table a:hover {
  text-decoration: underline;
}

.cell-summary {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  color: var(--text-muted);
}
</style>
