import { useRouter } from 'vue-router'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'
import { useFilterStore } from '@/stores/filters'

export function useFolderNavigation() {
  const gallery = useGalleryStore()
  const preferences = usePreferencesStore()
  const filters = useFilterStore()
  const router = useRouter()

  async function navigateToFolder(folderKey: string, params?: Record<string, string> | boolean) {
    // Support old signature: navigateToFolder(key, pushHistory)
    let queryParams: Record<string, string> | undefined
    if (typeof params === 'boolean') {
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

    // Reset client-side filters on folder change
    filters.reset()

    // Load data, then update URL
    await gallery.loadFolder(folderKey, queryParams)

    router.push({
      name: 'folder',
      params: { folderKey },
      query: queryParams,
    })
  }

  return { navigateToFolder }
}
