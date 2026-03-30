<script setup lang="ts">
import { computed } from 'vue'
import type { GalleryFile, FolderInfo } from '@/types/gallery'
import { mediaApi } from '@/api/gallery'
import { useGalleryStore } from '@/stores/gallery'
import {
  FolderOpen, ZoomIn, ZoomOut, Star, Download, Pencil, Trash2,
  ClipboardList, ClipboardCopy, ArrowDownToLine, ArrowUpFromLine,
  Film, Eye, ExternalLink, EyeOff, X,
} from 'lucide-vue-next'

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
  sendToInput: []
  sendWorkflow: []
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
  if (props.file.dimensions) parts.push(props.file.dimensions)
  if (props.file.size) {
    const kb = props.file.size / 1024
    parts.push(kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`)
  }
  if (props.file.duration) parts.push(props.file.duration)
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
          <FolderOpen :size="14" class="mr-1 shrink-0" />
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
        class="text-white/70 hover:text-white ml-4 p-1"
        title="Close (Esc)"
        @click="emit('close')"
      >
        <X :size="22" />
      </button>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 flex-wrap">
      <!-- Zoom -->
      <button
        class="lb-btn"
        title="Zoom in (+)"
        @click="emit('zoomIn')"
      ><ZoomIn :size="18" /></button>
      <button
        class="lb-btn"
        title="Zoom out (-)"
        @click="emit('zoomOut')"
      ><ZoomOut :size="18" /></button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Favorite -->
      <button
        class="lb-btn"
        :class="{ 'lb-favorite': isFavorite }"
        :title="isFavorite ? 'Remove Favorite (F)' : 'Add Favorite (F)'"
        @click="emit('toggleFavorite')"
      ><Star :size="18" :class="{ 'fill-current': isFavorite }" /></button>

      <!-- File -->
      <a
        v-if="file"
        :href="mediaApi.downloadUrl(file.id)"
        class="lb-btn lb-file inline-block"
        title="Download (S)"
        download
      ><Download :size="18" /></a>
        <button
          v-if="gallery.hasInputPath"
          class="lb-btn lb-file inline-block"
          title="Send to ComfyUI Input (Q)"
          @click="emit('sendToInput')"
        ><ArrowUpFromLine :size="18" /></button>
      <!-- Rename -->
      <button
        class="lb-btn lb-file inline-block"
        title="Rename (R)"
        @click="emit('rename')"
      ><Pencil :size="18" /></button>

      <!-- Delete -->
      <button
        class="lb-btn lb-danger"
        title="Delete (D)"
        @click="emit('delete')"
      ><Trash2 :size="18" /></button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Workflow buttons -->
      <template v-if="hasWorkflow">
        <a
          :href="mediaApi.workflowUrl(file!.id)"
          class="lb-btn lb-workflow inline-block"
          title="Download Workflow (W)..."
          download
        ><Download :size="18" /></a>
        <button
          class="lb-btn lb-workflow"
          title="Copy Workflow (C)"
          @click="emit('copyWorkflow')"
        ><ClipboardCopy :size="18" /></button>
        <button
          v-if="gallery.hasWorkflowsPath && hasWorkflow"
          class="lb-btn lb-workflow"
          title="Send Workflow to ComfyUI (Shift+W)"
          @click="emit('sendWorkflow')"
        ><ArrowUpFromLine :size="18" /></button>
<!--        <button-->
<!--          class="lb-btn lb-metadata"-->
<!--          title="Node Summary (N)"-->
<!--          @click="emit('nodeSummary')"-->
<!--        ><ClipboardList :size="18" /></button>-->
      </template>

      <!-- Storyboard -->
      <button
        v-if="canStoryboard"
        class="lb-btn"
        title="Storyboard (E)"
        @click="emit('storyboard')"
      ><Film :size="18" /></button>

      <!-- Info / Metadata panel -->
      <button
        class="lb-btn lb-metadata"
        title="File Info & Prompt (I)"
        @click="emit('toggleMeta')"
      ><Eye :size="18" /></button>

      <div class="w-px h-6 bg-white/20 mx-1" />

      <!-- Open in new tab -->
      <a
        v-if="file"
        :href="mediaApi.fileUrl(file.id)"
        target="_blank"
        class="lb-btn inline-block"
        title="Open in New Tab (O)"
      ><ExternalLink :size="18" /></a>

      <!-- Toggle UI -->
      <button
        class="lb-btn"
        title="Toggle UI (H)"
        @click="emit('toggleUi')"
      ><EyeOff :size="18" /></button>
    </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.lb-btn {
  @apply text-white/70 hover:text-white hover:bg-white/10 rounded-lg px-2.5 py-1.5 text-base transition-colors cursor-pointer no-underline;
}
.lb-btn.lb-workflow {
  color: var(--color-workflow);
  &:hover { color: var(--color-workflow-hover); }
}
.lb-btn.lb-metadata {
  color: var(--color-metadata);
  &:hover { color: var(--color-metadata-hover); }
}
.lb-btn.lb-file {
  color: var(--color-file);
  &:hover { color: var(--color-file-hover); }
}
.lb-btn.lb-danger {
  color: var(--color-danger);
  &:hover { color: var(--color-danger-hover); }
}
.lb-btn.lb-favorite {
  color: var(--color-favorite);
  &:hover { color: var(--color-favorite-hover); }
}
</style>
