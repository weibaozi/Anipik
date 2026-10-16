<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NEmpty, NIcon, NInput, NProgress, NRadioButton, NRadioGroup, NSkeleton, NTag, useMessage } from 'naive-ui'
import { AddOutline, SearchOutline } from '@vicons/ionicons5'
import { api, type Subscription } from '../api'
import Cover from '../components/Cover.vue'
import { errorText, usePolling } from '../util'

const router = useRouter()
const message = useMessage()
const subs = ref<Subscription[] | null>(null)
const query = ref('')
const filter = ref<'enabled' | 'all' | 'disabled'>('enabled')

usePolling(async () => {
  try {
    subs.value = await api.subscriptions()
  } catch (error) {
    if (subs.value === null) message.error(errorText(error))
  }
}, 5000)

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (subs.value ?? []).filter((s) => {
    if (filter.value === 'enabled' && !s.enabled) return false
    if (filter.value === 'disabled' && s.enabled) return false
    return !q || s.name.toLowerCase().includes(q) || (s.original_name ?? '').toLowerCase().includes(q)
  })
})

function progressText(s: Subscription) {
  const done = s.counts.done ?? 0
  return s.total_episodes ? `${done} / ${s.total_episodes}` : `${done} 集`
}
function progressPercent(s: Subscription) {
  if (!s.total_episodes) return 0
  return Math.min(100, Math.round(((s.counts.done ?? 0) / s.total_episodes) * 100))
}
function problems(s: Subscription) {
  return (s.counts.failed ?? 0) + (s.counts.needs_attention ?? 0)
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>订阅</h1>
      <div class="toolbar">
        <n-input v-model:value="query" placeholder="搜索订阅" clearable size="small" style="width: 200px">
          <template #prefix><n-icon><search-outline /></n-icon></template>
        </n-input>
        <n-radio-group v-model:value="filter" size="small">
          <n-radio-button value="enabled">追番中</n-radio-button>
          <n-radio-button value="disabled">已停用</n-radio-button>
          <n-radio-button value="all">全部</n-radio-button>
        </n-radio-group>
        <n-button type="primary" size="small" @click="router.push('/new')">
          <template #icon><n-icon><add-outline /></n-icon></template>
          新建订阅
        </n-button>
      </div>
    </div>

    <div v-if="subs === null" class="grid">
      <div v-for="i in 8" :key="i">
        <n-skeleton style="aspect-ratio: 2/3; height: auto; border-radius: 8px" />
        <n-skeleton text style="margin-top: 10px" />
      </div>
    </div>
    <n-empty v-else-if="!visible.length" :description="subs.length ? '没有符合条件的订阅' : '还没有订阅'" style="margin-top: 80px">
      <template v-if="!subs.length" #extra>
        <n-button type="primary" @click="router.push('/new')">新建第一个订阅</n-button>
      </template>
    </n-empty>
    <div v-else class="grid">
      <router-link v-for="s in visible" :key="s.id" :to="`/sub/${s.id}`" class="card" :class="{ disabled: !s.enabled }">
        <cover :src="s.cover_url" :name="s.name">
          <div class="badges">
            <n-tag v-if="!s.enabled" size="small" round :bordered="false">已停用</n-tag>
            <n-tag v-if="problems(s)" size="small" round type="warning" :bordered="false">{{ problems(s) }} 需处理</n-tag>
            <n-tag v-if="s.active_jobs" size="small" round type="info" :bordered="false">下载中 {{ s.active_progress?.toFixed(0) }}%</n-tag>
          </div>
          <div class="overlay">
            <span class="ep">{{ progressText(s) }}</span>
            <span v-if="s.latest_done" class="muted-light">最新 第{{ s.latest_done }}集</span>
          </div>
        </cover>
        <n-progress
          v-if="s.total_episodes"
          type="line"
          :percentage="progressPercent(s)"
          :show-indicator="false"
          :height="3"
          :border-radius="0"
          class="bar"
        />
        <div class="title" :title="s.name">{{ s.name }}</div>
        <div class="subtitle">{{ s.sources.join(' · ') || '未绑定来源' }}</div>
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 22px 18px;
}
.card {
  color: inherit;
  text-decoration: none;
  display: block;
  transition: transform 0.15s ease;
}
.card:hover {
  transform: translateY(-3px);
}
.card.disabled :deep(img),
.card.disabled :deep(.cover-placeholder) {
  filter: grayscale(0.9);
  opacity: 0.6;
}
.badges {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.overlay {
  position: absolute;
  inset: auto 0 0 0;
  padding: 28px 10px 8px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  color: #fff;
  font-size: 12px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
}
.ep {
  font-weight: 600;
  font-size: 13px;
}
.muted-light {
  opacity: 0.8;
}
.bar {
  margin-top: -3px;
  position: relative;
}
.title {
  margin-top: 8px;
  font-weight: 600;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.subtitle {
  font-size: 12px;
  opacity: 0.55;
  margin-top: 2px;
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 16px 12px;
  }
}
</style>
