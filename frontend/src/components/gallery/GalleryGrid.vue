<script setup lang="ts">
import { ref, computed } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'
import { useUiStore } from '@/stores/ui'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useSelection } from '@/composables/useSelection'
import GalleryCard from './GalleryCard.vue'

const gallery = useGalleryStore()
const preferences = usePreferencesStore()
const ui = useUiStore()

const sentinel = ref<HTMLElement | null>(null)
const { loading, exhausted } = useInfiniteScroll(sentinel)
const { handleSelect } = useSelection()

const focusMode = computed(() => preferences.focusMode)
const gridItemSize = computed(() => preferences.gridSize === 'compact' ? 240 : 320)

function openLightbox(fileId: string) {
  const index = gallery.files.findIndex(f => f.id === fileId)
  if (index >= 0) {
    ui.openLightbox(fileId, index)
  }
}
</script>

<template>
  <div class="gallery-grid-wrapper">
    <!-- Empty state -->
    <div
      v-if="gallery.files.length === 0 && !loading"
      class="flex items-center justify-center min-h-[50vh] text-neutral-500 text-lg"
    >
      No files in this folder
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid gap-8 p-8"
      :class="focusMode ? 'gallery-focus' : ''"
      :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${gridItemSize}px, 1fr))` }"
    >
      <GalleryCard
        v-for="file in gallery.files"
        :key="file.id"
        :file="file"
        :selected="gallery.selectedFiles.has(file.id)"
        :focus-mode="focusMode"
        @select="handleSelect"
        @open="openLightbox"
      />
    </div>

    <!-- Infinite scroll sentinel -->
    <div ref="sentinel" class="h-1" />

    <!-- Loading indicator -->
    <div v-if="loading" class="flex justify-center py-8">
      <div class="w-8 h-8 border-2 border-neutral-600 border-t-white rounded-full animate-spin" />
    </div>

    <!-- End of results -->
    <div v-if="exhausted && gallery.files.length > 0" class="text-center text-neutral-600 text-sm py-4">
      All {{ gallery.totalFiles }} files loaded
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.gallery-focus :deep(.gallery-card) {
  @apply rounded-sm;
}
</style>
