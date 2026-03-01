<template>
  <div class="heatmap-wrapper">
    <table class="heatmap-table">
      <thead>
        <tr>
          <th class="team-col">Team</th>
          <th v-for="phase in phases" :key="phase.id" class="phase-col">
            <span class="phase-dot" :style="{ background: phase.color }"></span>
            {{ phase.label }}
          </th>
          <th class="phase-col total-col">Total</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(teamData, teamId) in teams"
          :key="teamId"
          class="team-row"
          @click="$router.push(`/team/${teamId}`)"
        >
          <td class="team-name">{{ teamData.name }}</td>
          <td
            v-for="phase in phases"
            :key="phase.id"
            class="heatmap-cell"
            :class="cellClass(teamData.aggregated.cycle_time[phase.id])"
            :title="cellTitle(teamData.aggregated.cycle_time[phase.id])"
          >
            {{ formatDays(teamData.aggregated.cycle_time[phase.id]) }}
          </td>
          <td
            class="heatmap-cell total-col"
            :class="cellClass(teamData.aggregated.cycle_time.total)"
            :title="cellTitle(teamData.aggregated.cycle_time.total)"
          >
            {{ formatDays(teamData.aggregated.cycle_time.total) }}
          </td>
        </tr>
      </tbody>
    </table>
    <p class="heatmap-hint">Click a row to drill down → p50 cycle time in days</p>
  </div>
</template>

<script setup>
const props = defineProps({
  teams: { type: Object, required: true },
  phases: { type: Array, required: true },
  thresholds: { type: Object, required: true },
})

function cellClass(stat) {
  if (!stat || stat.count === 0) return 'cell-empty'
  if (stat.p50 < props.thresholds.good) return 'cell-good'
  if (stat.p50 < props.thresholds.warning) return 'cell-warning'
  return 'cell-bad'
}

function cellTitle(stat) {
  if (!stat || stat.count === 0) return 'No data'
  return `p50: ${stat.p50}d  p85: ${stat.p85}d  n=${stat.count}`
}

function formatDays(stat) {
  if (!stat || stat.count === 0) return '—'
  return `${stat.p50}d`
}
</script>

<style scoped>
.heatmap-wrapper {
  overflow-x: auto;
}

.heatmap-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

thead tr {
  border-bottom: 1px solid var(--border);
}

th {
  padding: 0.5rem 0.75rem;
  text-align: center;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.team-col {
  text-align: left;
  min-width: 130px;
}

.phase-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

.team-row {
  cursor: pointer;
  transition: background 0.1s;
}

.team-row:hover td {
  background: var(--bg-card-hover);
}

.team-name {
  padding: 0.6rem 0.75rem;
  font-weight: 500;
  color: var(--text-primary);
  border-right: 1px solid var(--border);
}

.heatmap-cell {
  padding: 0.5rem 0.6rem;
  text-align: center;
  border: 1px solid transparent;
  border-radius: 4px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  margin: 2px;
  min-width: 64px;
}

.cell-good {
  background: var(--heatmap-good);
  color: var(--heatmap-good-text);
}

.cell-warning {
  background: var(--heatmap-warning);
  color: var(--heatmap-warning-text);
}

.cell-bad {
  background: var(--heatmap-bad);
  color: var(--heatmap-bad-text);
}

.cell-empty {
  background: var(--heatmap-empty);
  color: var(--heatmap-empty-text);
}

.total-col {
  border-left: 1px solid var(--border);
}

.heatmap-hint {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}
</style>
