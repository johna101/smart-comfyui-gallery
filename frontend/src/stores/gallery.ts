import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GalleryFile, FoldersMap, FolderInfo, Breadcrumb } from '@/types/gallery'
import { navApi } from '@/api/gallery'
import { useFilterStore } from '@/stores/filters'

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
  const hasInputPath = ref(false)
  const hasWorkflowsPath = ref(false)

  // --- Computed ---
  const selectedCount = computed(() => selectedFiles.value.size)
  const hasSelection = computed(() => selectedFiles.value.size > 0)
  const currentFolder = computed(() => folders.value[currentFolderKey.value])
  const hasMoreFiles = computed(() => files.value.length < totalFiles.value)

  // Reverse lookup: folder path → folder key (for mapping files to folders)
  const folderPathToKey = computed(() => {
    const map: Record<string, string> = {}
    for (const [key, info] of Object.entries(folders.value)) {
      if (info.path) {
        // Normalize: strip trailing slash, lowercase for comparison
        const norm = info.path.replace(/[\\/]+$/, '')
        map[norm] = key
      }
    }
    return map
  })

  /** Find the folder key that contains a given file */
  function folderKeyForFile(file: GalleryFile): string | null {
    if (!file.path) return null
    // Get directory from file path
    const sep = file.path.includes('/') ? '/' : '\\'
    const lastSep = file.path.lastIndexOf(sep)
    if (lastSep < 0) return '_root_'
    const dir = file.path.substring(0, lastSep)
    return folderPathToKey.value[dir] || null
  }

  /** Client-side filtered view of files — instant, no network */
  const filteredFiles = computed(() => {
    const filters = useFilterStore()

    // No active filters → return all files (fast path)
    if (filters.activeCount === 0) return files.value

    let result = files.value

    // Name search (case-insensitive)
    if (filters.search) {
      const q = filters.search.toLowerCase()
      result = result.filter(f => f.name.toLowerCase().includes(q))
    }

    // Workflow files search (comma-separated keywords, case-insensitive)
    if (filters.workflowFiles) {
      const keywords = filters.workflowFiles.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
      result = result.filter(f =>
        keywords.every(kw => (f.workflow_files || '').toLowerCase().includes(kw))
      )
    }

    // Prompt search (comma-separated keywords, case-insensitive)
    if (filters.workflowPrompt) {
      const keywords = filters.workflowPrompt.split(',').map(k => k.trim().toLowerCase()).filter(Boolean)
      result = result.filter(f =>
        keywords.every(kw => (f.workflow_prompt || '').toLowerCase().includes(kw))
      )
    }

    // Extensions
    if (filters.selectedExtensions.length > 0) {
      const exts = new Set(filters.selectedExtensions.map(e => e.toLowerCase().replace(/^\./, '')))
      result = result.filter(f => {
        const ext = f.name.split('.').pop()?.toLowerCase() || ''
        return exts.has(ext)
      })
    }

    // Prefixes
    if (filters.selectedPrefixes.length > 0) {
      result = result.filter(f =>
        filters.selectedPrefixes.some(prefix => f.name.startsWith(prefix + '_'))
      )
    }

    // Favorites
    if (filters.showFavorites) {
      result = result.filter(f => f.is_favorite)
    }
    if (filters.hideFavorites) {
      result = result.filter(f => !f.is_favorite)
    }

    // No workflow
    if (filters.noWorkflow) {
      result = result.filter(f => !f.has_workflow)
    }

    // Date range
    if (filters.startDate) {
      const ts = new Date(filters.startDate).getTime() / 1000
      result = result.filter(f => f.mtime >= ts)
    }
    if (filters.endDate) {
      const ts = new Date(filters.endDate).getTime() / 1000 + 86399
      result = result.filter(f => f.mtime <= ts)
    }

    return result
  })

  const filteredCount = computed(() => filteredFiles.value.length)

  /** Track the last selected file for sidebar focus indicator */
  const lastSelectedFileId = ref<string | null>(null)

  /** Set of folder keys that contain at least one selected file */
  const highlightedFolderKeys = computed(() => {
    const keys = new Set<string>()
    if (selectedFiles.value.size === 0) return keys
    for (const fileId of selectedFiles.value) {
      const file = files.value.find(f => f.id === fileId)
      if (file) {
        const key = folderKeyForFile(file)
        if (key) keys.add(key)
      }
    }
    return keys
  })

  /** The folder key of the most recently selected file — for focused indicator */
  const focusedFolderKey = computed(() => {
    if (!lastSelectedFileId.value) return null
    const file = files.value.find(f => f.id === lastSelectedFileId.value)
    if (!file) return null
    return folderKeyForFile(file)
  })

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
    hasInputPath.value = data.hasInputPath ?? false
    hasWorkflowsPath.value = data.hasWorkflowsPath ?? false
  }

  function toggleFileSelection(fileId: string) {
    const next = new Set(selectedFiles.value)
    if (next.has(fileId)) {
      next.delete(fileId)
    } else {
      next.add(fileId)
      lastSelectedFileId.value = fileId
    }
    selectedFiles.value = next
  }

  function clearSelection() {
    selectedFiles.value = new Set()
    lastSelectedFileId.value = null
  }

  function selectAll() {
    selectedFiles.value = new Set(filteredFiles.value.map(f => f.id))
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

  const loading = ref(false)

  async function loadFolder(folderKey: string, params?: Record<string, string>) {
    loading.value = true
    // Update key + ancestors immediately so sidebar can collapse before API returns
    currentFolderKey.value = folderKey
    const newAncestors: string[] = []
    let curr: string | null = folders.value[folderKey]?.parent ?? null
    while (curr && folders.value[curr]) {
      newAncestors.push(curr)
      curr = folders.value[curr].parent ?? null
    }
    ancestorKeys.value = newAncestors
    // Clear selection on folder change
    selectedFiles.value = new Set()
    try {
      // Skip folders in response if we already have them (saves ~500KB)
      const hasFolders = Object.keys(folders.value).length > 0
      const skipFolders = hasFolders && !params?.force_refresh
      const fetchParams = skipFolders
        ? { ...params, skip_folders: 'true' }
        : params
      const data = await navApi.fetchFolder(folderKey, fetchParams)
      files.value = data.files
      // Only update folders if server sent them
      if (data.folders) {
        folders.value = data.folders as FoldersMap
      }
      currentFolderKey.value = data.currentFolderKey
      currentFolderInfo.value = data.currentFolderInfo as unknown as FolderInfo
      breadcrumbs.value = data.breadcrumbs as Breadcrumb[]
      ancestorKeys.value = data.ancestorKeys
      totalFiles.value = data.totalFiles
      totalFolderFiles.value = data.totalFolderFiles
      totalDbFiles.value = data.totalDbFiles
      availableExtensions.value = data.availableExtensions
      availablePrefixes.value = data.availablePrefixes
      activeFiltersCount.value = data.activeFiltersCount
      currentScope.value = data.currentScope
      isRecursive.value = data.isRecursive
      appVersion.value = data.appVersion
      ffmpegAvailable.value = data.ffmpegAvailable
      streamThreshold.value = data.streamThreshold
      hasInputPath.value = data.hasInputPath ?? hasInputPath.value
      hasWorkflowsPath.value = data.hasWorkflowsPath ?? hasWorkflowsPath.value
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    folders, files, currentFolderKey, currentFolderInfo,
    breadcrumbs, ancestorKeys, protectedFolderKeys,
    totalFiles, totalFolderFiles, totalDbFiles,
    availableExtensions, availablePrefixes, selectedExtensions, selectedPrefixes,
    activeFiltersCount, showFavorites, isRecursive, currentScope,
    selectedFiles, enableAiSearch, isAiSearch, aiQuery, isGlobalSearch,
    appVersion, ffmpegAvailable, streamThreshold, updateAvailable, hasInputPath, hasWorkflowsPath,
    // Computed
    selectedCount, hasSelection, currentFolder, hasMoreFiles,
    filteredFiles, filteredCount, highlightedFolderKeys, focusedFolderKey, lastSelectedFileId,
    loading,
    // Actions
    initFromServer, toggleFileSelection, clearSelection, selectAll,
    appendFiles, removeFile, updateFile, loadFolder, folderKeyForFile,
  }
})
