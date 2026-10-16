<script setup lang="ts">
import { computed } from 'vue'
import {
  NConfigProvider,
  NDialogProvider,
  NGlobalStyle,
  NLoadingBarProvider,
  NMessageProvider,
  darkTheme,
  dateZhCN,
  useOsTheme,
  zhCN,
  type GlobalThemeOverrides,
} from 'naive-ui'
import AppShell from './components/AppShell.vue'
import { theme } from './store'

const osTheme = useOsTheme()
const dark = computed(() => (theme.pref === 'auto' ? osTheme.value === 'dark' : theme.pref === 'dark'))

const overrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#7c5cff',
    primaryColorHover: '#9278ff',
    primaryColorPressed: '#6a48f0',
    primaryColorSuppl: '#9278ff',
    borderRadius: '8px',
  },
}
</script>

<template>
  <n-config-provider :theme="dark ? darkTheme : null" :theme-overrides="overrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-global-style />
    <n-loading-bar-provider>
      <n-message-provider>
        <n-dialog-provider>
          <app-shell :dark="dark" />
        </n-dialog-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
