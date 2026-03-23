import { ref, onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'

export function useSelection() {
  const gallery = useGalleryStore()
  const lastSelectedId = ref<string | null>(null)

  function handleSelect(fileId: string, event: MouseEvent) {
    if (event.shiftKey && lastSelectedId.value) {
      // Range select
      const files = gallery.files
      const lastIdx = files.findIndex(f => f.id === lastSelectedId.value)
      const currentIdx = files.findIndex(f => f.id === fileId)
      if (lastIdx >= 0 && currentIdx >= 0) {
        const start = Math.min(lastIdx, currentIdx)
        const end = Math.max(lastIdx, currentIdx)
        const next = new Set(gallery.selectedFiles)
        for (let i = start; i <= end; i++) {
          next.add(files[i].id)
        }
        gallery.selectedFiles = next
      }
    } else {
      gallery.toggleFileSelection(fileId)
    }
    lastSelectedId.value = fileId
  }

  function handleKeydown(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

    // Ctrl/Cmd+A: select all
    if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
      e.preventDefault()
      gallery.selectAll()
      return
    }

    // Escape: clear selection
    if (e.key === 'Escape' && gallery.hasSelection) {
      e.preventDefault()
      gallery.clearSelection()
      return
    }
  }

  onMounted(() => document.addEventListener('keydown', handleKeydown))
  onUnmounted(() => document.removeEventListener('keydown', handleKeydown))

  return { handleSelect, lastSelectedId }
}
