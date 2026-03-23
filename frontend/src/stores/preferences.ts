import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/** Persistent user preferences backed by localStorage. */
export const usePreferencesStore = defineStore('preferences', () => {
  // --- State (initialized from localStorage) ---
  const videoAutoplay = ref(localStorage.getItem('sg_videoAutoplay') === 'true')
  const gridSize = ref<'normal' | 'compact'>(
    (localStorage.getItem('sg_gridSize') as 'normal' | 'compact') || 'normal'
  )
  const focusMode = ref(localStorage.getItem('galleryFocusMode') === 'true')
  const sidebarMinimized = ref(localStorage.getItem('sidebarMinimizedState') === 'true')

  const expandedFolderKeys = ref<Set<string>>(
    new Set(JSON.parse(localStorage.getItem('galleryFolderState') || '[]'))
  )

  const sortPreference = ref(
    JSON.parse(localStorage.getItem('gallerySortPreference') || JSON.stringify({
      nav: { key: 'name', dir: 'asc' },
      move: { key: 'name', dir: 'asc' },
    }))
  )

  // --- Watchers (auto-persist to localStorage) ---
  watch(videoAutoplay, v => localStorage.setItem('sg_videoAutoplay', String(v)))
  watch(gridSize, v => localStorage.setItem('sg_gridSize', v))
  watch(focusMode, v => localStorage.setItem('galleryFocusMode', String(v)))
  watch(sidebarMinimized, v => localStorage.setItem('sidebarMinimizedState', String(v)))
  watch(expandedFolderKeys, v => {
    localStorage.setItem('galleryFolderState', JSON.stringify([...v]))
  }, { deep: true })
  watch(sortPreference, v => {
    localStorage.setItem('gallerySortPreference', JSON.stringify(v))
  }, { deep: true })

  // --- Actions ---
  function toggleFocusMode() {
    focusMode.value = !focusMode.value
  }

  function toggleSidebar() {
    sidebarMinimized.value = !sidebarMinimized.value
  }

  function toggleFolderExpanded(folderKey: string) {
    if (expandedFolderKeys.value.has(folderKey)) {
      expandedFolderKeys.value.delete(folderKey)
    } else {
      expandedFolderKeys.value.add(folderKey)
    }
  }

  return {
    videoAutoplay, gridSize, focusMode, sidebarMinimized,
    expandedFolderKeys, sortPreference,
    toggleFocusMode, toggleSidebar, toggleFolderExpanded,
  }
})
