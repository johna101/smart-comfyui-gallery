<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { usePreferencesStore } from '@/stores/preferences'

const props = withDefaults(defineProps<{
  folderKey: string
  depth?: number
  mode?: 'nav' | 'picker'
  excludeKey?: string
  searchFilter?: string
  sortKey?: string
  sortDir?: string
  expandedOverride?: Set<string> | null
}>(), {
  depth: 0,
  mode: 'nav',
  excludeKey: '',
  searchFilter: '',
  sortKey: 'name',
  sortDir: 'asc',
  expandedOverride: null,
})

const emit = defineEmits<{
  navigate: [folderKey: string]
  pick: [folderKey: string]
  contextMenu: [folderKey: string, x: number, y: number]
}>()

const gallery = useGalleryStore()
const preferences = usePreferencesStore()

const folder = computed(() => gallery.folders[props.folderKey])
const isActive = computed(() => gallery.currentFolderKey === props.folderKey)
const isHighlighted = computed(() => gallery.highlightedFolderKeys.has(props.folderKey))
const isFocused = computed(() => gallery.focusedFolderKey === props.folderKey)
const isExpanded = computed(() => {
  if (props.expandedOverride) {
    return props.expandedOverride.has(props.folderKey)
  }
  return preferences.expandedFolderKeys.has(props.folderKey) ||
    gallery.ancestorKeys.includes(props.folderKey)
})
const hasChildren = computed(() => (folder.value?.children?.length ?? 0) > 0)

const sortedChildren = computed(() => {
  if (!folder.value?.children) return []
  const children = [...folder.value.children]

  // Exclude source folder in picker mode
  const filtered = props.excludeKey
    ? children.filter(k => k !== props.excludeKey && !isDescendant(k, props.excludeKey))
    : children

  // Apply search filter
  const searched = props.searchFilter
    ? filtered.filter(k => matchesSearch(k, props.searchFilter))
    : filtered

  // Sort
  return searched.sort((a, b) => {
    const fa = gallery.folders[a]
    const fb = gallery.folders[b]
    if (!fa || !fb) return 0

    let cmp: number
    if (props.sortKey === 'mtime') {
      cmp = (fa.mtime || 0) - (fb.mtime || 0)
    } else {
      cmp = fa.display_name.localeCompare(fb.display_name, undefined, { sensitivity: 'base' })
    }
    return props.sortDir === 'desc' ? -cmp : cmp
  })
})

function isDescendant(key: string, ancestorKey: string): boolean {
  let current = gallery.folders[key]?.parent
  while (current) {
    if (current === ancestorKey) return true
    current = gallery.folders[current]?.parent ?? null
  }
  return false
}

function matchesSearch(key: string, search: string): boolean {
  const f = gallery.folders[key]
  if (!f) return false
  const term = search.toLowerCase()
  if (f.display_name.toLowerCase().includes(term)) return true
  // Also match if any descendant matches (keep parent visible)
  if (f.children) {
    return f.children.some(childKey => matchesSearch(childKey, search))
  }
  return false
}

function toggleExpand() {
  if (props.expandedOverride) {
    // Isolated expand state for picker mode
    if (props.expandedOverride.has(props.folderKey)) {
      props.expandedOverride.delete(props.folderKey)
    } else {
      props.expandedOverride.add(props.folderKey)
    }
    return
  }
  // If collapsing and the active folder is a descendant, navigate to this folder
  if (isExpanded.value && props.mode === 'nav') {
    const activeKey = gallery.currentFolderKey
    if (activeKey !== props.folderKey && isDescendant(activeKey, props.folderKey)) {
      emit('navigate', props.folderKey)
    }
  }
  preferences.toggleFolderExpanded(props.folderKey)
}

function handleClick() {
  if (props.mode === 'picker') {
    emit('pick', props.folderKey)
  } else {
    emit('navigate', props.folderKey)
  }
}

const rowEl = ref<HTMLElement | null>(null) // template ref
void rowEl // suppress TS6133 — used as template ref

function handleContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  emit('contextMenu', props.folderKey, e.clientX, e.clientY)
}
</script>

<template>
  <li class="folder-node">
    <div
      ref="rowEl"
      class="flex items-center gap-1 px-2 py-1.5 rounded-lg cursor-pointer transition-colors group/item"
      :class="{
        'bg-blue-600/30 text-white': isActive && mode === 'nav',
        'border-l-2 border-amber-400/60 bg-amber-400/5': isHighlighted && !isActive && mode === 'nav',
        'hover:bg-neutral-800': !isActive || mode === 'picker',
        'text-neutral-300': !isActive && !isHighlighted,
        'text-amber-200': isHighlighted && !isActive && mode === 'nav',
      }"
      :style="{ paddingLeft: `${depth * 16 + 8}px` }"
    >
      <!-- Expand/collapse toggle -->
      <button
        v-if="hasChildren"
        class="w-5 h-5 flex items-center justify-center text-neutral-500 hover:text-white shrink-0 transition-transform"
        :class="{ 'rotate-90': isExpanded }"
        @click.stop="toggleExpand"
      >&#9654;</button>
      <span v-else class="w-5 h-5 shrink-0" />

      <!-- Folder icon + name (clickable) -->
      <div class="flex-1 min-w-0 flex items-center gap-1.5 truncate" @click="handleClick">
        <span class="text-sm shrink-0">&#128193;</span>
        <span class="text-sm truncate">{{ folder?.display_name }}</span>
        <span v-if="folder?.is_mount" class="text-neutral-500 text-xs shrink-0">&#128279;</span>
        <span
          v-if="isFocused && mode === 'nav'"
          class="w-2 h-2 rounded-full bg-amber-400 shrink-0 ml-auto"
          title="Last selected file is in this folder"
        />
      </div>

      <!-- Picker mode: move-here button -->
      <button
        v-if="mode === 'picker'"
        class="shrink-0 text-neutral-500 hover:text-white px-1"
        title="Move here"
        @click.stop="emit('pick', folderKey)"
      >&#10132;</button>

      <!-- Nav mode: context menu trigger -->
      <button
        v-if="mode === 'nav'"
        class="shrink-0 text-neutral-500 hover:text-white opacity-0 group-hover/item:opacity-100 px-1 transition-opacity"
        @click.stop="handleContextMenu"
      >&#8942;</button>
    </div>

    <!-- Children (recursive) -->
    <ul v-if="hasChildren && isExpanded" class="list-none p-0 m-0">
      <FolderTree
        v-for="childKey in sortedChildren"
        :key="childKey"
        :folder-key="childKey"
        :depth="depth + 1"
        :mode="mode"
        :exclude-key="excludeKey"
        :search-filter="searchFilter"
        :sort-key="sortKey"
        :sort-dir="sortDir"
        :expanded-override="expandedOverride"
        @navigate="emit('navigate', $event)"
        @pick="emit('pick', $event)"
        @context-menu="(key: string, x: number, y: number) => emit('contextMenu', key, x, y)"
      />
    </ul>
  </li>
</template>
