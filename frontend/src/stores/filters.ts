import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/** Reactive filter state — changes here instantly update the gallery grid */
export const useFilterStore = defineStore('filters', () => {
  // --- Client-side filters (instant) ---
  const search = ref('')
  const workflowFiles = ref('')
  const workflowPrompt = ref('')
  const selectedExtensions = ref<string[]>([])
  const selectedPrefixes = ref<string[]>([])
  const showFavorites = ref(false)
  const hideFavorites = ref(false)
  const noWorkflow = ref(false)
  const startDate = ref('')
  const endDate = ref('')

  // --- Server-side scope (triggers re-fetch) ---
  const scope = ref<'local' | 'global'>('local')
  const recursive = ref(false)
  const serverLoading = ref(false)

  const activeCount = computed(() => {
    let n = 0
    if (search.value) n++
    if (workflowFiles.value) n++
    if (workflowPrompt.value) n++
    if (selectedExtensions.value.length) n++
    if (selectedPrefixes.value.length) n++
    if (showFavorites.value) n++
    if (hideFavorites.value) n++
    if (noWorkflow.value) n++
    if (startDate.value) n++
    if (endDate.value) n++
    return n
  })

  function reset() {
    search.value = ''
    workflowFiles.value = ''
    workflowPrompt.value = ''
    selectedExtensions.value = []
    selectedPrefixes.value = []
    showFavorites.value = false
    hideFavorites.value = false
    noWorkflow.value = false
    startDate.value = ''
    endDate.value = ''
    scope.value = 'local'
    recursive.value = false
  }

  function toggleExtension(ext: string) {
    const idx = selectedExtensions.value.indexOf(ext)
    if (idx >= 0) {
      selectedExtensions.value = selectedExtensions.value.filter(e => e !== ext)
    } else {
      selectedExtensions.value = [...selectedExtensions.value, ext]
    }
  }

  function togglePrefix(prefix: string) {
    const idx = selectedPrefixes.value.indexOf(prefix)
    if (idx >= 0) {
      selectedPrefixes.value = selectedPrefixes.value.filter(p => p !== prefix)
    } else {
      selectedPrefixes.value = [...selectedPrefixes.value, prefix]
    }
  }

  return {
    search, workflowFiles, workflowPrompt,
    selectedExtensions, selectedPrefixes,
    showFavorites, hideFavorites, noWorkflow,
    startDate, endDate,
    scope, recursive, serverLoading,
    activeCount,
    reset, toggleExtension, togglePrefix,
  }
})
