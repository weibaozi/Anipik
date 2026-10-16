import { computed, reactive, ref, watch } from 'vue'
import { api, type Status } from './api'

// App-wide state: backend status (polled by the shell) and theme preference.
export const status = ref<Status | null>(null)
export const statusError = ref<string | null>(null)

export async function refreshStatus() {
  try {
    status.value = await api.status()
    statusError.value = null
  } catch (error) {
    statusError.value = error instanceof Error ? error.message : String(error)
  }
}

export const attentionCount = computed(() => status.value?.jobs.needs_attention ?? 0)
export const activeCount = computed(() => (status.value?.jobs.running ?? 0) + (status.value?.jobs.pending ?? 0))

type ThemePref = 'auto' | 'light' | 'dark'
function readTheme(): ThemePref {
  try {
    const value = localStorage.getItem('anipik.theme')
    return value === 'light' || value === 'dark' ? value : 'auto'
  } catch {
    return 'auto'
  }
}
export const theme = reactive({ pref: readTheme() })
watch(
  () => theme.pref,
  (value) => {
    try {
      localStorage.setItem('anipik.theme', value)
    } catch {
      /* storage unavailable: preference lasts for this tab only */
    }
  },
)
