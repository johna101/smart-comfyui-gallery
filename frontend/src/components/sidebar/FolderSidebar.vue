<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import FolderTree from './FolderTree.vue'
import FolderContextMenu from './FolderContextMenu.vue'
import FolderMoveDialog from './FolderMoveDialog.vue'

const gallery = useGalleryStore()
const preferences = usePreferencesStore()
const { navigateToFolder } = useFolderNavigation()

const searchFilter = ref('')
const sortKey = ref(preferences.sortPreference?.nav?.key || 'name')
const sortDir = ref(preferences.sortPreference?.nav?.dir || 'asc')

const treeContainer = ref<HTMLElement | null>(null)

// Context menu state
const contextMenu = ref<{ folderKey: string; x: number; y: number } | null>(null)

// Move dialog state
const movingFolderKey = ref<string | null>(null)

// Scroll active folder into view after full tree renders
onMounted(() => {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const active = treeContainer.value?.querySelector('.bg-blue-600\\/30')
      active?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  })
})

function toggleSort() {
  if (sortKey.value === 'name') {
    sortKey.value = 'mtime'
    sortDir.value = 'desc'
  } else {
    sortKey.value = 'name'
    sortDir.value = 'asc'
  }
  // Persist
  preferences.sortPreference = {
    ...preferences.sortPreference,
    nav: { key: sortKey.value, dir: sortDir.value },
  }
}

async function handleNavigate(folderKey: string) {
  await navigateToFolder(folderKey)
}

function handleContextMenu(folderKey: string, x: number, y: number) {
  contextMenu.value = { folderKey, x, y }
}

function handleMoveFolder(folderKey: string) {
  movingFolderKey.value = folderKey
  contextMenu.value = null
}

async function handleContextNavigate(folderKey: string) {
  contextMenu.value = null
  await navigateToFolder(folderKey)
}

function expandAll() {
  Object.keys(gallery.folders).forEach(key => {
    if (gallery.folders[key]?.children?.length) {
      preferences.expandedFolderKeys.add(key)
    }
  })
  // Trigger reactivity
  preferences.expandedFolderKeys = new Set(preferences.expandedFolderKeys)
}

function collapseAll() {
  preferences.expandedFolderKeys = new Set()
}
</script>

<template>
  <aside class="vue-sidebar w-[280px] shrink-0 bg-neutral-900 border-r border-neutral-800 flex flex-col h-screen overflow-hidden">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-neutral-800">
      <div class="flex items-center justify-between">
        <div
          class="cursor-pointer"
          @click="handleNavigate('_root_')"
        >
          <span class="text-purple-400 font-bold text-lg">SmartGallery</span>
          <span class="text-neutral-500 text-xs ml-1">v{{ gallery.appVersion }}</span>
        </div>
        <div class="flex gap-1">
          <button
            class="text-neutral-500 hover:text-white text-sm px-1"
            title="Collapse all"
            @click="collapseAll"
          >&#9668;</button>
          <button
            class="text-neutral-500 hover:text-white text-sm px-1"
            title="Expand all"
            @click="expandAll"
          >&#9654;</button>
        </div>
      </div>
    </div>

    <!-- Search + Sort -->
    <div class="px-3 py-2 space-y-2 border-b border-neutral-800">
      <input
        v-model="searchFilter"
        type="text"
        placeholder="&#128269; Search folders..."
        class="w-full bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-white text-sm placeholder-neutral-500 outline-none focus:border-neutral-500"
      />
      <div class="flex gap-2">
        <button
          class="flex-1 py-1 rounded-lg text-xs text-center transition-colors"
          :class="sortKey === 'name' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-700'"
          @click="sortKey !== 'name' && toggleSort()"
        >A-Z &#8593;</button>
        <button
          class="flex-1 py-1 rounded-lg text-xs text-center transition-colors"
          :class="sortKey === 'mtime' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-700'"
          @click="sortKey !== 'mtime' && toggleSort()"
        >&#128197;</button>
      </div>
    </div>

    <!-- Folder Tree -->
    <div ref="treeContainer" class="flex-1 overflow-y-auto px-1 py-2">
      <ul class="list-none p-0 m-0">
        <FolderTree
          folder-key="_root_"
          :depth="0"
          mode="nav"
          :search-filter="searchFilter"
          :sort-key="sortKey"
          :sort-dir="sortDir"
          @navigate="handleNavigate"
          @context-menu="handleContextMenu"
        />
      </ul>
    </div>

    <!-- Loading indicator -->
    <div
      v-if="gallery.loading"
      class="px-4 py-2 text-center text-neutral-500 text-xs border-t border-neutral-800"
    >
      Loading...
    </div>

    <!-- Context Menu -->
    <FolderContextMenu
      v-if="contextMenu"
      :folder-key="contextMenu.folderKey"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @close="contextMenu = null"
      @navigate="handleContextNavigate"
      @move-folder="handleMoveFolder"
    />

    <!-- Move Folder Dialog -->
    <FolderMoveDialog
      v-if="movingFolderKey"
      :folder-key="movingFolderKey"
      @close="movingFolderKey = null"
      @navigate="handleContextNavigate"
    />
  </aside>
</template>
