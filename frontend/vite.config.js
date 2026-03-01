import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { createReadStream, existsSync } from 'fs'
import { fileURLToPath } from 'url'

// 若您的 GitHub Pages 路徑不同，請修改此處的 base
// 例如：https://your-org.github.io/performance-dashboard/ → base: '/performance-dashboard/'
// 例如：https://your-custom-domain.com/ → base: '/'
const base = '/performance-dashboard/'
const projectRoot = resolve(fileURLToPath(import.meta.url), '../..')

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'serve-project-data',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const prefix = `${base}data/`
          if (!req.url?.startsWith(prefix)) return next()

          const relative = req.url.slice(prefix.length).split('?')[0]
          const filePath = resolve(projectRoot, 'data', relative)
          const dataDir = resolve(projectRoot, 'data')

          if (filePath.startsWith(dataDir) && existsSync(filePath) && filePath.endsWith('.json')) {
            res.setHeader('Content-Type', 'application/json')
            createReadStream(filePath).pipe(res)
            return
          }
          next()
        })
      },
    },
  ],
  base,
})
