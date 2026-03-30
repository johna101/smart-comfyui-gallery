<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Calendar, X } from 'lucide-vue-next'
import FolderTree from '@/components/sidebar/FolderTree.vue'

const props = withDefaults(defineProps<{
  title?: string
  excludeKeys?: string[]
}>(), {
  title: 'Select Folder',
  excludeKeys: () => [],
})

const emit = defineEmits<{
  select: [folderKey: string]
  close: []
}>()

const searchFilter = ref('')
const sortKey = ref('name')
const sortDir = ref('asc')
const busy = ref(false)
// Isolated expand state so picker doesn't affect sidebar
const pickerExpanded = ref(new Set<string>(['_root_']))

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown, true))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown, true))

function handlePick(folderKey: string) {
  if (props.excludeKeys.includes(folderKey)) return
  emit('select', folderKey)
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[6000] flex items-center justify-center bg-black/60" @click.self="emit('close')">
      <div class="bg-neutral-900 border border-neutral-700 rounded-2xl shadow-2xl w-[400px] max-h-[80vh] flex flex-col relative">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-neutral-700 text-center">
          <h3 class="text-white font-medium">{{ title }}</h3>
        </div>

        <!-- Search + Sort -->
        <div class="px-4 py-2 space-y-2">
          <input
            v-model="searchFilter"
            type="text"
            placeholder="Search folders..."
            class="w-full bg-neutral-800 border border-neutral-600 rounded-lg px-3 py-2 text-white text-sm placeholder-neutral-500 outline-none focus:border-neutral-400"
          />
          <div class="flex gap-2">
            <button
              class="flex-1 py-1.5 rounded-lg text-sm text-center transition-colors"
              :class="sortKey === 'name' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-600'"
              @click="sortKey = 'name'; sortDir = 'asc'"
            >A-Z</button>
            <button
              class="flex-1 py-1.5 rounded-lg text-sm text-center transition-colors flex items-center justify-center"
              :class="sortKey === 'mtime' ? 'bg-blue-600/30 text-white border border-blue-500/50' : 'bg-neutral-800 text-neutral-400 border border-neutral-600'"
              @click="sortKey = 'mtime'; sortDir = 'desc'"
            ><Calendar :size="14" /></button>
          </div>
        </div>

        <!-- Tree -->
        <div class="flex-1 overflow-y-auto px-2 py-1 min-h-[200px]">
          <ul class="list-none p-0 m-0">
            <FolderTree
              folder-key="_root_"
              :depth="0"
              mode="picker"
              :exclude-key="excludeKeys[0] || ''"
              :search-filter="searchFilter"
              :sort-key="sortKey"
              :sort-dir="sortDir"
              :expanded-override="pickerExpanded"
              @pick="handlePick"
            />
          </ul>
        </div>

        <!-- Loading overlay -->
        <div v-if="busy" class="absolute inset-0 bg-black/50 flex items-center justify-center rounded-2xl">
          <div class="w-8 h-8 border-2 border-neutral-600 border-t-white rounded-full animate-spin" />
        </div>

        <!-- Cancel -->
        <button
          class="w-full py-3 text-center text-red-400 hover:bg-red-900/30 border-t border-neutral-700 transition-colors cursor-pointer"
          @click="emit('close')"
        ><X :size="14" class="inline-block" /> Cancel</button>
      </div>
    </div>
  </Teleport>
</template>
