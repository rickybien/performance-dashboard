import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import HeatmapTable from '../HeatmapTable.vue'

// 最簡路由，避免 <router-link> 報錯
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div/>' } }],
})

const THRESHOLDS = { good: 2, warning: 5 }

// ============================================================
// 輔助函式：提取元件的純邏輯（直接測試邏輯，不透過 DOM）
// ============================================================

// 因為 formatDays / cellClass / cellTitle 是內部函式，我們透過 mount 後
// 呼叫 vm.exposed 或直接對 DOM 結果做斷言。
// 這裡用輕量 wrapper 封裝邏輯供直接測試。

function makeWrapper(teamsData) {
  return mount(HeatmapTable, {
    global: { plugins: [router] },
    props: {
      teams: teamsData,
      phases: [{ id: 'planning', label: 'Planning', color: '#888' }],
      thresholds: THRESHOLDS,
    },
  })
}

// ============================================================
// formatDays 邏輯
// ============================================================

describe('HeatmapTable formatDays', () => {
  it('stat 為 null 時顯示 —', () => {
    const wrapper = makeWrapper({
      t1: { name: 'T1', aggregated: { cycle_time: { planning: null, total: null } } },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].text()).toBe('—')
  })

  it('stat.count = 0 時顯示 —', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: { cycle_time: { planning: { count: 0, p50: 0, p75: 0, p90: 0 }, total: null } },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].text()).toBe('—')
  })

  it('有 filtered.count > 0 時顯示 filtered.p50', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: {
              count: 8, p50: 0.06, p75: 0.2, p90: 0.5,
              filtered: { count: 5, p50: 1.18, p75: 2.0, p90: 3.0, excluded_count: 3, threshold_hours: 1.0 },
            },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].text()).toBe('1.18d')
  })

  it('無 filtered 時顯示 stat.p50', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: { count: 5, p50: 2.5, p75: 3.0, p90: 4.0 },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].text()).toBe('2.5d')
  })

  it('filtered.count = 0 時 fallback 到 stat.p50', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: {
              count: 3, p50: 0.5, p75: 0.8, p90: 1.0,
              filtered: { count: 0, p50: 0, p75: 0, p90: 0, excluded_count: 3, threshold_hours: 1.0 },
            },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].text()).toBe('0.5d')
  })
})

// ============================================================
// cellClass 邏輯
// ============================================================

describe('HeatmapTable cellClass', () => {
  it('filtered.p50 < good → cell-good', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: {
              count: 8, p50: 6.0,  // 超過 warning，但 filtered 在 good 範圍
              filtered: { count: 5, p50: 1.5, excluded_count: 3, threshold_hours: 1.0 },
            },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].classes()).toContain('cell-good')
  })

  it('無 filtered，原始 p50 >= bad → cell-bad', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: { count: 3, p50: 7.0, p75: 9.0, p90: 10.0 },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].classes()).toContain('cell-bad')
  })
})

// ============================================================
// cellTitle 邏輯
// ============================================================

describe('HeatmapTable cellTitle', () => {
  it('有 filtered 時 title 包含 pass-through 資訊', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: {
              count: 8, p50: 0.06, p75: 0.2, p90: 0.5,
              filtered: { count: 5, p50: 1.18, excluded_count: 3, threshold_hours: 1.0 },
            },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    const title = cells[0].attributes('title')
    expect(title).toContain('filtered')
    expect(title).toContain('1.18d')
    expect(title).toContain('pass-through')
    expect(title).toContain('3')
  })

  it('無 filtered 時 title 顯示標準 p50/p75/p90', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: {
          cycle_time: {
            planning: { count: 5, p50: 2.5, p75: 3.0, p90: 4.0 },
            total: null,
          },
        },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    const title = cells[0].attributes('title')
    expect(title).toContain('p50: 2.5d')
    expect(title).toContain('p75: 3d')
    expect(title).toContain('n=5')
  })

  it('無資料時 title 為 No data', () => {
    const wrapper = makeWrapper({
      t1: {
        name: 'T1',
        aggregated: { cycle_time: { planning: null, total: null } },
      },
    })
    const cells = wrapper.findAll('.heatmap-cell')
    expect(cells[0].attributes('title')).toBe('No data')
  })
})
