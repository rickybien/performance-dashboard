<template>
  <div>
    <!-- Loading / Error -->
    <div v-if="loading" class="state-container">載入中…</div>
    <div v-else-if="error" class="state-container" style="color: #f87171">
      載入失敗：{{ error }}
    </div>

    <template v-else-if="data">
      <!-- Summary Cards -->
      <section class="summary-section">
        <div class="card summary-card">
          <div class="summary-value">{{ data.summary.total_completed_issues }}</div>
          <div class="summary-label">Completed Issues (90d)</div>
        </div>
        <div class="card summary-card">
          <div class="summary-value">
            {{ data.summary.avg_cycle_time_days != null ? data.summary.avg_cycle_time_days + 'd' : '—' }}
          </div>
          <div class="summary-label">Avg Cycle Time</div>
        </div>
        <div class="card summary-card">
          <div class="summary-value">{{ Object.keys(data.teams).length }}</div>
          <div class="summary-label">Teams Tracked</div>
        </div>
        <div class="card summary-card">
          <div class="summary-value muted">{{ formatDate(data.period.end) }}</div>
          <div class="summary-label">Data as of</div>
        </div>
        <div class="card summary-card">
          <div class="summary-value">{{ data.summary.total_prs_merged ?? '—' }}</div>
          <div class="summary-label">PRs Merged (90d)</div>
        </div>
        <div class="card summary-card">
          <div class="summary-value">
            {{ data.summary.avg_pr_pickup_hours != null ? data.summary.avg_pr_pickup_hours + 'h' : '—' }}
          </div>
          <div class="summary-label">PR Pickup p50</div>
        </div>
      </section>

      <!-- Heatmap -->
      <section class="card heatmap-section">
        <div class="section-header">
          <h2>Cycle Time Heatmap</h2>
          <div class="legend">
            <span class="legend-item good">≤ {{ data.meta.thresholds.good }}d</span>
            <span class="legend-item warning">≤ {{ data.meta.thresholds.warning }}d</span>
            <span class="legend-item bad">&gt; {{ data.meta.thresholds.warning }}d</span>
          </div>
        </div>
        <HeatmapTable
          :teams="data.teams"
          :phases="data.meta.phases"
          :thresholds="data.meta.thresholds"
        />
      </section>
    </template>
  </div>
</template>

<script setup>
import { useMetrics } from '../composables/useMetrics.js'
import HeatmapTable from '../components/HeatmapTable.vue'

const { data, loading, error } = useMetrics()

function formatDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('zh-TW', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
</script>

<style scoped>
.summary-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.summary-value.muted {
  font-size: 1rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.summary-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.heatmap-section {
  margin-bottom: 1.25rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.legend {
  display: flex;
  gap: 0.5rem;
}

.legend-item {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-weight: 600;
}

.legend-item.good {
  background: var(--heatmap-good);
  color: var(--heatmap-good-text);
}

.legend-item.warning {
  background: var(--heatmap-warning);
  color: var(--heatmap-warning-text);
}

.legend-item.bad {
  background: var(--heatmap-bad);
  color: var(--heatmap-bad-text);
}
</style>
