<script setup lang="ts">
import { computed } from 'vue'
import type { GalleryFile } from '@/types/gallery'
import { useGalleryStore } from '@/stores/gallery'
import { fileApi, mediaApi } from '@/api/gallery'
import {
  Star, Ruler, HardDrive, Calendar, Trash2, Check, Download,
} from 'lucide-vue-next'
import LazyImage from './LazyImage.vue'

const props = defineProps<{
  file: GalleryFile
  selected: boolean
  focusMode: boolean
}>()

const emit = defineEmits<{
  select: [fileId: string, event: MouseEvent]
  open: [fileId: string]
}>()

const gallery = useGalleryStore()

const thumbnailUrl = computed(() => mediaApi.thumbnailUrl(props.file.id))
const isVideo = computed(() => props.file.type === 'video')
const isAnimated = computed(() => props.file.type === 'animated_image')
const hasWorkflow = computed(() => !!props.file.has_workflow)
const isFavorite = computed(() => !!props.file.is_favorite)

// Parse dimensions into aspect ratio bucket
const aspectClass = computed(() => {
  const dims = props.file.dimensions
  if (!dims) return 'aspect-[4/3]' // fallback

  const match = dims.match(/(\d+)\s*x\s*(\d+)/)
  if (!match) return 'aspect-[4/3]'

  const w = parseInt(match[1])
  const h = parseInt(match[2])
  if (w === 0 || h === 0) return 'aspect-[4/3]'

  const ratio = w / h

  // Buckets chosen to avoid extreme height variation in the grid
  if (ratio > 1.5)      return 'aspect-video'     // wide landscape (16:9, 2:1, etc.)
  if (ratio > 1.15)     return 'aspect-[4/3]'     // standard landscape
  if (ratio > 0.85)     return 'aspect-square'     // square-ish (1:1, 4:5ish)
  if (ratio > 0.6)      return 'aspect-[3/4]'     // portrait (3:4, 2:3)
  return 'aspect-[9/16]'                           // tall portrait (9:16)
})

const fileSize = computed(() => {
  const bytes = props.file.size
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
})

const fileDate = computed(() => {
  if (!props.file.mtime) return ''
  const d = new Date(props.file.mtime * 1000)
  return d.toLocaleDateString('en-GB', {
    day: '2-digit', month: '2-digit', year: 'numeric'
  }) + ', ' + d.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit'
  })
})

function handleThumbnailClick(e: MouseEvent) {
  if (props.focusMode) {
    emit('select', props.file.id, e)
  } else {
    emit('open', props.file.id)
  }
}

function handleCheckmark(e: MouseEvent) {
  e.stopPropagation()
  emit('select', props.file.id, e)
}

async function toggleFavorite(e: MouseEvent) {
  e.stopPropagation()
  try {
    const res = await fileApi.toggleFavorite(props.file.id)
    gallery.updateFile(props.file.id, { is_favorite: res.is_favorite ? 1 : 0 })
  } catch (err) {
    console.error('Failed to toggle favorite:', err)
  }
}

async function deleteFile(e: MouseEvent) {
  e.stopPropagation()
  if (!confirm(`Delete ${props.file.name}?`)) return
  try {
    await fileApi.deleteFile(props.file.id)
    gallery.removeFile(props.file.id)
  } catch (err) {
    console.error('Failed to delete:', err)
  }
}
</script>

<template>
  <div
    class="gallery-card group relative rounded-xl bg-neutral-900 transition-all duration-200 hover:-translate-y-1 hover:shadow-[0_0_0_2px_rgba(255,255,255,0.5)] overflow-hidden"
    :class="{
      'ring-2 ring-white ring-offset-2 ring-offset-black': selected && !focusMode,
      'focus-selected': selected && focusMode,
      'cursor-pointer': focusMode,
    }"
  >
    <!-- Thumbnail (click opens lightbox or toggles selection in focus mode) -->
    <div
      class="relative bg-neutral-800 overflow-hidden cursor-pointer"
      :class="aspectClass"
      @click="handleThumbnailClick"
    >
      <LazyImage
        v-if="!isVideo"
        :src="thumbnailUrl"
        :alt="file.name"
      />
      <LazyImage
        v-else
        :src="thumbnailUrl"
        :alt="file.name"
      />

      <!-- Top-left indicators (focus mode: workflow dot + duration; normal: duration) -->
      <div class="absolute top-2 left-2 flex items-center gap-1.5">
        <div
          v-if="hasWorkflow && focusMode"
          class="w-3 h-3 rounded-full bg-workflow shadow-lg"
          title="Has workflow"
        />
        <div v-if="isVideo && file.duration" class="flex items-center gap-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
          <span class="w-1.5 h-1.5 rounded-full bg-media-video inline-block" />
          {{ file.duration }}
        </div>
        <div v-if="isAnimated" class="bg-media-video-bg text-media-video text-xs px-1.5 py-0.5 rounded border border-media-video/20">
          GIF
        </div>
      </div>

      <!-- Favorite star overlay (focus mode) -->
      <div
        v-if="isFavorite && focusMode"
        class="absolute top-2 right-2 text-favorite drop-shadow"
      ><Star :size="18" class="fill-current" /></div>

      <!-- Selection checkmark (focus mode: bottom-left) -->
      <button
        v-if="focusMode && selected"
        class="absolute bottom-2 left-2 w-7 h-7 rounded-full bg-white flex items-center justify-center shadow-lg"
        @click="handleCheckmark"
      >
        <Check :size="14" class="text-fuchsia-600" />
      </button>

    </div>

    <!-- Metadata (hidden in focus mode) — click selects/deselects -->
    <div v-if="!focusMode" class="p-3 space-y-1.5 cursor-pointer" @click="handleCheckmark">
      <p class="text-white text-sm font-medium truncate" :title="file.name">{{ file.name }}</p>
      <div class="flex items-center gap-x-3 text-neutral-400 text-xs">
        <span v-if="file.dimensions" class="inline-flex items-center gap-0.5"><Ruler :size="11" /> {{ file.dimensions }}</span>
        <span class="inline-flex items-center gap-0.5"><HardDrive :size="11" /> {{ fileSize }}</span>
        <span class="ml-auto flex items-center gap-1">
          <span :class="isVideo ? 'pill-video' : isAnimated ? 'pill-video' : 'pill-image'">{{ isVideo ? 'VID' : isAnimated ? 'GIF' : 'IMG' }}</span>
          <span v-if="hasWorkflow" class="pill-workflow">WF</span>
        </span>
      </div>
      <div class="text-neutral-500 text-xs inline-flex items-center gap-0.5">
        <Calendar :size="11" /> {{ fileDate }}
      </div>

      <!-- Action buttons + selection toggle -->
      <div class="flex items-center gap-1 pt-1">
        <button
          class="p-1.5 rounded text-neutral-400 hover:text-favorite hover:bg-neutral-800 transition-colors"
          :class="{ 'text-favorite': isFavorite }"
          title="Toggle Favorite"
          @click="toggleFavorite"
        ><Star :size="14" :class="{ 'fill-current': isFavorite }" /></button>
        <a
          :href="mediaApi.fileUrl(file.id)"
          :download="file.name"
          class="p-1.5 rounded text-neutral-400 hover:text-file hover:bg-neutral-800 transition-colors"
          title="Download"
          @click.stop
        ><Download :size="14" /></a>
        <button
          class="p-1.5 rounded text-neutral-400 hover:text-danger hover:bg-neutral-800 transition-colors"
          title="Delete"
          @click="deleteFile"
        ><Trash2 :size="14" /></button>

        <!-- Selection checkmark (right side of action row) -->
        <button
          class="ml-auto w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all"
          :class="selected
            ? 'bg-blue-500 border-blue-500'
            : 'border-neutral-600 opacity-0 group-hover:opacity-100 hover:border-white/70'"
          :style="selected ? 'opacity: 1' : ''"
          title="Select"
          @click="handleCheckmark"
        >
          <Check v-if="selected" :size="12" class="text-white" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.focus-selected {
  box-shadow: 0 0 0 4px rgba(255,255,255,0.7), 0 0 0 5px rgba(110, 39, 163, 0.71), 0 8px 24px rgba(0,0,0,0.5);
  z-index: 10;
}
.pill-image {
  @apply px-1.5 py-px rounded-full text-[10px] font-medium leading-none border;
  background: var(--color-media-image-bg);
  color: var(--color-media-image);
  border-color: color-mix(in srgb, var(--color-media-image) 20%, transparent);
}
.pill-video {
  @apply px-1.5 py-px rounded-full text-[10px] font-medium leading-none border;
  background: var(--color-media-video-bg);
  color: var(--color-media-video);
  border-color: color-mix(in srgb, var(--color-media-video) 20%, transparent);
}
.pill-workflow {
  @apply px-1.5 py-px rounded-full text-[10px] font-medium leading-none border;
  background: var(--color-workflow-bg);
  color: var(--color-workflow);
  border-color: color-mix(in srgb, var(--color-workflow) 20%, transparent);
}
</style>
