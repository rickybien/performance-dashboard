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
        <div class="range-buttons">
          <button
            v-for="opt in rangeOptions"
            :key="opt"
            :class="['range-btn', { active: trendRange === opt }]"
            @click="trendRange = opt"
          >{{ opt }}W</button>
        </div>
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
            :weeks="slicedWeeks"
            :throughput="slicedThroughput"
            :cycle-time-p50="slicedCycleTimeP50"
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
          (p75: {{ bottleneck.p75 }}d, p90: {{ bottleneck.p90 }}d, n={{ bottleneck.count }})
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

      <!-- Dev Source Info -->
      <section v-if="devSourceStats && devSourceStats.total > 0" class="card" style="margin-top: 1rem">
        <h3>Development 數據來源</h3>
        <ul class="dev-source-list">
          <li>Jira status 時間：<strong>{{ devSourceStats.jira_count }}</strong> 筆</li>
          <li v-if="devSourceStats.github_count > 0">
            GitHub commit 時間補充：<strong>{{ devSourceStats.github_count }}</strong> 筆
          </li>
        </ul>
      </section>

      <!-- Pass-Through 過濾統計（所有 active phase） -->
      <section v-if="filteredPhaseStats.length" class="card" style="margin-top: 1rem">
        <h3>Pass-Through 過濾統計</h3>
        <p class="chart-subtitle">
          排除停留 &lt; {{ filteredPhaseStats[0]?.threshold_hours }}h 的 issue（Jira 批次拖票），還原各 phase 真實等待時間
        </p>
        <table class="filter-table">
          <thead>
            <tr>
              <th>Phase</th>
              <th class="num-col">原始 p50</th>
              <th class="num-col">過濾後 p50</th>
              <th class="num-col">排除筆數</th>
              <th class="num-col">n (過濾後)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredPhaseStats" :key="s.id">
              <td>
                <span class="phase-badge" :style="{ background: s.color + '33', color: s.color }">
                  {{ s.label }}
                </span>
              </td>
              <td class="num-col muted">{{ s.raw_p50 }}d</td>
              <td class="num-col emphasized">{{ s.filtered_p50 }}d</td>
              <td class="num-col">
                {{ s.excluded_count }} 筆
                <span class="muted">({{ s.excluded_pct }}%)</span>
              </td>
              <td class="num-col muted">{{ s.filtered_count }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Phase Insights -->
      <section v-if="phaseInsights.length" class="card" style="margin-top: 1rem">
        <h3>Phase Insights</h3>
        <ul class="insights-list">
          <li v-for="insight in phaseInsights" :key="insight.phase_id" class="insight-item">
            <span class="phase-badge" :style="{ background: insight.color + '33', color: insight.color }">
              {{ insight.label }}
            </span>
            p50 {{ insight.p50 }}d —
            {{ insight.pass_through_count }}/{{ insight.total_in_phase }}
            ({{ insight.pass_through_pct }}%) resolved issues 停留 &lt; 1 min
            <template v-if="insight.pass_through_pct >= 50">
              — 可能為 Jira 自動化穿越
            </template>
          </li>
        </ul>
      </section>

      <!-- PR Metrics -->
      <section class="card" style="margin-top: 1rem">
        <h3>PR Metrics</h3>
        <PrMetricsCard :pr-metrics="currentAggregated?.pr_metrics ?? null" />
      </section>

      <!-- Build Metrics（只在有資料時顯示） -->
      <section v-if="currentAggregated?.build_metrics" class="card" style="margin-top: 1rem">
        <h3>Build Metrics</h3>
        <BuildMetricsCard :build-metrics="currentAggregated.build_metrics" />
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
const trendRange = ref(12)

// 切換 team 時清空 project 選擇
watch(selectedTeamId, () => { selectedProjectKey.value = '' })

const currentTeam = computed(() =>
  data.value ? data.value.teams[selectedTeamId.value] : null,
)

const teamTrend = computed(() =>
  data.value ? data.value.trends[selectedTeamId.value] : null,
)

const rangeOptions = computed(() => {
  const total = teamTrend.value?.weeks?.length ?? 0
  return [4, 8, 12].filter(n => n <= total)
})

const slicedWeeks = computed(() => {
  const weeks = teamTrend.value?.weeks ?? []
  return weeks.slice(-trendRange.value)
})

const slicedThroughput = computed(() => {
  const arr = teamTrend.value?.throughput ?? []
  return arr.slice(-trendRange.value)
})

const slicedCycleTimeP50 = computed(() => {
  const arr = teamTrend.value?.cycle_time_p50 ?? []
  return arr.slice(-trendRange.value)
})

// 依選擇的時間區間決定讀取 by_window 或 aggregated
const currentAggregated = computed(() => {
  if (!currentTeam.value) return null
  const maxWeeks = teamTrend.value?.weeks?.length ?? 12
  if (trendRange.value >= maxWeeks) return currentTeam.value.aggregated
  return currentTeam.value.by_window?.[String(trendRange.value)]
    ?? currentTeam.value.aggregated
})

// 依選擇的 project 篩選，或顯示所有 project；4W/8W 時使用 windowed cycle_time
const displayProjects = computed(() => {
  if (!currentTeam.value) return {}
  let projects = currentTeam.value.projects
  const maxWeeks = teamTrend.value?.weeks?.length ?? 12
  if (trendRange.value < maxWeeks) {
    const wp = currentTeam.value.by_window?.[String(trendRange.value)]?.projects
    if (wp) {
      const merged = {}
      for (const [pk, proj] of Object.entries(projects)) {
        merged[pk] = { ...proj, cycle_time: wp[pk]?.cycle_time ?? proj.cycle_time }
      }
      projects = merged
    }
  }
  if (selectedProjectKey.value && projects[selectedProjectKey.value]) {
    return { [selectedProjectKey.value]: projects[selectedProjectKey.value] }
  }
  return projects
})

// 找出 p50 最高的 phase（排除 total）
const bottleneck = computed(() => {
  if (!currentAggregated.value || !data.value) return null

  const ct = currentAggregated.value.cycle_time
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
  currentAggregated.value?.bottleneck_issues ?? [],
)

const phaseInsights = computed(() => {
  const raw = currentAggregated.value?.phase_insights ?? []
  const phases = data.value?.meta.phases ?? []
  const ct = currentAggregated.value?.cycle_time ?? {}
  return raw.map(insight => {
    const phase = phases.find(p => p.id === insight.phase_id)
    const stat = ct[insight.phase_id]
    return {
      ...insight,
      label: phase?.label ?? insight.phase_id,
      color: phase?.color ?? '#888',
      p50: stat?.p50 ?? 0,
    }
  })
})

const devSourceStats = computed(() =>
  currentAggregated.value?.dev_source_stats ?? null,
)

const filteredPhaseStats = computed(() => {
  if (!currentAggregated.value || !data.value) return []
  const ct = currentAggregated.value.cycle_time
  const phases = data.value.meta.phases
  return phases
    .filter(phase => ct[phase.id]?.filtered)
    .map(phase => {
      const stat = ct[phase.id]
      const f = stat.filtered
      return {
        id: phase.id,
        label: phase.label,
        color: phase.color,
        raw_p50: stat.p50,
        raw_count: stat.count,
        filtered_p50: f.p50,
        filtered_count: f.count,
        excluded_count: f.excluded_count,
        excluded_pct: stat.count > 0 ? Math.round(f.excluded_count / stat.count * 100) : 0,
        threshold_hours: f.threshold_hours,
      }
    })
})

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

.range-buttons {
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
  flex-shrink: 0;
}

.range-btn {
  padding: 0.2rem 0.55rem;
  font-size: 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--border-color, #e5e7eb);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.range-btn:hover {
  background: var(--hover-bg, #f3f4f6);
  color: var(--text-primary);
}

.range-btn.active {
  background: var(--accent, #3b82f6);
  color: #fff;
  border-color: var(--accent, #3b82f6);
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

.insights-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.insight-item {
  font-size: 0.8125rem;
  color: var(--text-primary);
  line-height: 1.6;
}

.dev-source-list {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-primary);
  line-height: 1.6;
}

.filter-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  margin-top: 0.75rem;
}

.filter-table th,
.filter-table td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
}

.filter-table th {
  font-weight: 600;
  color: var(--text-muted);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.num-col {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.emphasized {
  font-weight: 700;
  color: var(--text-primary);
}
</style>
