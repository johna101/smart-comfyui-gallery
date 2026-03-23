<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { folderApi } from '@/api/gallery'
import FolderTree from './FolderTree.vue'

const props = defineProps<{
  folderKey: string
}>()

const emit = defineEmits<{
  close: []
  navigate: [folderKey: string]
}>()

const gallery = useGalleryStore()
const folderName = gallery.folders[props.folderKey]?.display_name || props.folderKey

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
const searchFilter = ref('')
const sortKey = ref('name')
const sortDir = ref('asc')
const moving = ref(false)
const pickerExpanded = ref(new Set<string>(['_root_']))


async function handlePick(destinationKey: string) {
  if (destinationKey === props.folderKey) return
  moving.value = true
  try {
    await folderApi.moveFolder(props.folderKey, destinationKey)
    // Refresh folder data
    await gallery.loadFolder(gallery.currentFolderKey)
    emit('close')
  } catch (e) {
    console.log('Move folder failed:', e)
    alert('Move failed! The folder may not be movable to that location.')
  } finally {
    moving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[5000] flex items-center justify-center bg-black/60" @click.self="emit('close')">
      <div class="bg-neutral-900 border border-neutral-700 rounded-2xl shadow-2xl w-[400px] max-h-[80vh] flex flex-col">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-neutral-700 text-center">
          <h3 class="text-white font-medium">&#10132; Move "{{ folderName }}" to:</h3>
        </div>

        <!-- Search + Sort -->
        <div class="px-4 py-2 space-y-2">
          <input
            v-model="searchFilter"
            type="text"
            placeholder="&#128269; Search folders..."
            class="w-full bg-neutral-800 border border-neutral-600 rounded-lg px-3 py-2 text-white text-sm placeholder-neutral-500 outline-none focus:border-neutral-400"
          />
          <div class="flex gap-2">
            <button
              class="flex-1 py-1.5 rounded-lg text-sm text-center transition-colors"
              :class="sortKey === 'name' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-600'"
              @click="sortKey = 'name'; sortDir = 'asc'"
            >A-Z &#8593;</button>
            <button
              class="flex-1 py-1.5 rounded-lg text-sm text-center transition-colors"
              :class="sortKey === 'mtime' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-600'"
              @click="sortKey = 'mtime'; sortDir = 'desc'"
            >&#128197;</button>
          </div>
        </div>

        <!-- Tree -->
        <div class="flex-1 overflow-y-auto px-2 py-1 min-h-[200px]">
          <ul class="list-none p-0 m-0">
            <FolderTree
              folder-key="_root_"
              :depth="0"
              mode="picker"
              :exclude-key="folderKey"
              :search-filter="searchFilter"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              :expanded-override="pickerExpanded"
              @pick="handlePick"
            />
          </ul>
        </div>

        <!-- Loading overlay -->
        <div v-if="moving" class="absolute inset-0 bg-black/50 flex items-center justify-center rounded-2xl">
          <div class="w-8 h-8 border-2 border-neutral-600 border-t-white rounded-full animate-spin" />
        </div>

        <!-- Cancel -->
        <button
          class="w-full py-3 text-center text-red-400 hover:bg-red-900/30 border-t border-neutral-700 transition-colors"
          @click="emit('close')"
        >&#10005; Cancel</button>
      </div>
    </div>
  </Teleport>
</template>
