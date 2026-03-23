import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { fileApi } from '@/api/gallery'

export function useInfiniteScroll(sentinel: Ref<HTMLElement | null>) {
  const gallery = useGalleryStore()
  const loading = ref(false)
  const exhausted = ref(false)
  let observer: IntersectionObserver | null = null

  async function loadNext() {
    if (loading.value || exhausted.value || !gallery.hasMoreFiles) return

    loading.value = true
    try {
      const offset = gallery.files.length
      const res = await fileApi.loadMore(offset, gallery.currentFolderKey)
      if (res.files.length === 0) {
        exhausted.value = true
      } else {
        gallery.appendFiles(res.files)
      }
    } catch (e) {
      console.error('Load more failed:', e)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    // Check if already exhausted on initial load
    if (!gallery.hasMoreFiles) {
      exhausted.value = true
    }

    observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) loadNext()
      },
      { rootMargin: '300px' }
    )

    if (sentinel.value) observer.observe(sentinel.value)
  })

  onUnmounted(() => {
    observer?.disconnect()
  })

  return { loading, exhausted }
}
