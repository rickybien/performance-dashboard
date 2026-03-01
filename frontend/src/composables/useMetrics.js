import { ref } from 'vue'

let cached = null

/**
 * 載入並解析 dashboard.json。
 * 使用模組級快取，整個 SPA 生命週期只 fetch 一次。
 */
export function useMetrics() {
  const data = ref(null)
  const loading = ref(true)
  const error = ref(null)

  if (cached) {
    data.value = cached
    loading.value = false
    return { data, loading, error }
  }

  const baseUrl = import.meta.env.BASE_URL
  const url = `${baseUrl}data/latest/dashboard.json?_=${Date.now()}`

  fetch(url)
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    })
    .then((json) => {
      cached = json
      data.value = json
      loading.value = false
    })
    .catch((e) => {
      error.value = e.message
      loading.value = false
    })

  return { data, loading, error }
}
