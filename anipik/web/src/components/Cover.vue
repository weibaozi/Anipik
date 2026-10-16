<script setup lang="ts">
import { ref, watch } from 'vue'

// Poster with a gradient fallback (initials) when there is no cover or it fails to load.
const props = defineProps<{ src?: string | null; name: string; radius?: number }>()
const failed = ref(false)
watch(() => props.src, () => (failed.value = false))
const initials = (name: string) => name.replace(/[\s\[\]【】()（）!！]/g, '').slice(0, 2)
</script>

<template>
  <div class="cover" :style="{ borderRadius: `${radius ?? 8}px` }">
    <img v-if="src && !failed" :src="src" :alt="name" loading="lazy" referrerpolicy="no-referrer" @error="failed = true" />
    <div v-else class="cover-placeholder fill">{{ initials(name) }}</div>
    <slot />
  </div>
</template>

<style scoped>
.cover {
  position: relative;
  aspect-ratio: 2 / 3;
  overflow: hidden;
  background: rgba(128, 128, 128, 0.12);
}
img,
.fill {
  width: 100%;
  height: 100%;
}
img {
  object-fit: cover;
  display: block;
}
</style>
