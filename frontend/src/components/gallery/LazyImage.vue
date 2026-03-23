<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps<{
  src: string
  alt?: string
}>()

const blobUrl = ref('')
let abortController: AbortController | null = null
let observer: IntersectionObserver | null = null
let visibilityTimer: ReturnType<typeof setTimeout> | null = null
const containerRef = ref<HTMLElement | null>(null)

onMounted(() => {
  if (!containerRef.value) return

  observer = new IntersectionObserver((entries) => {
    const entry = entries[0]
    if (entry?.isIntersecting) {
      // Start timer — only fetch if still visible after 100ms
      visibilityTimer = setTimeout(() => {
        loadImage()
        observer?.disconnect()
      }, 150)
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
    blobUrl.value = URL.createObjectURL(blob)
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
  // Release blob URL
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
  }
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
