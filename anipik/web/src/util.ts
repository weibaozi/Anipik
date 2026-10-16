import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { EpisodeStatus, JobPhase } from './api'

type TagType = 'default' | 'success' | 'info' | 'warning' | 'error' | 'primary'

export const episodeStatus: Record<EpisodeStatus, { label: string; type: TagType }> = {
  done: { label: '已下载', type: 'success' },
  downloading: { label: '下载中', type: 'info' },
  queued: { label: '排队中', type: 'primary' },
  failed: { label: '失败', type: 'error' },
  needs_attention: { label: '需处理', type: 'warning' },
  skipped: { label: '跳过', type: 'default' },
}

export const jobPhase: Record<JobPhase, { label: string; type: TagType }> = {
  pending: { label: '等待中', type: 'default' },
  running: { label: '进行中', type: 'info' },
  done: { label: '完成', type: 'success' },
  failed: { label: '失败', type: 'error' },
  needs_attention: { label: '需处理', type: 'warning' },
  cancelled: { label: '已放弃', type: 'default' },
}

// PikPak client sub-phases (Job.state.phase)
export const backendPhase: Record<string, string> = {
  new: '准备中',
  cloud_submitting: '提交云端',
  cloud_waiting: '云端下载',
  local_ready: '准备本地下载',
  local_submitting: '提交本地下载',
  local_waiting: '本地下载',
  done: '完成',
  failed: '失败',
}

export function formatSpeed(bytesPerSecond: number | null | undefined) {
  if (!bytesPerSecond) return ''
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  let value = bytesPerSecond
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function formatTime(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  const diff = (Date.now() - date.getTime()) / 1000
  if (diff > -60 && diff < 60) return diff >= 0 ? '刚刚' : '马上'
  const abs = Math.abs(diff)
  const suffix = diff >= 0 ? '前' : '后'
  if (abs < 3600) return `${Math.round(abs / 60)} 分钟${suffix}`
  if (abs < 86400) return `${Math.round(abs / 3600)} 小时${suffix}`
  return date.toLocaleString('zh-CN', { hour12: false })
}

/** "26年10月" folder style, from a bgm.tv air date like 2026-10-03. */
export function seasonFolder(airDate: string | null | undefined) {
  const match = airDate?.match(/^(\d{4})-(\d{2})/)
  if (!match) return null
  const month = Number(match[2])
  const season = month >= 10 ? 10 : month >= 7 ? 7 : month >= 4 ? 4 : 1
  return `${match[1].slice(2)}年${season}月`
}

/** Call fn now and every `ms` while the component is mounted and the tab is visible. */
export function usePolling(fn: () => Promise<unknown> | unknown, ms: number) {
  const loading = ref(false)
  let timer: number | undefined
  async function tick() {
    if (document.visibilityState === 'visible' && !loading.value) {
      loading.value = true
      try {
        await fn()
      } finally {
        loading.value = false
      }
    }
  }
  onMounted(() => {
    tick()
    timer = window.setInterval(tick, ms)
  })
  onBeforeUnmount(() => window.clearInterval(timer))
  return { refresh: tick, loading }
}

export function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}
