<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import type { GalleryFile } from '@/types/gallery'
import { mediaApi } from '@/api/gallery'
import { useGalleryStore } from '@/stores/gallery'
import { AlertTriangle, Music } from 'lucide-vue-next'

const props = defineProps<{
  file: GalleryFile | null
  transformStyle: string
  isDragging: boolean
}>()

const emit = defineEmits<{
  dragStart: [e: MouseEvent]
  dragMove: [e: MouseEvent]
  dragEnd: []
  wheel: [e: WheelEvent]
}>()

const gallery = useGalleryStore()

const loading = ref(true)
const error = ref(false)
const videoRef = ref<HTMLVideoElement | null>(null)

const isVideo = computed(() => props.file?.type === 'video')
const isAudio = computed(() => props.file?.type === 'audio')
const isImage = computed(() =>
  props.file?.type === 'image' || props.file?.type === 'animated_image'
)

/** Determine video source — transcode only non-native formats */
function getVideoSrc(file: GalleryFile): string {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  // Formats browsers can't play natively — need ffmpeg transcode
  const needsTranscode = ['mkv', 'avi', 'wmv', 'flv'].includes(ext)

  if (gallery.ffmpegAvailable && needsTranscode) {
    return mediaApi.streamUrl(file.id)
  }
  // MP4, WebM, MOV: serve directly with range request support (any size)
  return mediaApi.fileUrl(file.id)
}

function onLoaded() {
  loading.value = false
  error.value = false
}

function onError() {
  loading.value = false
  error.value = true
}

// Pause media when file changes
watch(() => props.file, () => {
  loading.value = true
  error.value = false
  if (videoRef.value) {
    videoRef.value.pause()
  }
})

onUnmounted(() => {
  if (videoRef.value) {
    videoRef.value.pause()
    videoRef.value.src = ''
  }
})

defineExpose({ videoRef })
</script>

<template>
  <div
    class="relative flex items-center justify-center w-full h-full overflow-hidden select-none"
    :class="{ 'cursor-grab': !isDragging, 'cursor-grabbing': isDragging }"
    @mousedown="emit('dragStart', $event)"
    @mousemove="emit('dragMove', $event)"
    @mouseup="emit('dragEnd')"
    @mouseleave="emit('dragEnd')"
    @wheel.prevent="emit('wheel', $event)"
  >
    <!-- Loading spinner -->
    <div
      v-if="loading && file"
      class="absolute inset-0 flex items-center justify-center z-10"
    >
      <div class="w-12 h-12 border-4 border-white/30 border-t-white rounded-full animate-spin" />
    </div>

    <!-- Error state -->
    <div
      v-if="error"
      class="text-red-400 text-center p-8"
    >
      <AlertTriangle :size="48" class="mb-2" />
      <p>Error loading media</p>
    </div>

    <!-- Image -->
    <img
      v-if="file && isImage"
      :src="mediaApi.fileUrl(file.id)"
      :alt="file.name"
      class="max-w-full max-h-full object-contain transition-none"
      :style="{ transform: transformStyle }"
      draggable="false"
      @load="onLoaded"
      @error="onError"
    >

    <!-- Video -->
    <video
      v-else-if="file && isVideo"
      ref="videoRef"
      :src="getVideoSrc(file)"
      class="max-w-full max-h-full object-contain"
      :style="{ transform: transformStyle }"
      controls
      autoplay
      loop
      @loadeddata="onLoaded"
      @error="onError"
    />

    <!-- Audio -->
    <div
      v-else-if="file && isAudio"
      class="flex flex-col items-center gap-6 p-8"
    >
      <Music :size="96" class="text-white/60" />
      <audio
        :src="mediaApi.fileUrl(file.id)"
        controls
        autoplay
        @loadeddata="onLoaded"
        @error="onError"
      />
    </div>

    <!-- Empty state -->
    <div
      v-if="!file"
      class="text-white/50 text-center"
    >
      No file selected
    </div>
  </div>
</template>
