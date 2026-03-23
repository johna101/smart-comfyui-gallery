<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useThumbnailCache } from '@/composables/useThumbnailCache'

const props = defineProps<{
  src: string
  alt?: string
}>()

const thumbCache = useThumbnailCache()
const blobUrl = ref('')
let abortController: AbortController | null = null
let observer: IntersectionObserver | null = null
let visibilityTimer: ReturnType<typeof setTimeout> | null = null
const containerRef = ref<HTMLElement | null>(null)

onMounted(() => {
  // Check cache first — instant display if we've seen this thumbnail before
  const cached = thumbCache.get(props.src)
  if (cached) {
    blobUrl.value = cached
    return // No observer needed
  }

  if (!containerRef.value) return

  observer = new IntersectionObserver((entries) => {
    const entry = entries[0]
    if (entry?.isIntersecting) {
      // Start timer — only fetch if still visible after 150ms
      visibilityTimer = setTimeout(() => {
        loadImage()
        observer?.disconnect()
      }, 0)
    } else {
      // Scrolled away before timer fired — cancel
      if (visibilityTimer) {
        clearTimeout(visibilityTimer)
        visibilityTimer = null
      }
    }
  }, { rootMargin: '100px' })

  observer.observe(containerRef.value)
})

async function loadImage() {
  abortController = new AbortController()
  try {
    const res = await fetch(props.src, { signal: abortController.signal })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    blobUrl.value = url
    // Store in shared cache — survives folder navigation
    thumbCache.set(props.src, url)
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      console.warn('Thumbnail load failed:', props.src)
    }
  }
}

onBeforeUnmount(() => {
  // Cancel pending visibility timer
  if (visibilityTimer) {
    clearTimeout(visibilityTimer)
    visibilityTimer = null
  }
  // Cancel in-flight fetch
  abortController?.abort()
  observer?.disconnect()
  // Don't revoke blob URL — it's in the shared cache for reuse
})
</script>

<template>
  <div ref="containerRef" class="w-full h-full">
    <img
      v-if="blobUrl"
      :src="blobUrl"
      :alt="alt || ''"
      class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
    />
  </div>
</template>
