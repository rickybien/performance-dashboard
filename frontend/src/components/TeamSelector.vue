<template>
  <div class="selector-row">
    <div class="selector-group">
      <label class="selector-label" :for="teamSelectId">Team</label>
      <select :id="teamSelectId" :value="teamId" @change="$emit('update:teamId', $event.target.value)">
        <option v-for="(teamData, tid) in teams" :key="tid" :value="tid">
          {{ teamData.name }}
        </option>
      </select>
    </div>

    <div v-if="projectKeys.length > 1" class="selector-group">
      <label class="selector-label" :for="projSelectId">Project</label>
      <select :id="projSelectId" :value="projectKey" @change="$emit('update:projectKey', $event.target.value)">
        <option value="">All Projects</option>
        <option v-for="pk in projectKeys" :key="pk" :value="pk">{{ pk }}</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  teams: { type: Object, required: true },
  teamId: { type: String, required: true },
  projectKey: { type: String, default: '' },
})

defineEmits(['update:teamId', 'update:projectKey'])

const teamSelectId = 'team-select'
const projSelectId = 'project-select'

const projectKeys = computed(() =>
  props.teamId && props.teams[props.teamId]
    ? Object.keys(props.teams[props.teamId].projects)
    : [],
)
</script>

<style scoped>
.selector-row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  align-items: flex-end;
}

.selector-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.selector-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
