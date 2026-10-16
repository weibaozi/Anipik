<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  NBadge,
  NButton,
  NIcon,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NTag,
  NTooltip,
  useMessage,
  type MenuOption,
} from 'naive-ui'
import {
  CloudDownloadOutline,
  ContrastOutline,
  GlobeOutline,
  MoonOutline,
  RefreshOutline,
  SettingsOutline,
  SunnyOutline,
  TvOutline,
} from '@vicons/ionicons5'
import { api } from '../api'
import { activeCount, attentionCount, refreshStatus, status, statusError, theme } from '../store'
import { errorText, formatTime, usePolling } from '../util'

defineProps<{ dark: boolean }>()
const route = useRoute()
const message = useMessage()
const collapsed = ref(window.innerWidth < 900)
// Follow the window: collapse when it becomes narrow, expand when it becomes wide again.
let wasNarrow = window.innerWidth < 900
function onResize() {
  const narrow = window.innerWidth < 900
  if (narrow !== wasNarrow) collapsed.value = narrow
  wasNarrow = narrow
}
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

usePolling(refreshStatus, 4000)

function icon(component: any) {
  return () => h(NIcon, null, { default: () => h(component) })
}
function link(to: string, label: string, badge?: () => number) {
  return () =>
    h(RouterLink, { to }, {
      default: () =>
        badge && badge() > 0
          ? h('span', { style: 'display:inline-flex;align-items:center;gap:8px' }, [
              label,
              h(NBadge, { value: badge(), type: 'warning', max: 99 }),
            ])
          : label,
    })
}

const menu = computed<MenuOption[]>(() => [
  { key: 'subscriptions', label: link('/', '订阅'), icon: icon(TvOutline) },
  { key: 'jobs', label: link('/jobs', '下载任务', () => attentionCount.value), icon: icon(CloudDownloadOutline) },
  { key: 'sources', label: link('/sources', '来源'), icon: icon(GlobeOutline) },
  { key: 'settings', label: link('/settings', '设置'), icon: icon(SettingsOutline) },
])
const activeKey = computed(() => {
  const name = String(route.name ?? '')
  return ['new', 'subscription', 'edit'].includes(name) ? 'subscriptions' : name
})

const scheduler = computed(() => status.value?.scheduler)
const backend = computed(() => {
  const name = status.value?.downloader
  return name ? scheduler.value?.backends?.[name] : undefined
})

const scanning = ref(false)
async function scanNow() {
  scanning.value = true
  try {
    await api.scan()
    message.success(status.value?.scheduler_in_process ? '已开始扫描' : '已请求扫描（由独立调度进程执行）')
    setTimeout(refreshStatus, 800)
  } catch (error) {
    message.error(errorText(error))
  } finally {
    scanning.value = false
  }
}

const themeIcon = computed(() => (theme.pref === 'auto' ? ContrastOutline : theme.pref === 'dark' ? MoonOutline : SunnyOutline))
const themeLabel = computed(() => ({ auto: '跟随系统', dark: '深色', light: '浅色' })[theme.pref])
function cycleTheme() {
  theme.pref = theme.pref === 'auto' ? 'dark' : theme.pref === 'dark' ? 'light' : 'auto'
}
</script>

<template>
  <n-layout has-sider position="absolute">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="200"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="brand" :class="{ collapsed }">
        <span class="logo">A</span>
        <span v-if="!collapsed" class="name">Anipik</span>
      </div>
      <n-menu :value="activeKey" :options="menu" :collapsed="collapsed" :collapsed-width="64" :collapsed-icon-size="22" />
    </n-layout-sider>
    <n-layout content-style="display:flex;flex-direction:column;height:100%">
      <n-layout-header bordered class="topbar">
        <div class="chips">
          <n-tooltip v-if="statusError">
            <template #trigger><n-tag type="error" round size="small">后端未连接</n-tag></template>
            {{ statusError }}
          </n-tooltip>
          <template v-else-if="status">
            <n-tooltip>
              <template #trigger>
                <n-tag :type="scheduler?.running ? 'success' : 'warning'" round size="small">
                  {{ scheduler?.scanning ? '扫描中…' : scheduler?.running ? '调度运行中' : status.scheduler_in_process ? '调度已停止' : '外部调度' }}
                </n-tag>
              </template>
              <div>上次扫描：{{ formatTime(scheduler?.last_scan_at) }}<span v-if="scheduler?.last_scan_queued">（新增 {{ scheduler.last_scan_queued }} 集）</span></div>
              <div>下次扫描：{{ formatTime(scheduler?.next_scan_at) }}</div>
              <div v-if="scheduler?.last_scan_error">错误：{{ scheduler.last_scan_error }}</div>
            </n-tooltip>
            <n-tooltip v-if="backend">
              <template #trigger>
                <n-tag :type="backend.ok ? 'success' : 'error'" round size="small">PikPak {{ backend.ok ? '已连接' : '未连接' }}</n-tag>
              </template>
              {{ backend.ok ? `最近一次连接 ${formatTime(backend.at)}` : backend.error }}
            </n-tooltip>
            <router-link v-if="activeCount" to="/jobs" class="plain-link">
              <n-tag type="info" round size="small">{{ activeCount }} 个下载进行中</n-tag>
            </router-link>
          </template>
        </div>
        <div class="actions">
          <n-button size="small" secondary :loading="scanning || scheduler?.scanning" @click="scanNow">
            <template #icon><n-icon><refresh-outline /></n-icon></template>
            立即扫描
          </n-button>
          <n-tooltip>
            <template #trigger>
              <n-button size="small" quaternary circle @click="cycleTheme">
                <template #icon><n-icon><component :is="themeIcon" /></n-icon></template>
              </n-button>
            </template>
            主题：{{ themeLabel }}
          </n-tooltip>
        </div>
      </n-layout-header>
      <n-layout-content :native-scrollbar="false" class="content">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 18px;
}
.brand.collapsed {
  justify-content: center;
  padding: 0;
}
.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #7c5cff, #ec4899);
}
.name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.topbar {
  flex: none;
  min-height: 56px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 10px 20px;
}
.chips,
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.content {
  flex: 1;
  min-height: 0;
}
@media (max-width: 640px) {
  .topbar {
    padding: 8px 12px;
  }
}
.plain-link {
  text-decoration: none;
}
</style>
