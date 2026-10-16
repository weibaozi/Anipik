<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NEmpty,
  NIcon,
  NInput,
  NInputNumber,
  NScrollbar,
  NSpin,
  NSwitch,
  useMessage,
} from 'naive-ui'
import { AddOutline, ArrowBackOutline, CloseOutline, SearchOutline } from '@vicons/ionicons5'
import { api, type BangumiItem, type Binding, type Source, type SubscriptionInput } from '../api'
import BindingEditor from '../components/BindingEditor.vue'
import Cover from '../components/Cover.vue'
import { errorText, seasonFolder } from '../util'

const props = defineProps<{ id?: string }>()
const router = useRouter()
const message = useMessage()
const editing = computed(() => props.id !== undefined)

const form = ref<SubscriptionInput>({
  name: '',
  enabled: true,
  save_dir: '',
  bindings: [],
  start_episode: 1,
  bangumi_id: null,
  original_name: null,
  cover_url: null,
  air_date: null,
  total_episodes: null,
  summary: null,
})
const sources = ref<Source[]>([])
const libraryRoot = ref('')
const loading = ref(true)
const saving = ref(false)
const loadError = ref<string | null>(null)

onMounted(async () => {
  try {
    const [srcs, settings] = await Promise.all([api.sources(), api.settings()])
    sources.value = srcs
    libraryRoot.value = settings.library_root
    if (editing.value) {
      const sub = await api.subscription(Number(props.id))
      form.value = {
        name: sub.name,
        enabled: sub.enabled,
        save_dir: sub.save_dir,
        bindings: sub.bindings.map((b) => ({ ...b })),
        bangumi_id: sub.bangumi_id,
        original_name: sub.original_name,
        cover_url: sub.cover_url,
        air_date: sub.air_date,
        total_episodes: sub.total_episodes,
        summary: sub.summary,
      }
      query.value = sub.original_name || sub.name
    }
  } catch (error) {
    loadError.value = errorText(error)
  } finally {
    loading.value = false
  }
})

// --- bgm.tv search
const query = ref('')
const results = ref<BangumiItem[] | null>(null)
const searching = ref(false)
async function search() {
  if (!query.value.trim()) return
  searching.value = true
  try {
    results.value = await api.bangumiSearch(query.value.trim())
  } catch (error) {
    message.error(errorText(error))
  } finally {
    searching.value = false
  }
}
async function pick(item: BangumiItem) {
  let detail: BangumiItem = item
  try {
    detail = { ...item, ...(await api.bangumiSubject(item.id)) }
  } catch {
    /* search result alone is good enough */
  }
  const previousName = form.value.name
  const name = detail.name_cn || detail.name
  form.value = {
    ...form.value,
    bangumi_id: detail.id,
    original_name: detail.name || null,
    cover_url: detail.cover_url,
    air_date: detail.air_date,
    total_episodes: detail.total_episodes,
    summary: detail.summary ?? null,
    name: editing.value && previousName ? previousName : name,
  }
  if (!editing.value) {
    const season = seasonFolder(detail.air_date)
    form.value.save_dir = season ? `${season}/${form.value.name}` : form.value.name
    if (!form.value.bindings.length && sources.value.length) addBinding(name)
    else form.value.bindings.forEach((b) => !b.keywords.length && b.keywords.push(name))
  }
  results.value = null
}
function clearMetadata() {
  Object.assign(form.value, { bangumi_id: null, original_name: null, cover_url: null, air_date: null, total_episodes: null, summary: null })
}

// --- folders
const season = computed(() => seasonFolder(form.value.air_date))
const destination = computed(() => {
  const dir = (form.value.save_dir || form.value.name || '').trim()
  if (!dir) return ''
  if (/^([a-zA-Z]:[\\/]|[\\/]{2})/.test(dir)) return dir
  return `${libraryRoot.value.replace(/[\\/]+$/, '')}\\${dir.replace(/\//g, '\\')}`
})

// --- bindings
function addBinding(keyword?: string) {
  const used = new Set(form.value.bindings.map((b) => b.source_id))
  const source = sources.value.find((s) => s.enabled && !used.has(s.id)) ?? sources.value.find((s) => !used.has(s.id))
  if (!source) {
    message.warning(sources.value.length ? '所有来源都已添加' : '还没有来源，请先在「来源」页添加')
    return
  }
  const word = keyword ?? form.value.name
  form.value.bindings.push({ source_id: source.id, enabled: true, keywords: word ? [word] : [], include: [], exclude: [] })
}
function moveBinding(index: number, delta: number) {
  const list = form.value.bindings
  const [item] = list.splice(index, 1)
  list.splice(index + delta, 0, item)
}

async function save() {
  if (!form.value.name.trim()) return message.warning('请填写名称')
  const empty = form.value.bindings.findIndex((b) => !b.keywords.length)
  if (empty >= 0) return message.warning(`来源 ${empty + 1} 还没有关键词`)
  saving.value = true
  try {
    const body = { ...form.value, name: form.value.name.trim(), save_dir: form.value.save_dir?.trim() || null }
    const result = editing.value
      ? await api.updateSubscription(Number(props.id), { ...body, start_episode: undefined })
      : await api.createSubscription(body)
    message.success(editing.value ? '已保存' : '已创建订阅，正在扫描…')
    router.push(`/sub/${result.id}`)
  } catch (error) {
    message.error(errorText(error))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page narrow">
    <n-button text style="margin-bottom: 14px" @click="router.back()">
      <template #icon><n-icon><arrow-back-outline /></n-icon></template>
      返回
    </n-button>
    <div class="page-header"><h1>{{ editing ? '编辑订阅' : '新建订阅' }}</h1></div>

    <n-alert v-if="loadError" type="error" :title="loadError" />
    <n-spin v-else-if="loading" style="width: 100%; margin-top: 60px" />
    <template v-else>
      <n-card title="1. 番剧" size="small" class="section">
        <div v-if="form.bangumi_id" class="picked">
          <cover :src="form.cover_url" :name="form.name" class="picked-cover" />
          <div class="picked-body">
            <div class="picked-name">{{ form.name || form.original_name }}</div>
            <div class="muted">{{ form.original_name }}</div>
            <div class="muted small">
              {{ form.air_date ? `${form.air_date} 开播` : '' }}
              {{ form.total_episodes ? ` · ${form.total_episodes} 集` : '' }}
            </div>
          </div>
          <n-button quaternary circle size="small" @click="clearMetadata">
            <template #icon><n-icon><close-outline /></n-icon></template>
          </n-button>
        </div>
        <div class="search">
          <n-input v-model:value="query" placeholder="在 bgm.tv 搜索番剧名（可选，用于封面和集数）" clearable @keyup.enter="search">
            <template #prefix><n-icon><search-outline /></n-icon></template>
          </n-input>
          <n-button :loading="searching" @click="search">搜索</n-button>
        </div>
        <template v-if="results">
          <n-empty v-if="!results.length" description="没有找到" style="margin: 20px 0" />
          <n-scrollbar v-else x-scrollable>
            <div class="results">
              <button v-for="r in results" :key="r.id" type="button" class="result" @click="pick(r)">
                <cover :src="r.cover_url" :name="r.name_cn || r.name" />
                <div class="r-name">{{ r.name_cn || r.name }}</div>
                <div class="r-meta">{{ r.air_date || '' }}{{ r.total_episodes ? ` · ${r.total_episodes}集` : '' }}</div>
              </button>
            </div>
          </n-scrollbar>
        </template>
      </n-card>

      <n-card title="2. 基本设置" size="small" class="section">
        <div class="form-grid">
          <label>名称</label>
          <n-input v-model:value="form.name" placeholder="显示名称，也是默认文件夹名" />
          <label>保存目录</label>
          <div>
            <n-input v-model:value="form.save_dir" :placeholder="form.name || '相对于媒体库根目录，或绝对路径'" />
            <div class="quick">
              <n-button size="tiny" secondary @click="form.save_dir = form.name">{{ form.name || '名称' }}</n-button>
              <n-button v-if="season" size="tiny" secondary @click="form.save_dir = `${season}/${form.name}`">{{ season }}/{{ form.name || '名称' }}</n-button>
            </div>
            <div v-if="destination" class="mono muted dest">{{ destination }}</div>
          </div>
          <template v-if="!editing">
            <label>从第几集开始</label>
            <div>
              <n-input-number v-model:value="form.start_episode" :min="1" style="width: 140px" />
              <div class="muted small">之前的集数会标记为跳过</div>
            </div>
          </template>
          <label>启用</label>
          <n-switch v-model:value="form.enabled" />
        </div>
      </n-card>

      <n-card title="3. 来源" size="small" class="section">
        <template #header-extra>
          <n-button size="small" secondary @click="addBinding()">
            <template #icon><n-icon><add-outline /></n-icon></template>
            添加来源
          </n-button>
        </template>
        <div v-if="!form.bindings.length" class="muted">
          {{ sources.length ? '还没有绑定来源。按优先级依次查找，前面的来源找到的集数优先。' : '' }}
          <router-link v-if="!sources.length" to="/sources">先去添加一个来源</router-link>
        </div>
        <binding-editor
          v-for="(b, i) in form.bindings"
          :key="i"
          v-model="form.bindings[i]"
          :sources="sources"
          :index="i"
          :count="form.bindings.length"
          :subscription-id="editing ? Number(id) : undefined"
          @remove="form.bindings.splice(i, 1)"
          @move="moveBinding(i, $event)"
        />
      </n-card>

      <div class="footer">
        <n-button @click="router.back()">取消</n-button>
        <n-button type="primary" :loading="saving" @click="save">{{ editing ? '保存' : '创建订阅' }}</n-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.narrow {
  max-width: 980px;
}
.section {
  margin-bottom: 16px;
}
.picked {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.picked-cover {
  width: 72px;
  flex-shrink: 0;
}
.picked-body {
  flex: 1;
  min-width: 0;
}
.picked-name {
  font-weight: 600;
  font-size: 16px;
}
.small {
  font-size: 12px;
  margin-top: 4px;
}
.search {
  display: flex;
  gap: 8px;
}
.results {
  display: flex;
  gap: 12px;
  padding: 14px 0 6px;
}
.result {
  width: 112px;
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  padding: 0;
  cursor: pointer;
}
.result:hover {
  opacity: 0.85;
}
.r-name {
  font-size: 13px;
  font-weight: 600;
  margin-top: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.r-meta {
  font-size: 11px;
  opacity: 0.6;
}
.form-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 14px 16px;
  align-items: start;
}
.form-grid > label {
  padding-top: 6px;
  font-size: 14px;
  opacity: 0.85;
}
.quick {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.dest {
  margin-top: 6px;
}
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 8px 0 30px;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .form-grid > label {
    padding-top: 8px;
  }
}
</style>
