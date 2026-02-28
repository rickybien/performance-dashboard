<template>
  <div>
    <p v-if="!prMetrics" class="unavailable">PR data not available</p>
    <div v-else class="metrics-row">
      <div class="metric-item">
        <div class="metric-value">{{ prMetrics.total_prs_merged }}</div>
        <div class="metric-label">PRs Merged</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">
          {{ prMetrics.pickup_hours.count > 0 ? prMetrics.pickup_hours.p50 + 'h' : '—' }}
        </div>
        <div class="metric-label">Pickup p50</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">
          {{ prMetrics.merge_time_hours.count > 0 ? prMetrics.merge_time_hours.p50 + 'h' : '—' }}
        </div>
        <div class="metric-label">Merge Time p50</div>
      </div>
      <div class="metric-item">
        <div
          class="metric-value"
          :class="{ 'value-danger': prMetrics.large_pr_pct >= 30 }"
        >
          {{ prMetrics.large_pr_pct }}%
        </div>
        <div class="metric-label">Large PRs</div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  prMetrics: {
    type: Object,
    default: null,
  },
})
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

.metric-value.value-danger {
  color: #f87171;
}

.metric-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
