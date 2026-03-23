import { onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'

export function useFolderNavigation() {
  const gallery = useGalleryStore()
  const preferences = usePreferencesStore()

  async function navigateToFolder(folderKey: string, params?: Record<string, string> | boolean, pushHistory = true) {
    // Support old signature: navigateToFolder(key, pushHistory)
    let queryParams: Record<string, string> | undefined
    if (typeof params === 'boolean') {
      pushHistory = params
      queryParams = undefined
    } else {
      queryParams = params
    }

    // Auto-expand parent folders so the target is visible
    const folders = gallery.folders
    let parent = folders[folderKey]?.parent
    while (parent && parent !== '_root_') {
      preferences.expandedFolderKeys.add(parent)
      parent = folders[parent]?.parent ?? null
    }

    await gallery.loadFolder(folderKey, queryParams)

    if (pushHistory) {
      const qs = queryParams ? '?' + new URLSearchParams(queryParams).toString() : ''
      const url = `/galleryout/view/${folderKey}${qs}`
      history.pushState({ folderKey, params: queryParams }, '', url)
    }
  }

  function handlePopState(event: PopStateEvent) {
    const folderKey = event.state?.folderKey
    if (folderKey) {
      navigateToFolder(folderKey, event.state?.params, false)
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
