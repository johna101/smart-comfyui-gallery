<script setup lang="ts">
import { computed } from 'vue'
import type { GalleryFile } from '@/types/gallery'
import { useGalleryStore } from '@/stores/gallery'
import { fileApi, mediaApi } from '@/api/gallery'

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
      <img
        v-if="!isVideo"
        loading="lazy"
        :src="thumbnailUrl"
        :alt="file.name"
        class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
      />
      <video
        v-else
        :poster="thumbnailUrl"
        preload="none"
        muted
        class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
      />

      <!-- Workflow badge / green dot -->
      <div v-if="hasWorkflow && !focusMode" class="absolute top-2 left-2">
        <span class="inline-flex items-center gap-1 bg-green-600/90 text-white text-xs font-medium px-2 py-0.5 rounded-full">
          <span class="text-[10px]">&#9881;</span> Workflow
        </span>
      </div>
      <div
        v-if="hasWorkflow && focusMode"
        class="absolute top-2 left-2 w-3 h-3 rounded-full bg-green-500 shadow-lg"
        title="Has workflow"
      />

      <!-- Favorite star overlay (focus mode) -->
      <div
        v-if="isFavorite && focusMode"
        class="absolute top-2 right-2 text-yellow-400 text-lg drop-shadow"
      >&#9733;</div>

      <!-- Duration overlay for videos -->
      <div v-if="isVideo && file.duration" class="absolute bottom-2 right-2 flex items-center gap-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded">
        <span class="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
        {{ file.duration }}
      </div>

      <!-- Animated badge -->
      <div v-if="isAnimated" class="absolute bottom-2 right-2 bg-purple-600/80 text-white text-xs px-1.5 py-0.5 rounded">
        GIF
      </div>

      <!-- Selection checkmark (focus mode: bottom-left) -->
      <button
        v-if="focusMode && selected"
        class="absolute bottom-2 left-2 w-7 h-7 rounded-full bg-white flex items-center justify-center shadow-lg"
        @click="handleCheckmark"
      >
        <span class="text-fuchsia-600 text-sm font-bold">&#10003;</span>
      </button>

      <!-- Play button overlay for videos -->
      <div v-if="isVideo" class="absolute bottom-2 left-2 bg-black/50 rounded-full p-1">
        <span class="text-white text-lg">&#9654;</span>
      </div>
    </div>

    <!-- Metadata (hidden in focus mode) — click selects/deselects -->
    <div v-if="!focusMode" class="p-3 space-y-1.5 cursor-pointer" @click="handleCheckmark">
      <p class="text-white text-sm font-medium truncate" :title="file.name">{{ file.name }}</p>
      <div class="flex flex-wrap gap-x-3 gap-y-0.5 text-neutral-400 text-xs">
        <span v-if="file.dimensions">&#128208; {{ file.dimensions }}</span>
        <span>&#128190; {{ fileSize }}</span>
      </div>
      <div class="text-neutral-500 text-xs">
        &#128197; {{ fileDate }}
      </div>

      <!-- Action buttons + selection toggle -->
      <div class="flex items-center gap-1 pt-1">
        <button
          class="p-1.5 rounded text-neutral-400 hover:text-yellow-400 hover:bg-neutral-800 transition-colors"
          :class="{ 'text-yellow-400': isFavorite }"
          title="Toggle Favorite"
          @click="toggleFavorite"
        >&#9733;</button>
        <a
          :href="mediaApi.fileUrl(file.id)"
          :download="file.name"
          class="p-1.5 rounded text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
          title="Download"
          @click.stop
        >&#128190;</a>
        <button
          class="p-1.5 rounded text-neutral-400 hover:text-red-400 hover:bg-neutral-800 transition-colors"
          title="Delete"
          @click="deleteFile"
        >&#128465;</button>

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
          <span v-if="selected" class="text-white text-xs">&#10003;</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";
.focus-selected {
  box-shadow: 0 0 0 4px #ffffff, 0 0 0 10px #FF00FF, 0 10px 40px rgba(0,0,0,0.8);
  z-index: 10;
}
</style>
