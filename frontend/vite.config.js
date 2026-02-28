import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 若您的 GitHub Pages 路徑不同，請修改此處的 base
// 例如：https://your-org.github.io/performance-dashboard/ → base: '/performance-dashboard/'
// 例如：https://your-custom-domain.com/ → base: '/'
const base = '/performance-dashboard/'

export default defineConfig({
  plugins: [vue()],
  base,
})
