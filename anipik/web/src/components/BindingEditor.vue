<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NDynamicTags, NIcon, NRadioButton, NRadioGroup, NSelect, NSwitch, NTag, NTooltip } from 'naive-ui'
import { ArrowDownOutline, ArrowUpOutline, CloseOutline } from '@vicons/ionicons5'
import { api, type Binding, type Preview, type Source } from '../api'
import PreviewTable from './PreviewTable.vue'
import { errorText } from '../util'

// One source binding: which source, keywords, include/exclude filters, with a live search preview.
const binding = defineModel<Binding>({ required: true })
const props = defineProps<{ sources: Source[]; index: number; count: number; subscriptionId?: number }>()
const emit = defineEmits<{ remove: []; move: [delta: number] }>()

const sourceOptions = computed(() =>
  props.sources.map((s) => ({ label: s.enabled ? s.name : `${s.name}（已停用）`, value: s.id })),
)

const preview = ref<Preview | null>(null)
const previewError = ref<string | null>(null)
const loading = ref(false)
let timer: number | undefined
let sequence = 0

async function runPreview() {
  const b = binding.value
  if (!b.source_id || !b.keywords.length) {
    preview.value = null
    return
  }
  const mine = ++sequence
  loading.value = true
  try {
    const result = await api.preview({
      source_id: b.source_id,
      keywords: b.keywords,
      include: b.include,
      exclude: b.exclude,
      subscription_id: props.subscriptionId,
    })
    if (mine === sequence) {
      preview.value = result
      previewError.value = null
    }
  } catch (error) {
    if (mine === sequence) previewError.value = errorText(error)
  } finally {
    if (mine === sequence) loading.value = false
  }
}
watch(
  () => [binding.value.source_id, binding.value.keywords.join('\n'), binding.value.include.join('\n'), binding.value.exclude.join('\n')],
  () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(runPreview, 600)
  },
  { immediate: true },
)

// Bracketed tokens across result titles, e.g. 桜都字幕组 / 简体内嵌 / 1080P — one click turns them into filters.
const tokens = computed(() => {
  const counts = new Map<string, number>()
  for (const item of preview.value?.items ?? []) {
    const seen = new Set<string>()
    for (const match of item.title.matchAll(/[\[【]([^\]】]{1,24})[\]】]/g)) {
      const token = match[1].trim()
      if (!token || /^\d+(v\d)?$/i.test(token) || seen.has(token)) continue
      seen.add(token)
      counts.set(token, (counts.get(token) ?? 0) + 1)
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 16)
})
const tokenTarget = ref<'include' | 'exclude'>('include')
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
function addToken(token: string) {
  const list = binding.value[tokenTarget.value]
  const pattern = escape(token)
  if (!list.includes(pattern)) binding.value = { ...binding.value, [tokenTarget.value]: [...list, pattern] }
}
function tokenState(token: string) {
  const pattern = escape(token)
  if (binding.value.include.includes(pattern)) return 'success'
  if (binding.value.exclude.includes(pattern)) return 'error'
  return 'default'
}

const summary = computed(() => {
  const items = preview.value?.items ?? []
  const episodes = new Set(items.filter((i) => i.matched && i.episode !== null && !i.batch).map((i) => i.episode))
  return { total: items.length, matched: items.filter((i) => i.matched).length, episodes: episodes.size }
})
</script>

<template>
  <div class="binding">
    <div class="head">
      <n-tag :bordered="false" type="primary" size="small">优先级 {{ index + 1 }}</n-tag>
      <n-select
        v-model:value="binding.source_id"
        :options="sourceOptions"
        placeholder="选择来源"
        size="small"
        style="width: 200px"
      />
      <span class="switch"><n-switch v-model:value="binding.enabled" size="small" /> 启用</span>
      <div class="spacer" />
      <n-button quaternary circle size="small" :disabled="index === 0" @click="emit('move', -1)">
        <template #icon><n-icon><arrow-up-outline /></n-icon></template>
      </n-button>
      <n-button quaternary circle size="small" :disabled="index === count - 1" @click="emit('move', 1)">
        <template #icon><n-icon><arrow-down-outline /></n-icon></template>
      </n-button>
      <n-button quaternary circle size="small" @click="emit('remove')">
        <template #icon><n-icon><close-outline /></n-icon></template>
      </n-button>
    </div>

    <div class="rows">
      <div class="row">
        <label>搜索关键词</label>
        <n-dynamic-tags v-model:value="binding.keywords" />
      </div>
      <div class="row">
        <label>必须包含 <span class="hint">（正则，全部满足）</span></label>
        <n-dynamic-tags v-model:value="binding.include" type="success" />
      </div>
      <div class="row">
        <label>排除 <span class="hint">（正则，任一命中即排除）</span></label>
        <n-dynamic-tags v-model:value="binding.exclude" type="error" />
      </div>
    </div>

    <div v-if="tokens.length" class="tokens">
      <n-radio-group v-model:value="tokenTarget" size="small">
        <n-radio-button value="include">点击加入包含</n-radio-button>
        <n-radio-button value="exclude">点击加入排除</n-radio-button>
      </n-radio-group>
      <n-tooltip v-for="[token, n] in tokens" :key="token">
        <template #trigger>
          <n-tag size="small" round :type="tokenState(token)" class="token" @click="addToken(token)">{{ token }} · {{ n }}</n-tag>
        </template>
        出现在 {{ n }} 条结果中
      </n-tooltip>
    </div>

    <n-alert v-if="previewError" type="error" :show-icon="false" style="margin: 10px 0">{{ previewError }}</n-alert>
    <div v-if="preview" class="summary">
      搜到 {{ summary.total }} 条，过滤后 {{ summary.matched }} 条，覆盖 {{ summary.episodes }} 集
      <span class="mono muted">{{ preview.url }}</span>
    </div>
    <preview-table v-if="preview || loading" :items="preview?.items ?? []" :loading="loading" :max-height="300" />
    <div v-else-if="!binding.keywords.length" class="muted hint-line">填写关键词后会自动预览搜索结果</div>
  </div>
</template>

<style scoped>
.binding {
  border: 1px solid rgba(128, 128, 128, 0.2);
  border-radius: 10px;
  padding: 14px;
}
.binding + .binding {
  margin-top: 14px;
}
.head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.spacer {
  flex: 1;
}
.switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.rows {
  display: grid;
  gap: 10px;
  margin: 14px 0 6px;
}
.row label {
  display: block;
  font-size: 13px;
  margin-bottom: 6px;
  opacity: 0.8;
}
.hint {
  font-size: 12px;
  opacity: 0.6;
}
.tokens {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin: 10px 0;
}
.token {
  cursor: pointer;
}
.summary {
  font-size: 13px;
  margin: 10px 0 6px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: baseline;
}
.hint-line {
  font-size: 13px;
  margin-top: 8px;
}
</style>
