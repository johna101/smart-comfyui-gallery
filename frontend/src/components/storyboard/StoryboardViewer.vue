<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { GalleryFile } from '@/types/gallery'
import { mediaApi } from '@/api/gallery'

const props = defineProps<{
  file: GalleryFile
}>()

const emit = defineEmits<{ close: [] }>()

const frames = ref<string[]>([])
const loading = ref(true)
const error = ref('')
const zoomIndex = ref(-1)
const hdMode = ref(true)
const hiresLoading = ref(false)
const hiresUrl = ref<string | null>(null)
// Cache HD URLs so re-visiting a frame is instant
const hiresCache = ref<Record<number, string>>({})
// Video metadata for meaningful filenames
const totalVideoFrames = ref(0)
const videoFps = ref(0)
const videoDuration = ref(0)

// Load frames
onMounted(async () => {
  try {
    const res = await mediaApi.getStoryboard(props.file.id) as any
    if (res.status === 'success' && res.frames) {
      frames.value = res.frames
      totalVideoFrames.value = res.totalVideoFrames || 0
      videoFps.value = res.fps || 0
      videoDuration.value = res.duration || 0
    } else {
      error.value = res.message || 'Failed to generate storyboard'
    }
  } catch (e) {
    error.value = 'Network error loading storyboard'
  }
  loading.value = false
})

// Zoom navigation
function openZoom(index: number) {
  zoomIndex.value = index
  hiresUrl.value = hiresCache.value[index] || null
  hiresLoading.value = false
  if (hdMode.value && !hiresUrl.value) fetchHires(index)
}

function closeZoom() {
  zoomIndex.value = -1
  hiresUrl.value = null
  hiresLoading.value = false
}

function navigateZoom(dir: number) {
  if (frames.value.length === 0) return
  let next = zoomIndex.value + dir
  if (next < 0) next = frames.value.length - 1
  if (next >= frames.value.length) next = 0
  zoomIndex.value = next
  hiresUrl.value = hiresCache.value[next] || null
  hiresLoading.value = false
  if (hdMode.value && !hiresUrl.value) fetchHires(next)
}

function toggleHd() {
  hdMode.value = !hdMode.value
  if (hdMode.value && zoomIndex.value >= 0 && !hiresUrl.value) {
    fetchHires(zoomIndex.value)
  }
  if (!hdMode.value) {
    hiresUrl.value = null
  }
}

async function fetchHires(index: number) {
  if (hiresLoading.value) return
  // Check cache first
  if (hiresCache.value[index]) {
    hiresUrl.value = hiresCache.value[index]
    return
  }
  hiresLoading.value = true
  try {
    const url = mediaApi.storyboardHiresUrl(props.file.id, index)
    const img = new Image()
    img.onload = () => {
      hiresCache.value[index] = url
      // Only apply if still on the same frame
      if (zoomIndex.value === index && hdMode.value) {
        hiresUrl.value = url
      }
      hiresLoading.value = false
    }
    img.onerror = () => {
      hiresLoading.value = false
    }
    img.src = url
  } catch {
    hiresLoading.value = false
  }
}

function zoomStatusText() {
  const i = zoomIndex.value
  const total = frames.value.length
  const base = `${i + 1} / ${total}`
  if (i === 0) return `START  ·  ${base}`
  if (i === total - 1) return `${base}  ·  END`
  return base
}

async function downloadFrame() {
  const i = zoomIndex.value
  const src = hiresUrl.value || frames.value[i]
  if (!src) return

  const videoName = props.file.name.replace(/\.[^.]+$/, '') // strip extension
  const numFrames = frames.value.length
  const total = totalVideoFrames.value

  let filename: string
  if (total > 0) {
    const safeEnd = Math.max(0, videoDuration.value - 0.1)
    const timestamp = numFrames > 1 ? (safeEnd / (numFrames - 1)) * i : 0
    const frameNum = videoFps.value > 0 ? Math.round(timestamp * videoFps.value) + 1 : i + 1
    filename = `${videoName}_${frameNum}-of-${total}.png`
  } else {
    filename = `${videoName}_frame-${i + 1}-of-${numFrames}.png`
  }

  // Fetch, convert to lossless PNG via canvas, then download
  try {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = src
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('Failed to load image'))
    })

    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, 0, 0)

    canvas.toBlob((blob) => {
      if (!blob) return
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }, 'image/png')
  } catch (e) {
    console.error('Download failed:', e)
  }
}

// Keyboard
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    e.preventDefault()
    if (zoomIndex.value >= 0) { closeZoom(); return }
    emit('close')
    return
  }
  if (zoomIndex.value >= 0) {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.stopPropagation()
      e.preventDefault()
      navigateZoom(e.key === 'ArrowLeft' ? -1 : 1)
    }
  }
}

// Use capture phase so storyboard intercepts before lightbox/gallery handlers
onMounted(() => document.addEventListener('keydown', onKeydown, true))
onUnmounted(() => document.removeEventListener('keydown', onKeydown, true))
</script>

<template>
  <div class="fixed inset-0 z-[5000] bg-black/95 flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2 bg-black/80 border-b border-white/10 shrink-0">
      <h3 class="text-white text-sm font-medium">
        🎞️ Storyboard — {{ file.name }}
      </h3>
      <button
        class="text-white/70 hover:text-white text-xl cursor-pointer"
        @click="emit('close')"
        title="Close (Esc)"
      >✕</button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center h-full">
        <div class="text-white/50 text-sm">Extracting frames...</div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex items-center justify-center h-full">
        <div class="text-red-400 text-sm">{{ error }}</div>
      </div>

      <!-- Frame grid -->
      <div
        v-else
        class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3"
      >
        <div
          v-for="(url, i) in frames"
          :key="url"
          class="relative cursor-pointer group rounded-lg overflow-hidden bg-white/5 border border-white/5 hover:border-white/20 transition-colors"
          @click="openZoom(i)"
        >
          <img
            :src="url"
            loading="lazy"
            class="w-full object-contain"
          />
          <div class="absolute top-1.5 left-1.5 bg-black/60 text-white/60 text-[10px] px-1.5 py-0.5 rounded">
            {{ i + 1 }}/{{ frames.length }}
          </div>
        </div>
      </div>
    </div>

    <!-- Zoom overlay -->
    <div
      v-if="zoomIndex >= 0"
      class="fixed inset-0 z-[5001] bg-black flex items-center justify-center"
      @click.self="closeZoom"
    >
      <!-- Top bar: status + HD + close -->
      <div class="absolute top-0 left-0 right-0 flex items-center gap-3 px-4 py-2 z-10">
        <div class="text-xs px-2 py-0.5 rounded bg-black/50 text-white/50">
          {{ zoomStatusText() }}
        </div>
        <button
          class="text-xs px-2 py-0.5 rounded border cursor-pointer transition-colors"
          :class="hdMode
            ? 'border-green-500/40 bg-green-500/15 text-green-300 hover:bg-green-500/25'
            : 'border-white/15 bg-white/5 text-white/40 hover:bg-white/10 hover:text-white/70'"
          @click="toggleHd"
        >
          HD {{ hdMode ? 'ON' : 'OFF' }}
          <span v-if="hiresLoading" class="ml-1 animate-pulse">⏳</span>
        </button>
        <button
          class="text-xs px-2 py-0.5 rounded border cursor-pointer transition-colors
            border-blue-500/40 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20"
          @click="downloadFrame"
          title="Download this frame as PNG"
        >
          💾 Save
        </button>
        <div class="flex-1" />
        <button
          class="text-white/40 hover:text-white text-lg cursor-pointer"
          @click="closeZoom"
        >✕</button>
      </div>

      <!-- Navigation -->
      <button
        class="absolute left-4 top-1/2 -translate-y-1/2 text-4xl text-white/30 hover:text-white cursor-pointer z-10"
        @click="navigateZoom(-1)"
      >‹</button>
      <button
        class="absolute right-4 top-1/2 -translate-y-1/2 text-4xl text-white/30 hover:text-white cursor-pointer z-10"
        @click="navigateZoom(1)"
      >›</button>

      <!-- Frame (HD if available, otherwise low-res) -->
      <img
        :src="hiresUrl || frames[zoomIndex]"
        class="max-w-[90%] max-h-[90vh] object-contain"
      />
    </div>
  </div>
</template>
