<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useFilterStore } from '@/stores/filters'

const emit = defineEmits<{
  close: []
}>()

const gallery = useGalleryStore()
const filters = useFilterStore()

// When scope or recursive changes, re-fetch from server
watch([() => filters.scope, () => filters.recursive], async () => {
  filters.serverLoading = true
  try {
    const params: Record<string, string> = {}
    if (filters.scope === 'global') params.scope = 'global'
    if (filters.recursive) params.recursive = 'true'
    // Request all files (no pagination) so client-side filtering works on full dataset
    if (filters.scope === 'global' || filters.recursive) {
      params.no_pagination = 'true'
    }
    await gallery.loadFolder(gallery.currentFolderKey, params)
  } finally {
    filters.serverLoading = false
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
</script>

<template>
  <div class="border-t border-white/10 bg-white/[0.02] px-4 py-4">
    <!-- Server loading indicator -->
    <div v-if="filters.serverLoading" class="flex items-center gap-2 mb-3 text-xs text-white/40">
      <div class="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
      Loading...
    </div>

    <div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">

      <!-- Search Scope -->
      <div class="filter-group">
        <label class="filter-label">Search Scope</label>
        <div class="flex gap-2">
          <label
            class="scope-option"
            :class="{ active: filters.scope === 'local' }"
          >
            <input type="radio" v-model="filters.scope" value="local" class="hidden" />
            📂 Current Folder
          </label>
          <label
            class="scope-option"
            :class="{ active: filters.scope === 'global' }"
          >
            <input type="radio" v-model="filters.scope" value="global" class="hidden" />
            🌐 Global
          </label>
        </div>
        <label class="flex items-center gap-2 mt-2 text-xs text-white/50 cursor-pointer">
          <input type="checkbox" v-model="filters.recursive" class="accent-green-500" />
          📂 Include Subfolders
        </label>
      </div>

      <!-- Search by Name -->
      <div class="filter-group">
        <label class="filter-label">🔍 Search by Name</label>
        <input
          v-model="filters.search"
          type="text"
          placeholder="Type to filter..."
          class="filter-input"
        />
      </div>

      <!-- Workflow Files -->
      <div class="filter-group">
        <label class="filter-label">⚙️ Workflow Files</label>
        <input
          v-model="filters.workflowFiles"
          type="text"
          placeholder="Models, LoRAs..."
          class="filter-input"
        />
      </div>

      <!-- Prompt Keywords -->
      <div class="filter-group">
        <label class="filter-label">🎨 Prompt Keywords</label>
        <input
          v-model="filters.workflowPrompt"
          type="text"
          placeholder="Prompts..."
          class="filter-input"
        />
      </div>

      <!-- Extensions -->
      <div class="filter-group" v-if="gallery.availableExtensions.length">
        <label class="filter-label">📄 Extensions</label>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="ext in gallery.availableExtensions"
            :key="ext"
            class="tag-btn"
            :class="{ 'tag-active': filters.selectedExtensions.includes(ext) }"
            @click="filters.toggleExtension(ext)"
          >
            {{ ext }}
          </button>
        </div>
      </div>

      <!-- Prefixes -->
      <div class="filter-group" v-if="gallery.availablePrefixes.length">
        <label class="filter-label">🏷️ Prefixes</label>
        <div class="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
          <button
            v-for="prefix in gallery.availablePrefixes"
            :key="prefix"
            class="tag-btn"
            :class="{ 'tag-active': filters.selectedPrefixes.includes(prefix) }"
            @click="filters.togglePrefix(prefix)"
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
            <input v-model="filters.startDate" type="date" class="filter-input" />
          </div>
          <div>
            <label class="text-[10px] text-white/40">To:</label>
            <input v-model="filters.endDate" type="date" class="filter-input" />
          </div>
        </div>
      </div>

      <!-- Options -->
      <div class="filter-group">
        <label class="filter-label">Options</label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="filters.showFavorites" class="accent-yellow-400" />
          ⭐ Favorites Only
        </label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="filters.hideFavorites" class="accent-yellow-400" />
          ⭐ Hide Favorites
        </label>
        <label class="filter-checkbox">
          <input type="checkbox" v-model="filters.noWorkflow" class="accent-red-400" />
          🚫 No Workflow
        </label>
      </div>

      <!-- Actions -->
      <div class="filter-group flex flex-col justify-end">
        <div class="text-xs text-white/30 mb-2">
          {{ gallery.filteredCount }} of {{ gallery.files.length }} files
        </div>
        <button class="toolbar-btn-reset" @click="filters.reset()">
          🗑️ Reset All
        </button>
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

.toolbar-btn-reset {
  @apply px-4 py-1.5 rounded-lg text-sm text-white/60 bg-white/5
    border border-white/10 hover:bg-white/10 hover:text-white transition-all cursor-pointer;
}
</style>
