import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GalleryFile, FoldersMap, FolderInfo, Breadcrumb } from '@/types/gallery'

export const useGalleryStore = defineStore('gallery', () => {
  // --- Core data ---
  const folders = ref<FoldersMap>({})
  const files = ref<GalleryFile[]>([])
  const currentFolderKey = ref('_root_')
  const currentFolderInfo = ref<FolderInfo | null>(null)
  const breadcrumbs = ref<Breadcrumb[]>([])
  const ancestorKeys = ref<string[]>([])
  const protectedFolderKeys = ref<string[]>([])

  // --- Counts ---
  const totalFiles = ref(0)
  const totalFolderFiles = ref(0)
  const totalDbFiles = ref(0)

  // --- Filters ---
  const availableExtensions = ref<string[]>([])
  const availablePrefixes = ref<string[]>([])
  const selectedExtensions = ref<string[]>([])
  const selectedPrefixes = ref<string[]>([])
  const activeFiltersCount = ref(0)
  const showFavorites = ref(false)
  const isRecursive = ref(false)
  const currentScope = ref('local')

  // --- Selection ---
  const selectedFiles = ref(new Set<string>())

  // --- AI ---
  const enableAiSearch = ref(false)
  const isAiSearch = ref(false)
  const aiQuery = ref('')
  const isGlobalSearch = ref(false)

  // --- App info ---
  const appVersion = ref('')
  const ffmpegAvailable = ref(false)
  const streamThreshold = ref(0)
  const updateAvailable = ref(false)

  // --- Computed ---
  const selectedCount = computed(() => selectedFiles.value.size)
  const hasSelection = computed(() => selectedFiles.value.size > 0)
  const currentFolder = computed(() => folders.value[currentFolderKey.value])
  const hasMoreFiles = computed(() => files.value.length < totalFiles.value)

  // --- Actions ---
  function initFromServer() {
    const data = window.__GALLERY_DATA__
    if (!data) {
      console.warn('No __GALLERY_DATA__ found — running outside Flask template?')
      return
    }

    folders.value = data.folders
    files.value = data.files
    currentFolderKey.value = data.currentFolderKey
    currentFolderInfo.value = data.currentFolderInfo
    breadcrumbs.value = data.breadcrumbs
    ancestorKeys.value = data.ancestorKeys
    protectedFolderKeys.value = data.protectedFolderKeys
    totalFiles.value = data.totalFiles
    totalFolderFiles.value = data.totalFolderFiles
    totalDbFiles.value = data.totalDbFiles
    availableExtensions.value = data.availableExtensions
    availablePrefixes.value = data.availablePrefixes
    selectedExtensions.value = data.selectedExtensions
    selectedPrefixes.value = data.selectedPrefixes
    activeFiltersCount.value = data.activeFiltersCount
    showFavorites.value = data.showFavorites
    enableAiSearch.value = data.enableAiSearch
    isAiSearch.value = data.isAiSearch
    aiQuery.value = data.aiQuery
    isGlobalSearch.value = data.isGlobalSearch
    currentScope.value = data.currentScope
    isRecursive.value = data.isRecursive
    appVersion.value = data.appVersion
    ffmpegAvailable.value = data.ffmpegAvailable
    streamThreshold.value = data.streamThreshold
    updateAvailable.value = data.updateAvailable
  }

  function toggleFileSelection(fileId: string) {
    const next = new Set(selectedFiles.value)
    if (next.has(fileId)) {
      next.delete(fileId)
    } else {
      next.add(fileId)
    }
    selectedFiles.value = next
  }

  function clearSelection() {
    selectedFiles.value = new Set()
  }

  function selectAll() {
    selectedFiles.value = new Set(files.value.map(f => f.id))
  }

  function appendFiles(newFiles: GalleryFile[]) {
    files.value.push(...newFiles)
  }

  function removeFile(fileId: string) {
    const idx = files.value.findIndex(f => f.id === fileId)
    if (idx >= 0) {
      files.value.splice(idx, 1)
      const next = new Set(selectedFiles.value)
      next.delete(fileId)
      selectedFiles.value = next
      totalFiles.value--
    }
  }

  function updateFile(fileId: string, patch: Partial<GalleryFile>) {
    const file = files.value.find(f => f.id === fileId)
    if (file) Object.assign(file, patch)
  }

  return {
    // State
    folders, files, currentFolderKey, currentFolderInfo,
    breadcrumbs, ancestorKeys, protectedFolderKeys,
    totalFiles, totalFolderFiles, totalDbFiles,
    availableExtensions, availablePrefixes, selectedExtensions, selectedPrefixes,
    activeFiltersCount, showFavorites, isRecursive, currentScope,
    selectedFiles, enableAiSearch, isAiSearch, aiQuery, isGlobalSearch,
    appVersion, ffmpegAvailable, streamThreshold, updateAvailable,
    // Computed
    selectedCount, hasSelection, currentFolder, hasMoreFiles,
    // Actions
    initFromServer, toggleFileSelection, clearSelection, selectAll,
    appendFiles, removeFile, updateFile,
  }
})
