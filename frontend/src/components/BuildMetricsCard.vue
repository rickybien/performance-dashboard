<template>
  <div>
    <p v-if="!buildMetrics" class="unavailable">Build data not available</p>
    <div v-else>
      <div class="metrics-row">
        <div class="metric-item">
          <div
            class="metric-value"
            :class="successRateClass"
          >
            {{ buildMetrics.success_rate }}%
          </div>
          <div class="metric-label">Success Rate</div>
        </div>
        <div class="metric-item">
          <div class="metric-value">{{ buildMetrics.avg_duration_mins }}m</div>
          <div class="metric-label">Avg Build</div>
        </div>
        <div class="metric-item">
          <div class="metric-value">{{ buildMetrics.total_builds }}</div>
          <div class="metric-label">Total Builds</div>
        </div>
      </div>

      <div class="trend-section">
        <div class="trend-label">Weekly Trend</div>
        <div class="bar-chart">
          <div
            v-for="(val, idx) in buildMetrics.weekly_trend"
            :key="idx"
            class="bar-col"
          >
            <div
              class="bar"
              :style="{ height: barHeight(val) + '%' }"
            ></div>
            <div class="bar-val">{{ val }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  buildMetrics: {
    type: Object,
    default: null,
  },
})

const successRateClass = computed(() => {
  if (!props.buildMetrics) return ''
  const rate = props.buildMetrics.success_rate
  if (rate >= 90) return 'value-good'
  if (rate >= 70) return 'value-warning'
  return 'value-danger'
})

function barHeight(val) {
  if (!props.buildMetrics) return 0
  const max = Math.max(...props.buildMetrics.weekly_trend)
  if (max === 0) return 0
  return Math.round((val / max) * 100)
}
</script>

<style scoped>
.unavailable {
  font-size: 0.875rem;
  color: var(--text-muted);
  padding: 0.5rem 0;
}

.metrics-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding-top: 0.25rem;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 80px;
}

.metric-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.metric-value.value-good {
  color: #34d399;
}

.metric-value.value-warning {
  color: #fbbf24;
}

.metric-value.value-danger {
  color: #f87171;
}

.metric-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.trend-section {
  margin-top: 1rem;
}

.trend-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  height: 56px;
}

.bar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 0.25rem;
  flex: 1;
  height: 100%;
}

.bar {
  width: 100%;
  background: var(--accent);
  border-radius: 3px 3px 0 0;
  min-height: 4px;
  transition: height 0.2s;
}

.bar-val {
  font-size: 0.6875rem;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
