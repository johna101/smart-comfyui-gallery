<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'
import { useUiStore } from '@/stores/ui'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useSelection } from '@/composables/useSelection'
import GalleryCard from './GalleryCard.vue'

const RENDER_BATCH = 100

const gallery = useGalleryStore()
const preferences = usePreferencesStore()
const ui = useUiStore()

const sentinel = ref<HTMLElement | null>(null)
const { loading, exhausted } = useInfiniteScroll(sentinel)
const { handleSelect } = useSelection()

const focusMode = computed(() => preferences.focusMode)
const gridItemSize = computed(() => preferences.gridSize === 'compact' ? 240 : 320)

// Client-side render limit — only render a slice of filteredFiles
const renderLimit = ref(RENDER_BATCH)

// The files actually rendered in the DOM
const visibleFiles = computed(() => gallery.filteredFiles.slice(0, renderLimit.value))
const allRendered = computed(() => renderLimit.value >= gallery.filteredFiles.length)

// Reset render limit and force grid re-key when filtered results change
// The re-key destroys old <img> elements, cancelling in-flight thumbnail fetches
const gridKey = ref(0)
watch(() => gallery.filteredFiles, () => {
  renderLimit.value = RENDER_BATCH
  gridKey.value++
})

// Intersection observer for "load more" on scroll
const loadMoreSentinel = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && !allRendered.value) {
      renderLimit.value += RENDER_BATCH
    }
  }, { rootMargin: '400px' })
})

// Watch for sentinel element to observe
watch(loadMoreSentinel, (el, oldEl) => {
  if (oldEl) observer?.unobserve(oldEl)
  if (el) observer?.observe(el)
})

onUnmounted(() => observer?.disconnect())

function openLightbox(fileId: string) {
  const index = gallery.filteredFiles.findIndex(f => f.id === fileId)
  if (index >= 0) {
    ui.openLightbox(fileId, index)
  }
}
</script>

<template>
  <div class="gallery-grid-wrapper">
    <!-- Empty state -->
    <div
      v-if="gallery.filteredFiles.length === 0 && !loading"
      class="flex items-center justify-center min-h-[50vh] text-neutral-500 text-lg"
    >
      No files in this folder
    </div>

    <!-- Grid (key changes on filter to cancel in-flight thumbnail fetches) -->
    <div
      v-else
      :key="gridKey"
      class="grid gap-4 p-4"
      :class="focusMode ? 'gallery-focus' : ''"
      :style="{
        gridTemplateColumns: `repeat(auto-fill, minmax(${gridItemSize}px, 1fr))`,
        alignItems: 'start',
      }"
    >
      <GalleryCard
        v-for="file in visibleFiles"
        :key="file.id"
        :file="file"
        :selected="gallery.selectedFiles.has(file.id)"
        :focus-mode="focusMode"
        @select="handleSelect"
        @open="openLightbox"
      />
    </div>

    <!-- Render-more sentinel (client-side pagination) -->
    <div ref="loadMoreSentinel" class="h-1" />

    <!-- Server infinite scroll sentinel -->
    <div ref="sentinel" class="h-1" />

    <!-- Loading indicator -->
    <div v-if="loading || !allRendered" class="flex justify-center py-8">
      <div class="w-8 h-8 border-2 border-neutral-600 border-t-white rounded-full animate-spin" />
    </div>

    <!-- End of results -->
    <div v-if="allRendered && gallery.filteredFiles.length > 0 && exhausted" class="text-center text-neutral-600 text-sm py-4">
      {{ gallery.filteredFiles.length }} files
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.gallery-grid-wrapper {
  @apply select-none;
}
.gallery-focus :deep(.gallery-card) {
  @apply rounded-sm;
}
</style>
