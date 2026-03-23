<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import { folderApi } from '@/api/gallery'

const emit = defineEmits<{
  close: []
  apply: []
}>()

const gallery = useGalleryStore()
const { navigateToFolder } = useFolderNavigation()

// Parse current filter state from URL
const params = new URLSearchParams(window.location.search)

const search = ref(params.get('search') || '')
const workflowFiles = ref(params.get('workflow_files') || '')
const workflowPrompt = ref(params.get('workflow_prompt') || '')
const scope = ref(params.get('scope') || gallery.currentScope || 'local')
const recursive = ref(params.get('recursive') === 'true')
const startDate = ref(params.get('start_date') || '')
const endDate = ref(params.get('end_date') || '')
const showFavorites = ref(params.get('favorites') === 'true')
const hideFavorites = ref(params.get('hide_favorites') === 'true')
const noWorkflow = ref(params.get('no_workflow') === 'true')

// Multi-select: extensions and prefixes
const availableExtensions = ref<string[]>(gallery.availableExtensions || [])
const availablePrefixes = ref<string[]>(gallery.availablePrefixes || [])
const selectedExtensions = ref<string[]>(gallery.selectedExtensions || [])
const selectedPrefixes = ref<string[]>(gallery.selectedPrefixes || [])

// Refresh available options when scope/recursive changes
watch([scope, recursive], async () => {
  try {
    const data = await folderApi.searchOptions(scope.value, gallery.currentFolderKey, recursive.value)
    availableExtensions.value = data.extensions
    availablePrefixes.value = data.prefixes
  } catch (e) {
    // Ignore — keep existing options
  }
})

// Escape to close
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  }
}
onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))

// Toggle multi-select item
function toggleExtension(ext: string) {
  const idx = selectedExtensions.value.indexOf(ext)
  if (idx >= 0) selectedExtensions.value.splice(idx, 1)
  else selectedExtensions.value.push(ext)
}

function togglePrefix(prefix: string) {
  const idx = selectedPrefixes.value.indexOf(prefix)
  if (idx >= 0) selectedPrefixes.value.splice(idx, 1)
  else selectedPrefixes.value.push(prefix)
}

// Apply filters — navigates with query params
function applyFilters() {
  const p: Record<string, string> = {}

  if (search.value) p.search = search.value
  if (workflowFiles.value) p.workflow_files = workflowFiles.value
  if (workflowPrompt.value) p.workflow_prompt = workflowPrompt.value
  if (scope.value !== 'local') p.scope = scope.value
  if (recursive.value) p.recursive = 'true'
  if (startDate.value) p.start_date = startDate.value
  if (endDate.value) p.end_date = endDate.value
  if (showFavorites.value) p.favorites = 'true'
  if (hideFavorites.value) p.hide_favorites = 'true'
  if (noWorkflow.value) p.no_workflow = 'true'
  if (selectedExtensions.value.length) p.extensions = selectedExtensions.value.join(',')
  if (selectedPrefixes.value.length) p.prefixes = selectedPrefixes.value.join(',')

  navigateToFolder(gallery.currentFolderKey, p)
  emit('apply')
}

function resetFilters() {
  navigateToFolder(gallery.currentFolderKey)
  emit('apply')
}
</script>

<template>
  <div class="border-t border-white/10 bg-white/[0.02] px-4 py-4">
    <div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
      <!-- Search Scope -->
      <div class="filter-group">
        <label class="filter-label">Search Scope</label>
        <div class="flex gap-2">
          <label
            class="scope-option"
            :class="{ active: scope === 'local' }"
          >
            <input type="radio" v-model="scope" value="local" class="hidden" />
            📂 Current Folder
          </label>
          <label
            class="scope-option"
            :class="{ active: scope === 'global' }"
          >
            <input type="radio" v-model="scope" value="global" class="hidden" />
            🌐 Global
          </label>
        </div>
        <label class="flex items-center gap-2 mt-2 text-xs text-white/50 cursor-pointer">
          <input type="checkbox" v-model="recursive" class="accent-green-500" />
          📂 Include Subfolders
        </label>
      </div>

      <!-- Search by Name -->
      <div class="filter-group">
        <label class="filter-label">🔍 Search by Name</label>
        <input
          v-model="search"
          type="text"
          placeholder="Search files..."
          class="filter-input"
          @keydown.enter="applyFilters"
        />
      </div>

      <!-- Workflow Files -->
      <div class="filter-group">
        <label class="filter-label">⚙️ Workflow Files</label>
        <input
          v-model="workflowFiles"
          type="text"
          placeholder="Models, LoRAs..."
          class="filter-input"
          @keydown.enter="applyFilters"
        />
      </div>

      <!-- Prompt Keywords -->
      <div class="filter-group">
        <label class="filter-label">🎨 Prompt Keywords</label>
        <input
          v-model="workflowPrompt"
          type="text"
          placeholder="Prompts..."
          class="filter-input"
          @keydown.enter="applyFilters"
        />
      </div>

      <!-- Extensions -->
      <div class="filter-group" v-if="availableExtensions.length">
        <label class="filter-label">📄 Extensions</label>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="ext in availableExtensions"
            :key="ext"
            class="tag-btn"
            :class="{ 'tag-active': selectedExtensions.includes(ext) }"
            @click="toggleExtension(ext)"
          >
            {{ ext }}
          </button>
        </div>
      </div>

      <!-- Prefixes -->
      <div class="filter-group" v-if="availablePrefixes.length">
        <label class="filter-label">🏷️ Prefixes</label>
        <div class="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
          <button
            v-for="prefix in availablePrefixes"
            :key="prefix"
            class="tag-btn"
            :class="{ 'tag-active': selectedPrefixes.includes(prefix) }"
            @click="togglePrefix(prefix)"
          >
            {{ prefix }}
          </button>
        </div>
      </div>

      <!-- Date Range -->
      <div class="filter-group">
        <label class="filter-label">📅 Date Range</label>
        <div class="flex flex-col gap-1.5">
          <div>
            <label class="text-[10px] text-white/40">From:</label>
            <input v-model="startDate" type="date" class="filter-input" />
          </div>
          <div>
            <label class="text-[10px] text-white/40">To:</label>
            <input v-model="endDate" type="date" class="filter-input" />
          </div>
        </div>
      </div>

      <!-- Options -->
      <div class="filter-group">
        <label class="filter-label">Options</label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="showFavorites" class="accent-yellow-400" />
          ⭐ Favorites Only
        </label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="hideFavorites" class="accent-yellow-400" />
          ⭐ Hide Favorites
        </label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="noWorkflow" class="accent-red-400" />
          🚫 No Workflow
        </label>
      </div>

      <!-- Actions -->
      <div class="filter-group flex flex-col justify-end">
        <label class="filter-label">Actions</label>
        <div class="flex gap-2">
          <button class="toolbar-btn-apply" @click="applyFilters">
            🔍 Apply Filters
          </button>
          <button class="toolbar-btn-reset" @click="resetFilters">
            🗑️ Reset
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.filter-group {
  @apply flex flex-col gap-1.5;
}

.filter-label {
  @apply text-xs font-medium text-white/50 uppercase tracking-wide;
}

.filter-input {
  @apply w-full px-3 py-1.5 rounded-lg text-sm text-white bg-white/5
    border border-white/10 outline-none
    focus:border-blue-500/50 focus:bg-white/[0.08] transition-all;
}

/* Override date input icon color for dark theme */
.filter-input[type="date"]::-webkit-calendar-picker-indicator {
  filter: invert(0.7);
}

.scope-option {
  @apply px-3 py-1.5 rounded-lg text-xs text-white/60 bg-white/5
    border border-white/10 cursor-pointer transition-all;
}
.scope-option.active {
  @apply bg-blue-600/20 border-blue-500/40 text-blue-300;
}

.tag-btn {
  @apply px-2 py-0.5 rounded text-xs text-white/60 bg-white/5
    border border-white/10 cursor-pointer transition-all;
}
.tag-active {
  @apply bg-blue-600/20 border-blue-500/40 text-blue-300;
}

.filter-checkbox {
  @apply flex items-center gap-2 text-sm text-white/70 cursor-pointer;
}

.toolbar-btn-apply {
  @apply px-4 py-1.5 rounded-lg text-sm text-white bg-blue-600/30
    border border-blue-500/40 hover:bg-blue-600/40 transition-all;
}

.toolbar-btn-reset {
  @apply px-4 py-1.5 rounded-lg text-sm text-white/60 bg-white/5
    border border-white/10 hover:bg-white/10 hover:text-white transition-all;
}
</style>
