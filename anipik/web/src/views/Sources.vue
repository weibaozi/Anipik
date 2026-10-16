<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NDataTable,
  NIcon,
  NInput,
  NModal,
  NPopconfirm,
  NSpace,
  NSwitch,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import { api, type Preview, type Source } from '../api'
import PreviewTable from '../components/PreviewTable.vue'
import { errorText } from '../util'

const message = useMessage()
const sources = ref<Source[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    sources.value = await api.sources()
  } catch (error) {
    message.error(errorText(error))
  } finally {
    loading.value = false
  }
}
onMounted(load)

// Presets for common sites (rss_search: prefix + keywords joined by sep + suffix).
const presets = [
  { name: '动漫花园 dmhy', search_prefix: 'https://share.dmhy.org/topics/rss/rss.xml?keyword=', keyword_sep: '+', search_suffix: '' },
  { name: '末日动漫 acgnx', search_prefix: 'https://share.acgnx.se/rss.xml?keyword=', keyword_sep: '+', search_suffix: '' },
  { name: 'MioBT', search_prefix: 'https://www.miobt.com/rss-', keyword_sep: '+', search_suffix: '.xml' },
  { name: 'ACG.RIP', search_prefix: 'https://acg.rip/.xml?term=', keyword_sep: '+', search_suffix: '' },
  { name: 'Nyaa', search_prefix: 'https://nyaa.si/?page=rss&q=', keyword_sep: '+', search_suffix: '' },
]

const editing = ref<{ id?: number; name: string; enabled: boolean; config: Record<string, string> } | null>(null)
const testKeyword = ref('')
const testResult = ref<Preview | null>(null)
const testing = ref(false)
const saving = ref(false)

function open(source?: Source) {
  editing.value = source
    ? { id: source.id, name: source.name, enabled: source.enabled, config: { keyword_sep: '+', search_suffix: '', ...source.config } }
    : { name: '', enabled: true, config: { search_prefix: '', keyword_sep: '+', search_suffix: '' } }
  testResult.value = null
}
function applyPreset(preset: (typeof presets)[number]) {
  if (!editing.value) return
  const { name, ...config } = preset
  editing.value.config = config
  if (!editing.value.name) editing.value.name = name.split(' ')[0]
}
const exampleUrl = computed(() => {
  const c = editing.value?.config
  if (!c) return ''
  return `${c.search_prefix ?? ''}${['关键词1', '关键词2'].join(c.keyword_sep ?? '+')}${c.search_suffix ?? ''}`
})

async function test() {
  if (!editing.value || !testKeyword.value.trim()) return
  testing.value = true
  try {
    testResult.value = await api.preview({
      kind: 'rss_search',
      config: editing.value.config,
      keywords: testKeyword.value.trim().split(/\s+/),
    })
  } catch (error) {
    message.error(errorText(error))
  } finally {
    testing.value = false
  }
}

async function save() {
  const value = editing.value
  if (!value) return
  if (!value.name.trim() || !value.config.search_prefix?.trim()) return message.warning('名称和搜索前缀必填')
  saving.value = true
  try {
    if (value.id) await api.updateSource(value.id, { name: value.name.trim(), enabled: value.enabled, config: value.config })
    else await api.createSource({ name: value.name.trim(), kind: 'rss_search', enabled: value.enabled, config: value.config })
    message.success('已保存')
    editing.value = null
    load()
  } catch (error) {
    message.error(errorText(error))
  } finally {
    saving.value = false
  }
}

async function remove(source: Source) {
  try {
    await api.deleteSource(source.id)
    message.success(`已删除 ${source.name}`)
    load()
  } catch (error) {
    message.error(errorText(error))
  }
}

async function toggle(source: Source, enabled: boolean) {
  try {
    await api.updateSource(source.id, { enabled })
    source.enabled = enabled
  } catch (error) {
    message.error(errorText(error))
  }
}

const columns = computed<DataTableColumns<Source>>(() => [
  { title: '名称', key: 'name', width: 140, render: (row) => h('b', row.name) },
  {
    title: '搜索地址',
    key: 'config',
    ellipsis: { tooltip: true },
    render: (row) =>
      h('span', { class: 'mono' }, `${row.config.search_prefix ?? ''}{关键词}${row.config.search_suffix ?? ''}`),
  },
  { title: '订阅数', key: 'subscriptions', width: 80 },
  {
    title: '启用',
    key: 'enabled',
    width: 70,
    render: (row) => h(NSwitch, { size: 'small', value: row.enabled, onUpdateValue: (v: boolean) => toggle(row, v) }),
  },
  {
    title: '',
    key: 'actions',
    width: 140,
    render: (row) =>
      h(NSpace, { size: 6, justify: 'end' }, () => [
        h(NButton, { size: 'tiny', secondary: true, onClick: () => open(row) }, () => '编辑'),
        h(
          NPopconfirm,
          { onPositiveClick: () => remove(row), disabled: row.subscriptions > 0 },
          {
            trigger: () =>
              h(NButton, { size: 'tiny', quaternary: true, type: 'error', disabled: row.subscriptions > 0 }, () => '删除'),
            default: () => `删除来源「${row.name}」？`,
          },
        ),
      ]),
  },
])
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>来源</h1>
      <n-button type="primary" size="small" @click="open()">
        <template #icon><n-icon><add-outline /></n-icon></template>
        添加来源
      </n-button>
    </div>
    <n-alert type="info" :show-icon="false" style="margin-bottom: 16px">
      来源是一个可以按关键词搜索的 RSS 站点。订阅里为每个来源单独设置关键词和过滤条件；被订阅使用中的来源不能删除。
    </n-alert>
    <n-data-table :columns="columns" :data="sources" :loading="loading" :bordered="false" :row-key="(r: Source) => r.id" />

    <n-modal :show="!!editing" preset="card" :title="editing?.id ? '编辑来源' : '添加来源'" style="width: min(860px, 94vw)" @update:show="(v: boolean) => !v && (editing = null)">
      <template v-if="editing">
        <div class="presets">
          <span class="muted">常用站点：</span>
          <n-tag v-for="p in presets" :key="p.name" size="small" round class="preset" @click="applyPreset(p)">{{ p.name }}</n-tag>
        </div>
        <div class="form-grid">
          <label>名称</label>
          <n-input v-model:value="editing.name" placeholder="例如 dmhy" />
          <label>搜索前缀</label>
          <n-input v-model:value="editing.config.search_prefix" placeholder="https://share.dmhy.org/topics/rss/rss.xml?keyword=" />
          <label>关键词分隔</label>
          <n-input v-model:value="editing.config.keyword_sep" style="width: 120px" />
          <label>搜索后缀</label>
          <n-input v-model:value="editing.config.search_suffix" placeholder="可留空，例如 .xml" />
          <label>启用</label>
          <n-switch v-model:value="editing.enabled" />
          <label>示例</label>
          <span class="mono muted" style="padding-top: 6px">{{ exampleUrl }}</span>
          <label>测试搜索</label>
          <div class="test">
            <n-input v-model:value="testKeyword" placeholder="输入关键词，空格分隔" @keyup.enter="test" />
            <n-button :loading="testing" @click="test">测试</n-button>
          </div>
        </div>
        <preview-table v-if="testResult" :items="testResult.items" :max-height="260" style="margin-top: 14px" />
      </template>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editing = null">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 16px;
  font-size: 13px;
}
.preset {
  cursor: pointer;
}
.form-grid {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 12px 14px;
  align-items: start;
}
.form-grid > label {
  padding-top: 6px;
  font-size: 14px;
  opacity: 0.85;
}
.test {
  display: flex;
  gap: 8px;
}
</style>
