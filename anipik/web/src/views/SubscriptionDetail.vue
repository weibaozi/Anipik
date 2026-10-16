<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEllipsis,
  NIcon,
  NPopconfirm,
  NProgress,
  NSpace,
  NSpin,
  NSwitch,
  NTag,
  useDialog,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { ArrowBackOutline, CreateOutline, SearchOutline, TrashOutline } from '@vicons/ionicons5'
import { api, type Binding, type Episode, type Preview, type SubscriptionDetail } from '../api'
import Cover from '../components/Cover.vue'
import EpisodeGrid from '../components/EpisodeGrid.vue'
import PreviewTable from '../components/PreviewTable.vue'
import { backendPhase, episodeStatus, errorText, formatTime, jobPhase, usePolling } from '../util'

const props = defineProps<{ id: string }>()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const sub = ref<SubscriptionDetail | null>(null)
const loadError = ref<string | null>(null)
const selected = ref<number[]>([])

async function load() {
  try {
    sub.value = await api.subscription(Number(props.id))
    loadError.value = null
  } catch (error) {
    loadError.value = errorText(error)
  }
}
const { refresh } = usePolling(load, 4000)
watch(() => props.id, () => {
  sub.value = null
  selected.value = []
  refresh()
})

const counts = computed(() =>
  Object.entries(sub.value?.counts ?? {}).map(([status, count]) => ({ ...episodeStatus[status as Episode['status']], count })),
)

async function toggleEnabled(value: boolean) {
  if (!sub.value) return
  try {
    sub.value = await api.updateSubscription(sub.value.id, { enabled: value })
    message.success(value ? '已启用，下次扫描会检查新集数' : '已停用')
  } catch (error) {
    message.error(errorText(error))
  }
}

async function mark(status: 'done' | 'skipped' | 'delete') {
  if (!sub.value || !selected.value.length) return
  try {
    sub.value = await api.markEpisodes(sub.value.id, selected.value, status)
    message.success(`已更新 ${selected.value.length} 集`)
    selected.value = []
  } catch (error) {
    message.error(errorText(error))
  }
}

function remove() {
  if (!sub.value) return
  const name = sub.value.name
  dialog.warning({
    title: '删除订阅',
    content: `删除「${name}」及其集数记录？已下载的文件不会被删除。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteSubscription(sub.value!.id)
        message.success(`已删除 ${name}`)
        router.push('/')
      } catch (error) {
        message.error(errorText(error))
        return false
      }
    },
  })
}

// --- preview drawer
const drawerWidth = Math.min(900, window.innerWidth)
const previewOpen = ref(false)
const preview = ref<Preview | null>(null)
const previewBinding = ref<Binding | null>(null)
const previewLoading = ref(false)
async function openPreview(binding: Binding) {
  previewBinding.value = binding
  previewOpen.value = true
  previewLoading.value = true
  preview.value = null
  try {
    preview.value = await api.preview({
      source_id: binding.source_id,
      keywords: binding.keywords,
      include: binding.include,
      exclude: binding.exclude,
      subscription_id: sub.value?.id,
    })
  } catch (error) {
    message.error(errorText(error))
  } finally {
    previewLoading.value = false
  }
}

// --- download history (latest job per episode)
const jobs = computed(() =>
  (sub.value?.episodes ?? [])
    .filter((e) => e.job)
    .map((e) => e.job!)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
)
const jobColumns: DataTableColumns<NonNullable<Episode['job']>> = [
  { title: '集', key: 'episode', width: 56 },
  {
    title: '状态',
    key: 'phase',
    width: 100,
    render: (row) => h(NTag, { size: 'small', bordered: false, type: jobPhase[row.phase].type }, () => jobPhase[row.phase].label),
  },
  {
    title: '进度',
    key: 'progress',
    width: 200,
    render: (row) =>
      row.phase === 'running'
        ? h('div', [
            h(NProgress, { type: 'line', percentage: row.progress, height: 8, indicatorPlacement: 'inside', processing: true }),
            h('div', { class: 'muted', style: 'font-size:12px;margin-top:2px' }, backendPhase[row.backend_phase ?? ''] ?? row.message ?? ''),
          ])
        : row.error
          ? h(NEllipsis, { style: 'max-width:200px' }, () => row.error)
          : `${row.progress}%`,
  },
  { title: '发布', key: 'release_title', ellipsis: { tooltip: true } },
  { title: '更新', key: 'updated_at', width: 110, render: (row) => formatTime(row.updated_at) },
]
</script>

<template>
  <div class="page">
    <n-button text style="margin-bottom: 14px" @click="router.push('/')">
      <template #icon><n-icon><arrow-back-outline /></n-icon></template>
      返回订阅
    </n-button>

    <n-alert v-if="loadError && !sub" type="error" :title="loadError" />
    <n-spin v-else-if="!sub" style="width: 100%; margin-top: 80px" />
    <template v-else>
      <div class="hero">
        <cover :src="sub.cover_url" :name="sub.name" class="hero-cover" :radius="12" />
        <div class="hero-body">
          <div class="title-row">
            <h1>{{ sub.name }}</h1>
            <n-space :size="8">
              <n-button size="small" @click="router.push(`/sub/${sub.id}/edit`)">
                <template #icon><n-icon><create-outline /></n-icon></template>
                编辑
              </n-button>
              <n-button size="small" type="error" ghost @click="remove">
                <template #icon><n-icon><trash-outline /></n-icon></template>
                删除
              </n-button>
            </n-space>
          </div>
          <div v-if="sub.original_name" class="muted original">{{ sub.original_name }}</div>
          <n-space :size="6" style="margin: 12px 0">
            <n-tag v-if="sub.air_date" size="small" round :bordered="false">{{ sub.air_date }} 开播</n-tag>
            <n-tag v-if="sub.total_episodes" size="small" round :bordered="false">共 {{ sub.total_episodes }} 集</n-tag>
            <n-tag v-for="c in counts" :key="c.label" size="small" round :type="c.type" :bordered="false">{{ c.label }} {{ c.count }}</n-tag>
            <a v-if="sub.bangumi_id" :href="`https://bgm.tv/subject/${sub.bangumi_id}`" target="_blank" rel="noreferrer" class="bgm">bgm.tv ↗</a>
          </n-space>
          <div class="enable">
            <n-switch :value="sub.enabled" @update:value="toggleEnabled" />
            <span>{{ sub.enabled ? '追番中：定时扫描新集数' : '已停用：不再自动下载' }}</span>
          </div>
          <div class="field"><span class="muted">保存到</span> <span class="mono">{{ sub.destination }}</span></div>
          <n-ellipsis v-if="sub.summary" :line-clamp="3" :tooltip="{ width: 480 }" class="summary">{{ sub.summary }}</n-ellipsis>
        </div>
      </div>

      <n-card title="集数" size="small" class="section">
        <template #header-extra>
          <span class="muted legend">点击选择，Shift 多选</span>
        </template>
        <episode-grid v-model:selected="selected" :episodes="sub.episodes" :total="sub.total_episodes" />
        <div v-if="!sub.episodes.length && !sub.total_episodes" class="muted">还没有任何集数记录，扫描后会出现在这里。</div>
        <transition name="fade">
          <div v-if="selected.length" class="selection">
            <span>已选 {{ selected.length }} 集：{{ selected.join(', ') }}</span>
            <n-space :size="8">
              <n-button size="small" type="success" secondary @click="mark('done')">标记已下载</n-button>
              <n-button size="small" secondary @click="mark('skipped')">跳过</n-button>
              <n-popconfirm @positive-click="mark('delete')">
                <template #trigger><n-button size="small" type="warning" secondary>重置</n-button></template>
                清除这些集的记录，下次扫描会重新查找并下载。
              </n-popconfirm>
              <n-button size="small" quaternary @click="selected = []">取消</n-button>
            </n-space>
          </div>
        </transition>
      </n-card>

      <n-card title="来源" size="small" class="section">
        <div v-if="!sub.bindings.length" class="muted">未绑定来源，<router-link :to="`/sub/${sub.id}/edit`">去添加</router-link></div>
        <div v-for="(b, i) in sub.bindings" :key="b.id" class="binding">
          <div class="binding-main">
            <n-tag size="small" :type="b.enabled ? 'primary' : 'default'" :bordered="false">{{ i + 1 }}. {{ b.source_name }}</n-tag>
            <span class="kw">关键词 <n-tag v-for="k in b.keywords" :key="k" size="small">{{ k }}</n-tag></span>
            <span v-if="b.include.length" class="kw">包含 <n-tag v-for="k in b.include" :key="k" size="small" type="success">{{ k }}</n-tag></span>
            <span v-if="b.exclude.length" class="kw">排除 <n-tag v-for="k in b.exclude" :key="k" size="small" type="error">{{ k }}</n-tag></span>
            <n-tag v-if="!b.enabled" size="small">已停用</n-tag>
          </div>
          <n-button size="small" secondary @click="openPreview(b)">
            <template #icon><n-icon><search-outline /></n-icon></template>
            预览搜索结果
          </n-button>
        </div>
      </n-card>

      <n-card title="下载记录" size="small" class="section">
        <n-data-table size="small" :columns="jobColumns" :data="jobs" :bordered="false" :row-key="(row: any) => row.id" />
      </n-card>

      <n-drawer v-model:show="previewOpen" :width="drawerWidth" placement="right">
        <n-drawer-content :title="`预览 · ${previewBinding?.source_name ?? ''}`" closable>
          <div v-if="preview" class="muted mono" style="margin-bottom: 10px">{{ preview.url }} · {{ preview.count }} 条</div>
          <preview-table :items="preview?.items ?? []" :loading="previewLoading" :max-height="9999" />
        </n-drawer-content>
      </n-drawer>
    </template>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
}
.hero-cover {
  width: 180px;
  flex-shrink: 0;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
}
.hero-body {
  flex: 1;
  min-width: 0;
}
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 24px;
}
.original {
  margin-top: 4px;
}
.enable {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.field {
  margin-bottom: 10px;
}
.summary {
  font-size: 13px;
  opacity: 0.75;
  line-height: 1.6;
}
.bgm {
  font-size: 12px;
  color: inherit;
  opacity: 0.7;
}
.section {
  margin-bottom: 16px;
}
.legend {
  font-size: 12px;
}
.selection {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(124, 92, 255, 0.1);
}
.binding {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  flex-wrap: wrap;
}
.binding + .binding {
  border-top: 1px solid rgba(128, 128, 128, 0.15);
}
.binding-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.kw {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  opacity: 0.85;
  flex-wrap: wrap;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
@media (max-width: 640px) {
  .hero {
    flex-direction: column;
  }
  .hero-cover {
    width: 140px;
  }
}
</style>
