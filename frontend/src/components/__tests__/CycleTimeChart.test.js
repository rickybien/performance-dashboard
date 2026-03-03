import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import CycleTimeChart from '../CycleTimeChart.vue'

// Chart.js 在 happy-dom 環境無法渲染 canvas，mock 掉
vi.mock('vue-chartjs', () => ({
  Bar: {
    name: 'Bar',
    props: ['data', 'options'],
    template: '<canvas class="bar-chart" />',
  },
}))

const PHASES = [
  { id: 'planning', label: 'Planning', color: '#6366f1' },
  { id: 'dev', label: 'Development', color: '#22c55e' },
  { id: 'review', label: 'PR Review', color: '#f59e0b' },
]

function makeProjects(overrides = {}) {
  return {
    'PROJ-A': {
      cycle_time: {
        planning: { count: 10, p50: 0.0, p75: 0.5, p90: 1.0, ...overrides.planning },
        dev: { count: 10, p50: 0.06, p75: 1.0, p90: 2.0, ...overrides.dev },
        review: { count: 8, p50: 0.2, p75: 1.0, p90: 2.0, ...overrides.review },
      },
    },
  }
}

// ============================================================
// filtered p50 優先邏輯（所有 phase 通用）
// ============================================================

describe('CycleTimeChart filtered p50 priority', () => {
  it('dev phase 有 filtered 時使用 filtered.p50', () => {
    const projects = makeProjects({
      dev: {
        count: 10, p50: 0.06,
        filtered: { count: 6, p50: 1.18, excluded_count: 4, threshold_hours: 1.0 },
      },
    })

    const wrapper = mount(CycleTimeChart, {
      props: { projects, phases: PHASES },
    })

    // 取得傳給 Bar 的 data prop
    const barComp = wrapper.findComponent({ name: 'Bar' })
    const chartData = barComp.props('data')
    const devDataset = chartData.datasets.find((d) => d.label === 'Development')

    expect(devDataset).toBeDefined()
    expect(devDataset.data[0]).toBe(1.18)
  })

  it('planning phase 有 filtered 時同樣使用 filtered.p50', () => {
    const projects = makeProjects({
      planning: {
        count: 10, p50: 0.0,
        filtered: { count: 4, p50: 0.85, excluded_count: 6, threshold_hours: 1.0 },
      },
    })

    const wrapper = mount(CycleTimeChart, {
      props: { projects, phases: PHASES },
    })

    const barComp = wrapper.findComponent({ name: 'Bar' })
    const chartData = barComp.props('data')
    const planningDataset = chartData.datasets.find((d) => d.label === 'Planning')

    expect(planningDataset).toBeDefined()
    expect(planningDataset.data[0]).toBe(0.85)
  })

  it('review phase 有 filtered 時同樣使用 filtered.p50', () => {
    const projects = makeProjects({
      review: {
        count: 8, p50: 0.2,
        filtered: { count: 5, p50: 0.65, excluded_count: 3, threshold_hours: 1.0 },
      },
    })

    const wrapper = mount(CycleTimeChart, {
      props: { projects, phases: PHASES },
    })

    const barComp = wrapper.findComponent({ name: 'Bar' })
    const chartData = barComp.props('data')
    const reviewDataset = chartData.datasets.find((d) => d.label === 'PR Review')

    expect(reviewDataset).toBeDefined()
    expect(reviewDataset.data[0]).toBe(0.65)
  })

  it('無 filtered 時 fallback 到 stat.p50', () => {
    const projects = makeProjects()  // 無 filtered

    const wrapper = mount(CycleTimeChart, {
      props: { projects, phases: PHASES },
    })

    const barComp = wrapper.findComponent({ name: 'Bar' })
    const chartData = barComp.props('data')

    const devDataset = chartData.datasets.find((d) => d.label === 'Development')
    expect(devDataset.data[0]).toBe(0.06)

    const planningDataset = chartData.datasets.find((d) => d.label === 'Planning')
    expect(planningDataset.data[0]).toBe(0.0)
  })

  it('filtered.count = 0 時 fallback 到 stat.p50', () => {
    const projects = makeProjects({
      dev: {
        count: 5, p50: 2.5,
        filtered: { count: 0, p50: 0, excluded_count: 5, threshold_hours: 1.0 },
      },
    })

    const wrapper = mount(CycleTimeChart, {
      props: { projects, phases: PHASES },
    })

    const barComp = wrapper.findComponent({ name: 'Bar' })
    const chartData = barComp.props('data')
    const devDataset = chartData.datasets.find((d) => d.label === 'Development')
    expect(devDataset.data[0]).toBe(2.5)
  })
})
