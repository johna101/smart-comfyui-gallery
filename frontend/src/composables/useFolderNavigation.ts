import { onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'

export function useFolderNavigation() {
  const gallery = useGalleryStore()
  const preferences = usePreferencesStore()

  async function navigateToFolder(folderKey: string, pushHistory = true) {
    // Auto-expand parent folders so the target is visible
    const folders = gallery.folders
    let parent = folders[folderKey]?.parent
    while (parent && parent !== '_root_') {
      preferences.expandedFolderKeys.add(parent)
      parent = folders[parent]?.parent ?? null
    }

    await gallery.loadFolder(folderKey)

    if (pushHistory) {
      const url = `/galleryout/view/${folderKey}`
      history.pushState({ folderKey }, '', url)
    }
  }

  function handlePopState(event: PopStateEvent) {
    const folderKey = event.state?.folderKey
    if (folderKey) {
      navigateToFolder(folderKey, false)
    }
  }

  onMounted(() => {
    // Set initial history state so back works from the first page
    const currentKey = gallery.currentFolderKey
    history.replaceState({ folderKey: currentKey }, '', `/galleryout/view/${currentKey}`)

    window.addEventListener('popstate', handlePopState)
  })

  onUnmounted(() => {
    window.removeEventListener('popstate', handlePopState)
  })

  return { navigateToFolder }
}
