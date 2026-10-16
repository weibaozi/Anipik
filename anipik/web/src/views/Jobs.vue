<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert,
  NBadge,
  NButton,
  NDataTable,
  NEmpty,
  NProgress,
  NSpace,
  NTab,
  NTabs,
  NTag,
  useDialog,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { api, type Job } from '../api'
import Cover from '../components/Cover.vue'
import { attentionCount, refreshStatus } from '../store'
import { backendPhase, errorText, formatSpeed, formatTime, jobPhase, usePolling } from '../util'

type View = 'active' | 'attention' | 'history'
const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const view = ref<View>((['active', 'attention', 'history'] as View[]).includes(route.query.view as View) ? (route.query.view as View) : 'active')
const jobs = ref<Job[] | null>(null)

async function load() {
  try {
    jobs.value = await api.jobs(view.value, view.value === 'history' ? 200 : 100)
  } catch (error) {
    if (jobs.value === null) message.error(errorText(error))
  }
}
const { refresh } = usePolling(load, 2000)
watch(view, (value) => {
  jobs.value = null
  router.replace({ query: { view: value } })
  refresh()
})

function label(job: Job) {
  return job.subscription ? `${job.subscription.name} 第${job.episode}集` : `任务 ${job.id}`
}
function stage(job: Job) {
  return backendPhase[job.backend_phase ?? ''] ?? job.backend_phase ?? jobPhase[job.phase].label
}

async function act(job: Job, action: 'retry' | 'retry_from_scratch' | 'mark_done' | 'abandon') {
  try {
    await api.jobAction(job.id, action)
    message.success({ retry: '已恢复', retry_from_scratch: '已从头重试', mark_done: '已标记完成', abandon: '已放弃' }[action])
    refresh()
    refreshStatus()
  } catch (error) {
    message.error(errorText(error))
  }
}
function confirmFromScratch(job: Job) {
  dialog.warning({
    title: '从头重试',
    content:
      '会丢弃这个任务的进度记录并重新提交。如果 PikPak 里其实已经有这个任务，可能产生重复下载——请先在 PikPak 客户端里确认。',
    positiveText: '从头重试',
    negativeText: '取消',
    onPositiveClick: () => act(job, 'retry_from_scratch'),
  })
}

const historyColumns = computed<DataTableColumns<Job>>(() => [
  {
    title: '番剧',
    key: 'subscription',
    render: (row) =>
      row.subscription
        ? h('a', { class: 'link', onClick: () => router.push(`/sub/${row.subscription!.id}`) }, label(row))
        : label(row),
  },
  {
    title: '结果',
    key: 'phase',
    width: 90,
    render: (row) => h(NTag, { size: 'small', bordered: false, type: jobPhase[row.phase].type }, () => jobPhase[row.phase].label),
  },
  { title: '说明', key: 'error', ellipsis: { tooltip: true }, render: (row) => row.error || row.message || '' },
  { title: '保存到', key: 'destination', ellipsis: { tooltip: true } },
  { title: '时间', key: 'finished_at', width: 120, render: (row) => formatTime(row.finished_at || row.updated_at) },
])
</script>

<template>
  <div class="page">
    <div class="page-header"><h1>下载任务</h1></div>
    <n-tabs v-model:value="view" type="line">
      <n-tab name="active">进行中</n-tab>
      <n-tab name="attention">
        <span class="tab">需要处理 <n-badge v-if="attentionCount" :value="attentionCount" type="warning" /></span>
      </n-tab>
      <n-tab name="history">历史</n-tab>
    </n-tabs>

    <div class="body">
      <template v-if="jobs === null" />
      <n-empty
        v-else-if="!jobs.length"
        :description="{ active: '没有进行中的下载', attention: '没有需要处理的任务', history: '还没有下载记录' }[view]"
        style="margin-top: 60px"
      />

      <template v-else-if="view === 'history'">
        <n-data-table size="small" :columns="historyColumns" :data="jobs" :bordered="false" :row-key="(r: Job) => r.id" />
      </template>

      <div v-else class="list">
        <div v-for="job in jobs" :key="job.id" class="job">
          <cover :src="job.subscription?.cover_url" :name="job.subscription?.name ?? '?'" class="thumb" :radius="6" />
          <div class="job-body">
            <div class="job-title">
              <router-link v-if="job.subscription" :to="`/sub/${job.subscription.id}`" class="link">{{ label(job) }}</router-link>
              <span v-else>{{ label(job) }}</span>
              <n-tag size="small" :bordered="false" :type="jobPhase[job.phase].type">{{ job.phase === 'running' ? stage(job) : jobPhase[job.phase].label }}</n-tag>
            </div>
            <div class="muted release">{{ job.release_title }}</div>

            <template v-if="view === 'active'">
              <n-progress
                type="line"
                :percentage="job.progress"
                :processing="job.phase === 'running'"
                indicator-placement="inside"
                :height="14"
                style="margin: 10px 0 6px"
              />
              <div class="meta">
                <span>{{ job.message || (job.phase === 'pending' ? '等待空闲下载位' : '') }}</span>
                <span v-if="job.speed">{{ formatSpeed(job.speed) }}</span>
                <span v-if="job.files_total">文件 {{ job.files_done }}/{{ job.files_total }}</span>
                <span class="mono">{{ job.destination }}</span>
              </div>
              <n-alert v-if="job.error" type="warning" :show-icon="false" class="err">{{ job.error }}</n-alert>
            </template>

            <template v-else>
              <n-alert type="warning" :show-icon="false" class="err">
                <div>{{ job.error }}</div>
                <div class="muted small">卡在：{{ stage(job) }} · {{ formatTime(job.updated_at) }}</div>
              </n-alert>
              <n-space :size="8" style="margin-top: 10px">
                <n-button size="small" type="primary" @click="act(job, 'retry')">继续</n-button>
                <n-button size="small" @click="confirmFromScratch(job)">从头重试</n-button>
                <n-button size="small" type="success" secondary @click="act(job, 'mark_done')">我已确认下载完成</n-button>
                <n-button size="small" quaternary @click="act(job, 'abandon')">放弃（跳过该集）</n-button>
              </n-space>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.body {
  margin-top: 16px;
}
.list {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}
.job {
  display: flex;
  gap: 14px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid rgba(128, 128, 128, 0.18);
}
.thumb {
  width: 54px;
  flex-shrink: 0;
  align-self: flex-start;
}
.job-body {
  flex: 1;
  min-width: 0;
}
.job-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  flex-wrap: wrap;
}
.release {
  font-size: 12px;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 12px;
  opacity: 0.75;
}
.err {
  margin-top: 10px;
  overflow-wrap: anywhere;
}
.small {
  font-size: 12px;
  margin-top: 4px;
}
.link {
  color: inherit;
  cursor: pointer;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
</style>
