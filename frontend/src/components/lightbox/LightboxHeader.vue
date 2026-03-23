<script setup lang="ts">
import { computed } from 'vue'
import type { GalleryFile, FolderInfo } from '@/types/gallery'
import { mediaApi } from '@/api/gallery'
import { useGalleryStore } from '@/stores/gallery'

const props = defineProps<{
  file: GalleryFile | null
  zoomPercent: number
  uiHidden: boolean
}>()

const emit = defineEmits<{
  close: []
  delete: []
  rename: []
  toggleFavorite: []
  toggleUi: []
  zoomIn: []
  zoomOut: []
  nodeSummary: []
  copyWorkflow: []
  storyboard: []
  navigateFolder: [folderKey: string]
  toggleMeta: []
}>()

const gallery = useGalleryStore()

const fileName = computed(() => props.file?.name ?? '')

/** Build breadcrumb trail from folder key up to root */
const folderBreadcrumbs = computed(() => {
  if (!props.file) return []
  const folderKey = gallery.folderKeyForFile(props.file)
  if (!folderKey) return []

  const crumbs: Array<{ key: string; name: string }> = []
  let current: string | null = folderKey
  while (current && current !== '_root_') {
    const f: FolderInfo | undefined = gallery.folders[current]
    if (!f) break
    crumbs.unshift({ key: current, name: f.display_name })
    current = f.parent ?? null
  }
  // Add root
  crumbs.unshift({ key: '_root_', name: 'Main' })
  return crumbs
})

const resolution = computed(() => {
  if (!props.file) return ''
  const parts: string[] = []
  if (props.file.dimensions) parts.push(`📐 ${props.file.dimensions}`)
  if (props.file.size) {
    const kb = props.file.size / 1024
    parts.push(kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`)
  }
  if (props.file.duration) parts.push(`⏱️ ${props.file.duration}`)
  return parts.join('  ·  ')
})

const hasWorkflow = computed(() => !!props.file?.has_workflow)

const canStoryboard = computed(() =>
  gallery.ffmpegAvailable &&
  (props.file?.type === 'video' || props.file?.type === 'animated_image')
)

const isFavorite = computed(() => !!props.file?.is_favorite)
</script>

<template>
  <div
    v-show="!uiHidden"
    class="absolute top-0 left-0 z-20 p-3 max-w-[90%]"
  >
    <div class="bg-black/50 backdrop-blur-sm rounded-xl px-4 py-3">
    <!-- Title row -->
    <div class="flex items-center justify-between mb-2">
      <div class="min-w-0 flex-1">
        <h2 class="text-white text-lg font-medium truncate">
          {{ fileName }}
          <span class="text-white/50 text-sm ml-2">{{ zoomPercent }}%</span>
        </h2>
        <p class="text-white/60 text-sm truncate flex items-center gap-0.5">
          <span class="mr-1">📂</span>
          <template v-for="(crumb, i) in folderBreadcrumbs" :key="crumb.key">
            <span
              class="cursor-pointer hover:text-white/90 transition-colors"
              @click="emit('navigateFolder', crumb.key)"
            >{{ crumb.name }}</span>
            <span v-if="i < folderBreadcrumbs.length - 1" class="text-white/30 mx-0.5">/</span>
          </template>
          <span v-if="resolution" class="ml-3 text-white/40">{{ resolution }}</span>
        </p>
      </div>
      <button
        class="text-white/70 hover:text-white text-2xl ml-4 p-1"
        title="Close (Esc)"
        @click="emit('close')"
      >
        ✕
      </button>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 flex-wrap">
      <!-- Zoom -->
      <button
        class="lb-btn"
        title="Zoom in (+)"
        @click="emit('zoomIn')"
      >🔍+</button>
      <button
        class="lb-btn"
        title="Zoom out (-)"
        @click="emit('zoomOut')"
      >🔍−</button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Favorite -->
      <button
        class="lb-btn"
        :class="{ 'text-yellow-400': isFavorite }"
        :title="isFavorite ? 'Remove Favorite (F)' : 'Add Favorite (F)'"
        @click="emit('toggleFavorite')"
      >{{ isFavorite ? '★' : '☆' }}</button>

      <!-- Download -->
      <a
        v-if="file"
        :href="mediaApi.downloadUrl(file.id)"
        class="lb-btn inline-block"
        title="Download (S)"
        download
      >💾</a>

      <!-- Rename -->
      <button
        class="lb-btn"
        title="Rename (R)"
        @click="emit('rename')"
      >✏️</button>

      <!-- Delete -->
      <button
        class="lb-btn text-red-400 hover:text-red-300"
        title="Delete (D)"
        @click="emit('delete')"
      >🗑️</button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Workflow buttons -->
      <template v-if="hasWorkflow">
        <a
          :href="mediaApi.workflowUrl(file!.id)"
          class="lb-btn inline-block"
          title="Download Workflow (W)"
          download
        >⚙️</a>
        <button
          class="lb-btn"
          title="Node Summary (N)"
          @click="emit('nodeSummary')"
        >📋</button>
        <button
          class="lb-btn"
          title="Copy Workflow (C)"
          @click="emit('copyWorkflow')"
        >📎</button>
      </template>

      <!-- Storyboard -->
      <button
        v-if="canStoryboard"
        class="lb-btn"
        title="Storyboard (E)"
        @click="emit('storyboard')"
      >🎞️</button>

      <!-- Info / Metadata panel -->
      <button
        class="lb-btn"
        title="File Info & Prompt (I)"
        @click="emit('toggleMeta')"
      >👁️</button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Open in new tab -->
      <a
        v-if="file"
        :href="mediaApi.fileUrl(file.id)"
        target="_blank"
        class="lb-btn inline-block"
        title="Open in New Tab (O)"
      >↗️</a>

      <!-- Toggle UI -->
      <button
        class="lb-btn"
        title="Toggle UI (H)"
        @click="emit('toggleUi')"
      >👁️</button>
    </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.lb-btn {
  @apply text-white/70 hover:text-white hover:bg-white/10 rounded-lg px-2.5 py-1.5 text-base transition-colors cursor-pointer no-underline;
}
</style>
