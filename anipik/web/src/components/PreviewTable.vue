<script setup lang="ts">
import { computed, h } from 'vue'
import { NDataTable, NTag, type DataTableColumns } from 'naive-ui'
import type { PreviewItem } from '../api'
import { episodeStatus } from '../util'

// Search results with how each title parses / filters. Unmatched rows are dimmed.
const props = defineProps<{ items: PreviewItem[]; loading?: boolean; maxHeight?: number }>()

type Row = PreviewItem & { key: number; first: boolean; rank: number }

// Display order: will download, already has a status, duplicate, unrecognized / batch, filtered out.
function rank(item: PreviewItem, first: boolean) {
  if (!item.matched) return 4
  if (item.batch || item.episode === null) return 3
  if (item.status) return 1
  return first ? 0 : 2
}

// Like the scheduler: feeds are newest first and the first matching release per episode wins,
// so "first" is decided in feed order before sorting (sort is stable: feed order within a group).
const rows = computed<Row[]>(() => {
  const seen = new Set<number>()
  return props.items
    .map((item, key) => {
      const usable = item.matched && item.episode !== null && !item.batch
      const first = usable && !seen.has(item.episode!)
      if (usable) seen.add(item.episode!)
      return { ...item, key, first, rank: rank(item, first) }
    })
    .sort((a, b) => a.rank - b.rank)
})

const columns = computed<DataTableColumns<Row>>(() => [
  {
    title: '集',
    key: 'episode',
    width: 64,
    render: (row) =>
      row.batch ? h(NTag, { size: 'small', bordered: false }, () => '合集') : row.episode ?? h('span', { class: 'muted' }, '?'),
  },
  {
    title: '字幕组',
    key: 'group',
    width: 130,
    ellipsis: { tooltip: true },
    render: (row) => row.group ?? '—',
  },
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  {
    title: '状态',
    key: 'status',
    width: 120,
    render: (row) => {
      if (!row.matched) return h('span', { class: 'muted' }, '被过滤')
      if (row.batch) return h('span', { class: 'muted' }, '合集不下载')
      if (row.episode === null) return h('span', { class: 'muted' }, '无法识别集数')
      if (row.status) {
        const s = episodeStatus[row.status]
        return h(NTag, { size: 'small', type: s.type, bordered: false }, () => s.label)
      }
      if (!row.first) return h('span', { class: 'muted' }, '同集已有更早匹配')
      return h(NTag, { size: 'small', type: 'primary', bordered: false }, () => '会下载')
    },
  },
])
const rowProps = (row: Row) => ({ style: row.first || row.status ? '' : 'opacity:.45' })
</script>

<template>
  <n-data-table
    size="small"
    :columns="columns"
    :data="rows"
    :row-key="(row: Row) => row.key"
    :loading="loading"
    :max-height="maxHeight ?? 360"
    :row-props="rowProps"
    :bordered="false"
    virtual-scroll
  />
</template>
