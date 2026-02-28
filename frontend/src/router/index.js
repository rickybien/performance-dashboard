import { createRouter, createWebHashHistory } from 'vue-router'
import OverviewDashboard from '../views/OverviewDashboard.vue'
import TeamDrilldown from '../views/TeamDrilldown.vue'
import Comparison from '../views/Comparison.vue'

const routes = [
  {
    path: '/',
    name: 'overview',
    component: OverviewDashboard,
  },
  {
    path: '/team/:teamId',
    name: 'team',
    component: TeamDrilldown,
    props: true,
  },
  {
    path: '/comparison',
    name: 'comparison',
    component: Comparison,
  },
]

const router = createRouter({
  // GitHub Pages 靜態部署使用 hash history，不需要 server 配置
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
