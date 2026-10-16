<script setup lang="ts">
import { computed, ref } from 'vue'
import { NTooltip } from 'naive-ui'
import type { Episode } from '../api'
import { backendPhase, episodeStatus } from '../util'

// One cell per episode number; click to select, shift+click to select a range.
const props = defineProps<{ episodes: Episode[]; total: number | null }>()
const selected = defineModel<number[]>('selected', { default: () => [] })

const byNumber = computed(() => new Map(props.episodes.map((e) => [e.number, e])))
const numbers = computed(() => {
  const known = props.episodes.map((e) => e.number)
  const max = Math.max(props.total ?? 0, ...known, 0)
  // Show 1..max; absolute numbering (e.g. 1100) would be too many cells, so then only known ones.
  if (max > 200) return [...known].sort((a, b) => a - b)
  return Array.from({ length: max }, (_, i) => i + 1)
})
const anchor = ref<number | null>(null)

function toggle(number: number, event: MouseEvent) {
  const set = new Set(selected.value)
  if (event.shiftKey && anchor.value !== null) {
    const [a, b] = [Math.min(anchor.value, number), Math.max(anchor.value, number)]
    numbers.value.filter((n) => n >= a && n <= b).forEach((n) => set.add(n))
  } else if (set.has(number)) {
    set.delete(number)
  } else {
    set.add(number)
  }
  anchor.value = number
  selected.value = [...set].sort((a, b) => a - b)
}

function cellClass(number: number) {
  const episode = byNumber.value.get(number)
  return [episode ? `s-${episode.status}` : 's-none', { selected: selected.value.includes(number) }]
}
</script>

<template>
  <div class="grid">
    <n-tooltip v-for="n in numbers" :key="n" :delay="300">
      <template #trigger>
        <button type="button" class="cell" :class="cellClass(n)" @click="toggle(n, $event)">
          <span class="num">{{ n }}</span>
          <span
            v-if="byNumber.get(n)?.status === 'downloading' && byNumber.get(n)?.job"
            class="fill"
            :style="{ width: `${byNumber.get(n)!.job!.progress}%` }"
          />
        </button>
      </template>
      <template v-if="byNumber.get(n)">
        <div><b>第{{ n }}集 · {{ episodeStatus[byNumber.get(n)!.status].label }}</b></div>
        <div v-if="byNumber.get(n)!.release_title" style="max-width: 360px">{{ byNumber.get(n)!.release_title }}</div>
        <div v-if="byNumber.get(n)!.job?.backend_phase">
          {{ backendPhase[byNumber.get(n)!.job!.backend_phase!] ?? byNumber.get(n)!.job!.backend_phase }}
          · {{ byNumber.get(n)!.job!.progress }}%
        </div>
        <div v-if="byNumber.get(n)!.job?.error" style="max-width: 360px">{{ byNumber.get(n)!.job!.error }}</div>
      </template>
      <template v-else>第{{ n }}集 · 未发现</template>
    </n-tooltip>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(46px, 1fr));
  gap: 6px;
}
.cell {
  position: relative;
  height: 40px;
  border-radius: 8px;
  border: 1px solid rgba(128, 128, 128, 0.25);
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}
.cell:hover {
  transform: translateY(-1px);
}
.num {
  position: relative;
  z-index: 1;
}
.fill {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 100%;
  background: rgba(32, 128, 240, 0.35);
}
.cell.selected {
  box-shadow: 0 0 0 2px #7c5cff;
}
.s-none {
  opacity: 0.45;
  border-style: dashed;
}
.s-done {
  background: rgba(24, 160, 88, 0.85);
  border-color: transparent;
  color: #fff;
}
.s-downloading {
  background: rgba(32, 128, 240, 0.18);
  border-color: rgba(32, 128, 240, 0.6);
}
.s-queued {
  background: rgba(124, 92, 255, 0.15);
  border-color: rgba(124, 92, 255, 0.6);
}
.s-failed {
  background: rgba(208, 48, 80, 0.85);
  border-color: transparent;
  color: #fff;
}
.s-needs_attention {
  background: rgba(240, 160, 32, 0.9);
  border-color: transparent;
  color: #fff;
}
.s-skipped {
  background: rgba(128, 128, 128, 0.18);
  text-decoration: line-through;
  opacity: 0.7;
}
</style>
