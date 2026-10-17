<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NInput, NInputNumber, NSpin, NSwitch, NTag, useDialog, useMessage } from 'naive-ui'
import { api, type Health, type Settings } from '../api'
import { status } from '../store'
import { errorText } from '../util'

const message = useMessage()
const dialog = useDialog()
const settings = ref<Settings | null>(null)
const original = ref('')
const saving = ref(false)
const health = ref<Health | null>(null)
const probing = ref(false)

onMounted(async () => {
  try {
    const loaded = await api.settings()
    // Older saved values may lack newer keys; fill them so the form and change detection agree.
    loaded['downloader.pikpak_client'] = {
    port: 19223,
    exe_path: '',
    auto_start: true,
    start_hidden: true,
    ...loaded['downloader.pikpak_client'],
  }
    settings.value = loaded
    original.value = JSON.stringify(settings.value)
  } catch (error) {
    message.error(errorText(error))
  }
  probe()
})

async function save() {
  if (!settings.value) return
  const before = JSON.parse(original.value)
  const changed = Object.fromEntries(
    Object.entries(settings.value).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(before[key])),
  )
  if (!Object.keys(changed).length) return message.info('没有修改')
  saving.value = true
  try {
    settings.value = await api.updateSettings(changed)
    original.value = JSON.stringify(settings.value)
    message.success('已保存')
  } catch (error) {
    message.error(errorText(error))
  } finally {
    saving.value = false
  }
}

async function probe() {
  probing.value = true
  try {
    health.value = await api.health()
  } catch (error) {
    health.value = { downloader: '?', ok: false, error: errorText(error) }
  } finally {
    probing.value = false
  }
}

const moduleLabels: Record<string, string> = {
  drive: '云盘 / 云下载接口',
  task_meta: '任务元数据',
  task_enums: '任务状态枚举',
  task_manager: '本地任务管理器',
  task_status: '本地任务状态',
  path: '路径工具',
  download_action: '下载到本地',
  download_kernel: '下载内核（主窗口）',
}
const pikpak = () =>
  settings.value!['downloader.pikpak_client'] as { port: number; exe_path: string; auto_start: boolean; start_hidden: boolean }

const acting = ref(false)
async function startClient() {
  acting.value = true
  try {
    message.info((await api.startDownloader()).message)
    setTimeout(probe, 4000)
  } catch (error) {
    message.error(errorText(error))
  } finally {
    acting.value = false
  }
}
function restartClient() {
  dialog.warning({
    title: '重启 PikPak',
    content: '会退出正在运行的 PikPak 并以调试端口重新启动。进行中的本地下载会暂停，客户端登录后由 anipik 自动继续。',
    positiveText: '重启',
    negativeText: '取消',
    onPositiveClick: async () => {
      acting.value = true
      try {
        message.info((await api.restartDownloader()).message)
        setTimeout(probe, 6000)
      } catch (error) {
        message.error(errorText(error))
      } finally {
        acting.value = false
      }
    },
  })
}
</script>

<template>
  <div class="page narrow">
    <div class="page-header"><h1>设置</h1></div>
    <n-spin v-if="!settings" style="width: 100%; margin-top: 60px" />
    <template v-else>
      <n-card title="下载器 · PikPak 客户端" size="small" class="section">
        <template #header-extra>
          <n-button size="small" :loading="probing" @click="probe">检测连接</n-button>
        </template>
        <div v-if="health" class="health">
          <n-tag :type="health.ok ? 'success' : 'error'" round>{{ health.ok ? '可用' : '不可用' }}</n-tag>
          <span v-if="health.version" class="muted mono">{{ health.version.match(/PikPak\/[\d.]+/)?.[0] ?? health.version }}</span>
        </div>
        <div v-if="health?.client" class="client">
          <span>进程 <b :class="health.client.process_running ? 'ok' : 'bad'">{{ health.client.process_running ? '运行中' : '未运行' }}</b></span>
          <span>调试端口 <b :class="health.client.port_open ? 'ok' : 'bad'">{{ health.client.port_open ? '已开启' : '未开启' }}</b></span>
          <span class="mono muted">{{ health.client.exe ?? '未找到 PikPak.exe' }}</span>
        </div>
        <n-alert v-if="health && !health.ok" type="error" :show-icon="false" style="margin: 10px 0">
          <template v-if="health.client?.process_running && !health.client.port_open">
            PikPak 正在运行，但不是以调试端口启动的。点「重启 PikPak」由 anipik 重新启动它。
          </template>
          <template v-else-if="health.client && !health.client.process_running">
            PikPak 没有运行。点「启动 PikPak」，或开启自动启动后由调度器在需要时启动。
          </template>
          <template v-else>{{ health.error || '部分客户端模块不可用，客户端可能已更新' }}</template>
        </n-alert>
        <div class="actions">
          <n-button size="small" type="primary" secondary :loading="acting" :disabled="health?.client?.port_open" @click="startClient">启动 PikPak</n-button>
          <n-button size="small" :loading="acting" :disabled="!health?.client?.process_running" @click="restartClient">重启 PikPak</n-button>
        </div>
        <div v-if="health?.modules" class="modules">
          <div v-for="(value, key) in health.modules" :key="key" class="module">
            <span :class="value === true ? 'ok' : 'bad'">{{ value === true ? '✓' : '✗' }}</span>
            {{ moduleLabels[key] ?? key }}
            <span v-if="value !== true" class="muted small">{{ value }}</span>
          </div>
        </div>
        <div class="form-grid" style="margin-top: 14px">
          <label>客户端路径</label>
          <div>
            <n-input v-model:value="pikpak().exe_path" :placeholder="health?.client?.exe ?? 'C:\\Program Files\\PikPak\\PikPak.exe'" clearable />
            <div class="muted small">留空则自动查找默认安装位置</div>
          </div>
          <label>自动启动</label>
          <div>
            <n-switch v-model:value="pikpak().auto_start" />
            <div class="muted small">anipik 启动时、以及有下载任务但客户端没运行时，自动以调试端口启动 PikPak</div>
          </div>
          <label>最小化到托盘</label>
          <div>
            <n-switch v-model:value="pikpak().start_hidden" />
            <div class="muted small">由 anipik 启动 / 重启时不弹出窗口，只在托盘显示（与客户端「开机自启」相同的方式），双击托盘图标可打开</div>
          </div>
          <label>调试端口</label>
          <n-input-number v-model:value="pikpak().port" :min="1" :max="65535" style="width: 140px" />
        </div>
      </n-card>

      <n-card title="下载" size="small" class="section">
        <div class="form-grid">
          <label>媒体库根目录</label>
          <div>
            <n-input v-model:value="settings.library_root" placeholder="N:\新番" />
            <div class="muted small">订阅的保存目录相对于这里</div>
          </div>
          <label>同时下载数</label>
          <n-input-number v-model:value="settings.max_active_jobs" :min="1" :max="50" style="width: 140px" />
          <label>失败重试次数</label>
          <n-input-number v-model:value="settings.max_attempts" :min="1" :max="20" style="width: 140px" />
        </div>
      </n-card>

      <n-card title="调度" size="small" class="section">
        <div class="form-grid">
          <label>扫描间隔</label>
          <div class="inline"><n-input-number v-model:value="settings.scan_interval" :min="60" :step="60" style="width: 140px" /> 秒</div>
          <label>进度轮询</label>
          <div class="inline"><n-input-number v-model:value="settings.poll_interval" :min="2" style="width: 140px" /> 秒</div>
          <label>连接失败上限</label>
          <div>
            <n-input-number v-model:value="settings.max_transient_errors" :min="1" style="width: 140px" />
            <div class="muted small">单个任务连续出错这么多次后转为「需要处理」</div>
          </div>
        </div>
      </n-card>

      <n-card title="通知 · Discord" size="small" class="section">
        <div class="form-grid">
          <label>启用</label>
          <n-switch v-model:value="settings['notify.discord.enabled']" />
        </div>
        <div class="muted small" style="margin-top: 8px">消息写入 Discord 机器人的队列（chatbot/notify_queue.yaml），机器人需单独运行。</div>
      </n-card>

      <div class="footer">
        <span class="muted mono">{{ status?.db }}</span>
        <n-button type="primary" :loading="saving" @click="save">保存设置</n-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.narrow {
  max-width: 860px;
}
.section {
  margin-bottom: 16px;
}
.client {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin-top: 12px;
  font-size: 13px;
}
.actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.health {
  display: flex;
  gap: 10px;
  align-items: center;
}
.modules {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 6px 14px;
  margin-top: 12px;
  font-size: 13px;
}
.ok {
  color: #18a058;
  font-weight: 700;
}
.bad {
  color: #d03050;
  font-weight: 700;
}
.small {
  font-size: 12px;
  margin-top: 4px;
}
.form-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 12px 14px;
  align-items: start;
}
.form-grid > label {
  padding-top: 6px;
  font-size: 14px;
  opacity: 0.85;
}
.inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 8px 0 30px;
  flex-wrap: wrap;
}
</style>
