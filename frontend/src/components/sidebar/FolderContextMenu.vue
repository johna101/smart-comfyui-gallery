<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { folderApi } from '@/api/gallery'

const props = defineProps<{
  folderKey: string
  x: number
  y: number
}>()

const menuEl = ref<HTMLElement | null>(null)
const adjustedX = ref(props.x)
const adjustedY = ref(props.y)

const emit = defineEmits<{
  close: []
  navigate: [folderKey: string]
  moveFolder: [folderKey: string]
}>()

const gallery = useGalleryStore()
const folder = ref(gallery.folders[props.folderKey])
const isMount = ref(folder.value?.is_mount ?? false)
const isProtected = ref(gallery.protectedFolderKeys.includes(props.folderKey))

function handleClickOutside(_e: MouseEvent) {
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
  }
}

onMounted(async () => {
  setTimeout(() => document.addEventListener('click', handleClickOutside), 0)
  document.addEventListener('keydown', handleKeydown)
  // Adjust position if menu overflows viewport
  await nextTick()
  if (menuEl.value) {
    const rect = menuEl.value.getBoundingClientRect()
    if (rect.bottom > window.innerHeight) {
      adjustedY.value = Math.max(4, props.y - rect.height)
    }
    if (rect.right > window.innerWidth) {
      adjustedX.value = Math.max(4, props.x - rect.width)
    }
  }
})
onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
})

async function renameFolder() {
  const currentName = folder.value?.display_name || ''
  const newName = prompt('Rename folder:', currentName)
  if (!newName || newName === currentName) { emit('close'); return }

  try {
    await folderApi.renameFolder(props.folderKey, newName)
    // Reload folder data to get updated tree
    await gallery.loadFolder(gallery.currentFolderKey, { force_refresh: 'true' })
  } catch (e) {
    console.error('Rename failed:', e)
  }
  emit('close')
}

async function deleteFolder() {
  const name = folder.value?.display_name || props.folderKey
  if (!confirm(`Delete folder "${name}" and all its contents?`)) { emit('close'); return }

  try {
    await folderApi.deleteFolder(props.folderKey)
    // Navigate to parent
    const parentKey = folder.value?.parent || '_root_'
    emit('navigate', parentKey)
  } catch (e) {
    console.error('Delete failed:', e)
  }
  emit('close')
}

function moveFolder() {
  emit('moveFolder', props.folderKey)
  emit('close')
}

async function createSubfolder() {
  const name = prompt('New folder name:')
  if (!name) { emit('close'); return }

  try {
    await folderApi.createFolder(props.folderKey, name)
    await gallery.loadFolder(gallery.currentFolderKey, { force_refresh: 'true' })
  } catch (e) {
    console.error('Create folder failed:', e)
    alert('Failed to create folder.')
  }
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuEl"
      class="fixed z-[5000] bg-neutral-800 border border-neutral-600 rounded-xl shadow-2xl overflow-hidden min-w-[160px] py-1"
      :style="{ left: `${adjustedX}px`, top: `${adjustedY}px` }"
      @click.stop
    >
      <button class="ctx-item" @click="createSubfolder">
        <span>&#128194;</span> New Folder
      </button>
      <button class="ctx-item" @click="renameFolder" v-if="!isMount">
        <span>&#9999;</span> Rename
      </button>
      <button class="ctx-item" @click="moveFolder" v-if="!isMount">
        <span>&#128193;</span> Move
      </button>
      <hr v-if="!isProtected" class="border-neutral-700 my-1" />
      <button class="ctx-item text-red-400 hover:text-red-300" @click="deleteFolder" v-if="!isProtected">
        <span>&#128465;</span> Delete
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
@reference "tailwindcss";
.ctx-item {
  @apply w-full text-left px-4 py-2 text-white text-sm hover:bg-neutral-700 transition-colors flex items-center gap-2 cursor-pointer;
}
</style>
