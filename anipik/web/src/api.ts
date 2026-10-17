// Typed client for the anipik FastAPI backend (/api).

export type EpisodeStatus = 'queued' | 'downloading' | 'done' | 'failed' | 'needs_attention' | 'skipped'
export type JobPhase = 'pending' | 'running' | 'done' | 'failed' | 'needs_attention' | 'cancelled'

export interface Binding {
  id?: number
  source_id: number
  source_name?: string
  enabled: boolean
  keywords: string[]
  include: string[]
  exclude: string[]
}

export interface Job {
  id: number
  phase: JobPhase
  progress: number
  message: string | null
  error: string | null
  downloader: string
  destination: string
  url: string
  backend_phase: string | null
  speed: number | null
  files_done: number | null
  files_total: number | null
  created_at: string
  updated_at: string
  finished_at: string | null
  episode: number | null
  release_title: string | null
  subscription: { id: number; name: string; cover_url: string | null } | null
}

export interface Episode {
  number: number
  status: EpisodeStatus
  attempts: number
  release_title: string | null
  source_name: string | null
  updated_at: string
  job: Job | null
}

export interface Metadata {
  bangumi_id: number | null
  original_name: string | null
  cover_url: string | null
  air_date: string | null
  total_episodes: number | null
  summary?: string | null
}

export interface Subscription extends Metadata {
  id: number
  name: string
  enabled: boolean
  save_dir: string | null
  sources: string[]
  counts: Partial<Record<EpisodeStatus, number>>
  latest_done: number | null
  active_jobs: number
  active_progress: number | null
  updated_at: string
}

export interface SubscriptionDetail extends Subscription {
  destination: string | null
  moved?: { from: string; to: string } | null
  bindings: Binding[]
  episodes: Episode[]
}

export interface SubscriptionInput extends Partial<Metadata> {
  name: string
  enabled: boolean
  save_dir: string | null
  bindings: Binding[]
  start_episode?: number | null
}

export interface Source {
  id: number
  name: string
  kind: string
  config: Record<string, string>
  enabled: boolean
  subscriptions: number
}

export interface PreviewItem {
  title: string
  episode: number | null
  batch: boolean
  matched: boolean
  group: string | null
  published: string | null
  page_link: string | null
  status: EpisodeStatus | null
}

export interface Preview {
  url: string | null
  count: number
  items: PreviewItem[]
}

export interface BangumiItem {
  id: number
  name: string
  name_cn: string
  cover_url: string | null
  air_date: string | null
  total_episodes: number | null
  summary?: string | null
}

export interface Status {
  scheduler: {
    running: boolean
    scanning?: boolean
    last_scan_at?: number | null
    last_scan_queued?: number
    last_scan_error?: string | null
    next_scan_at?: number | null
    backends?: Record<string, { ok: boolean; error: string | null; at: number }>
  }
  scheduler_in_process: boolean
  downloader: string
  jobs: Partial<Record<JobPhase, number>>
  subscriptions: number
  db: string
  server: { host?: string; port?: number; can_restart: boolean; addresses: string[] }
}

export interface Health {
  downloader: string
  ok: boolean
  version?: string
  modules?: Record<string, boolean | string>
  error?: string
  client?: { exe: string | null; auto_start: boolean; process_running: boolean; port_open: boolean }
}

export type Settings = Record<string, any>

export interface DiscordStatus {
  status: { state: string; user: string | null; error: string | null; commands?: boolean; since?: string | null }
  outbox: {
    pending: number
    failed: { message: string; error: string | null }[]
    last: { message: string; sent: boolean; error: string | null; attempts: number } | null
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 204) return undefined as T
  const text = await response.text()
  const data = text ? JSON.parse(text) : undefined
  if (!response.ok) {
    const detail = data?.detail
    const message = Array.isArray(detail)
      ? detail.map((d: any) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
      : detail || response.statusText
    throw new ApiError(response.status, message)
  }
  return data as T
}

export const api = {
  status: () => request<Status>('GET', '/status'),
  scan: () => request<{ requested: boolean }>('POST', '/scan'),
  restartApp: () => request<{ restarting: boolean }>('POST', '/app/restart'),

  subscriptions: () => request<Subscription[]>('GET', '/subscriptions'),
  subscription: (id: number) => request<SubscriptionDetail>('GET', `/subscriptions/${id}`),
  createSubscription: (body: SubscriptionInput) => request<SubscriptionDetail>('POST', '/subscriptions', body),
  updateSubscription: (id: number, body: Partial<SubscriptionInput> & { move_files?: boolean }) =>
    request<SubscriptionDetail>('PATCH', `/subscriptions/${id}`, body),
  deleteSubscription: (id: number) => request<void>('DELETE', `/subscriptions/${id}`),
  markEpisodes: (id: number, numbers: number[], status: 'done' | 'skipped' | 'delete') =>
    request<SubscriptionDetail>('POST', `/subscriptions/${id}/episodes`, { numbers, status }),

  sources: () => request<Source[]>('GET', '/sources'),
  createSource: (body: Omit<Source, 'id' | 'subscriptions'>) => request<Source>('POST', '/sources', body),
  updateSource: (id: number, body: Partial<Source>) => request<Source>('PATCH', `/sources/${id}`, body),
  deleteSource: (id: number) => request<void>('DELETE', `/sources/${id}`),
  preview: (body: {
    source_id?: number
    kind?: string
    config?: Record<string, string>
    keywords: string[]
    include?: string[]
    exclude?: string[]
    subscription_id?: number
  }) => request<Preview>('POST', '/sources/preview', body),

  jobs: (view: 'active' | 'attention' | 'history' | 'all', limit = 100) =>
    request<Job[]>('GET', `/jobs?view=${view}&limit=${limit}`),
  jobAction: (id: number, action: 'retry' | 'retry_from_scratch' | 'mark_done' | 'abandon') =>
    request<Job>('POST', `/jobs/${id}`, { action }),

  settings: () => request<Settings>('GET', '/settings'),
  updateSettings: (body: Settings) => request<Settings>('PATCH', '/settings', body),
  health: () => request<Health>('GET', '/downloader/health'),
  startDownloader: () => request<{ message: string }>('POST', '/downloader/start'),
  restartDownloader: () => request<{ message: string }>('POST', '/downloader/restart'),
  discordStatus: () => request<DiscordStatus>('GET', '/notify/discord'),
  discordTest: () => request<{ queued: boolean }>('POST', '/notify/discord/test'),

  bangumiSearch: (q: string) => request<BangumiItem[]>('GET', `/bangumi/search?q=${encodeURIComponent(q)}`),
  bangumiSubject: (id: number) => request<BangumiItem>('GET', `/bangumi/subject/${id}`),
}
