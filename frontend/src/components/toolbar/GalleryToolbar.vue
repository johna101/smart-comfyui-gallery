<script setup lang="ts">
import { ref, computed } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'
import { useFilterStore } from '@/stores/filters'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import FilterPanel from './FilterPanel.vue'
import RescanProgress from './RescanProgress.vue'

const gallery = useGalleryStore()
const preferences = usePreferencesStore()
const filters = useFilterStore()
const { navigateToFolder } = useFolderNavigation()

const showFilters = ref(false)
const uploadInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const rescanJobId = ref<string | null>(null)

// Sort
const sortBy = ref(new URLSearchParams(window.location.search).get('sort_by') || 'date')
const sortOrder = ref(new URLSearchParams(window.location.search).get('sort_order') || 'desc')

function toggleSort(field: 'date' | 'name') {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortOrder.value = field === 'name' ? 'asc' : 'desc'
  }
  applySort()
}

function applySort() {
  navigateToFolder(gallery.currentFolderKey, {
    sort_by: sortBy.value,
    sort_order: sortOrder.value,
  })
}

// Upload
async function handleUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return

  uploading.value = true
  const formData = new FormData()
  for (const file of input.files) {
    formData.append('files', file)
  }
  formData.append('folder_key', gallery.currentFolderKey)

  try {
    const res = await fetch('/galleryout/upload', {
      method: 'POST',
      body: formData,
    })
    const data = await res.json()
    if (data.status === 'success') {
      // Refresh folder to show new files
      navigateToFolder(gallery.currentFolderKey)
    }
  } catch (err) {
    console.error('Upload failed:', err)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

// Rescan
async function startRescan(mode: string = 'smart') {
  try {
    const { folderApi } = await import('@/api/gallery')
    const res = await folderApi.rescanFolder(gallery.currentFolderKey, mode)
    if (res.status === 'started') {
      rescanJobId.value = res.job_id
    }
  } catch (err) {
    console.error('Rescan failed:', err)
  }
}

function onRescanComplete() {
  rescanJobId.value = null
  navigateToFolder(gallery.currentFolderKey)
}

// Refresh — force_refresh tells server to rescan the directory tree
function refreshFolder() {
  navigateToFolder(gallery.currentFolderKey, { force_refresh: 'true' })
}

// File count display
const fileCountLabel = computed(() => {
  const total = gallery.files.length
  const filtered = gallery.filteredCount

  if (filters.activeCount > 0) {
    return `📂 ${filtered} of ${total} files`
  }
  return `📂 ${total} File${total !== 1 ? 's' : ''}`
})
</script>

<template>
  <div class="border-b border-white/10">
    <!-- Row 1: Breadcrumbs + Options/Focus/Shortcuts -->
    <div class="flex items-center justify-between px-4 py-2 gap-4">
      <!-- Breadcrumbs -->
      <div class="flex items-center gap-1 text-sm min-w-0">
        <template v-for="(crumb, i) in gallery.breadcrumbs" :key="crumb.key">
          <button
            class="text-white/60 hover:text-white transition-colors truncate"
            @click="navigateToFolder(crumb.key)"
          >
            {{ crumb.display_name }}
          </button>
          <span v-if="i < gallery.breadcrumbs.length - 1" class="text-white/30">/</span>
        </template>
      </div>

      <!-- Right side: Shortcuts, Focus, Options -->
      <div class="flex items-center gap-2 shrink-0">
        <button
          class="toolbar-btn"
          title="Keyboard Shortcuts (?)"
          @click="$emit('showShortcuts')"
        >
          <span class="font-bold">?</span> Shortcuts
        </button>

        <button
          class="toolbar-btn"
          :class="{ 'toolbar-btn-active': preferences.focusMode }"
          title="Focus Mode (F)"
          @click="preferences.toggleFocusMode()"
        >
          ⚡ Focus
          <span
            class="text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-1"
            :class="preferences.focusMode
              ? 'bg-green-500/30 text-green-400'
              : 'bg-white/10 text-white/40'"
          >
            {{ preferences.focusMode ? 'ON' : 'OFF' }}
          </span>
        </button>
      </div>
    </div>

    <!-- Row 2: Filters + Actions + Sort + File Count -->
    <div class="flex items-center px-4 py-2 gap-3 border-t border-white/5">
      <!-- Filters toggle -->
      <button
        class="toolbar-btn"
        :class="{ 'toolbar-btn-active': showFilters || filters.activeCount > 0 }"
        @click="showFilters = !showFilters"
      >
        🔍 Filters
        <span v-if="filters.activeCount > 0" class="text-xs ml-1">
          ({{ filters.activeCount }})
          <span
            class="ml-1 text-white/50 hover:text-white cursor-pointer"
            title="Clear all filters"
            @click.stop="filters.reset()"
          >✕</span>
        </span>
      </button>

      <!-- Upload / Rescan / Refresh -->
      <div class="flex items-center gap-2 ml-4">
        <button class="toolbar-btn" @click="uploadInput?.click()" :disabled="uploading">
          {{ uploading ? '⏳' : '📤' }} Upload
        </button>
        <input
          ref="uploadInput"
          type="file"
          multiple
          accept="image/*,video/*"
          class="hidden"
          @change="handleUpload"
        />

        <button class="toolbar-btn" @click="startRescan()" :disabled="!!rescanJobId">
          ♻️ Rescan
        </button>

        <button class="toolbar-btn" @click="refreshFolder">
          🔃 Refresh
        </button>
      </div>

      <!-- Spacer -->
      <div class="flex-1" />

      <!-- File count -->
      <span class="text-sm text-white/60 whitespace-nowrap">{{ fileCountLabel }}</span>

      <!-- Select All -->
      <button class="toolbar-btn" @click="gallery.hasSelection ? gallery.clearSelection() : gallery.selectAll()">
        {{ gallery.hasSelection ? '☐ Deselect' : '✅ Select All' }}
      </button>

      <!-- Sort -->
      <div class="flex items-center gap-0.5">
        <button
          class="toolbar-btn text-xs"
          :class="{ 'toolbar-btn-active': sortBy === 'date' }"
          @click="toggleSort('date')"
        >
          📅 Date {{ sortBy === 'date' ? (sortOrder === 'asc' ? '↑' : '↓') : '' }}
        </button>
        <button
          class="toolbar-btn text-xs"
          :class="{ 'toolbar-btn-active': sortBy === 'name' }"
          @click="toggleSort('name')"
        >
          🔤 Name {{ sortBy === 'name' ? (sortOrder === 'asc' ? '↑' : '↓') : '' }}
        </button>
      </div>
    </div>

    <!-- Rescan progress -->
    <RescanProgress
      v-if="rescanJobId"
      :job-id="rescanJobId"
      @complete="onRescanComplete"
      @error="rescanJobId = null"
    />

    <!-- Collapsible filter panel -->
    <FilterPanel
      v-if="showFilters"
      @close="showFilters = false"
    />
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.toolbar-btn {
  @apply px-3 py-1.5 rounded-lg text-sm text-white/80 bg-white/5
    hover:bg-white/10 hover:text-white transition-all
    flex items-center gap-1 whitespace-nowrap
    border border-white/10;
}

.toolbar-btn:disabled {
  @apply opacity-40 cursor-not-allowed;
}

.toolbar-btn-active {
  @apply bg-blue-600/20 border-blue-500/40 text-blue-300;
}
</style>
