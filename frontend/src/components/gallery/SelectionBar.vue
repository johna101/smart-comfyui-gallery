<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { batchApi } from '@/api/gallery'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import CompareViewer from '@/components/compare/CompareViewer.vue'
import FolderPickerDialog from '@/components/ui/FolderPickerDialog.vue'

const gallery = useGalleryStore()
const { navigateToFolder } = useFolderNavigation()
const showMore = ref(false)
const showCompare = ref(false)
const showMoveDialog = ref(false)
const showCopyDialog = ref(false)
const zipProgress = ref('')

const canCompare = computed(() => {
  if (gallery.selectedCount !== 2) return false
  const ids = Array.from(gallery.selectedFiles)
  const files = ids.map(id => gallery.files.find(f => f.id === id))
  return files.every(f => f && f.type !== 'video')
})

const compareFiles = computed(() => {
  if (!canCompare.value) return { a: null, b: null }
  const ids = Array.from(gallery.selectedFiles)
  return {
    a: gallery.files.find(f => f.id === ids[0]) ?? null,
    b: gallery.files.find(f => f.id === ids[1]) ?? null,
  }
})

// Close compare when selection changes
watch(() => gallery.selectedCount, () => { showCompare.value = false })

function getSelectedIds(): string[] {
  return Array.from(gallery.selectedFiles)
}

async function favoriteSelected() {
  const ids = getSelectedIds()
  try {
    await batchApi.favoriteBatch(ids, true)
    ids.forEach(id => gallery.updateFile(id, { is_favorite: 1 }))
  } catch (e) {
    console.error('Batch favorite failed:', e)
  }
}

async function unfavoriteSelected() {
  const ids = getSelectedIds()
  try {
    await batchApi.favoriteBatch(ids, false)
    ids.forEach(id => gallery.updateFile(id, { is_favorite: 0 }))
  } catch (e) {
    console.error('Batch unfavorite failed:', e)
  }
  showMore.value = false
}

async function deleteSelected() {
  const ids = getSelectedIds()
  if (!confirm(`Delete ${ids.length} file(s)?`)) return
  try {
    await batchApi.deleteBatch(ids)
    ids.forEach(id => gallery.removeFile(id))
    gallery.clearSelection()
  } catch (e) {
    console.error('Batch delete failed:', e)
  }
}

function moveSelected() {
  showMore.value = false
  showMoveDialog.value = true
}

function copySelected() {
  showMore.value = false
  showCopyDialog.value = true
}

async function handleMoveConfirm(destKey: string) {
  const ids = getSelectedIds()
  showMoveDialog.value = false
  try {
    await batchApi.moveBatch(ids, destKey)
    ids.forEach(id => gallery.removeFile(id))
    gallery.clearSelection()
  } catch (e) {
    console.error('Batch move failed:', e)
  }
}

async function handleCopyConfirm(destKey: string) {
  const ids = getSelectedIds()
  showCopyDialog.value = false
  try {
    await batchApi.copyBatch(ids, destKey, true)
    // Refresh to show any new files if copying within same folder
    navigateToFolder(gallery.currentFolderKey)
    gallery.clearSelection()
  } catch (e) {
    console.error('Batch copy failed:', e)
  }
}

async function downloadZip() {
  const ids = getSelectedIds()
  showMore.value = false
  zipProgress.value = 'Preparing...'
  try {
    const prepRes = await batchApi.prepareZip(ids)
    if (!prepRes.job_id) { zipProgress.value = ''; return }

    // Poll for completion — backend returns 'ready' when done
    const poll = setInterval(async () => {
      try {
        const status = await batchApi.checkZipStatus(prepRes.job_id) as any
        if ((status.status === 'ready' || status.status === 'complete') && status.download_url) {
          clearInterval(poll)
          zipProgress.value = ''
          window.open(status.download_url, '_blank')
        } else if (status.status === 'error') {
          clearInterval(poll)
          zipProgress.value = ''
          console.error('Zip failed:', status.message)
        } else {
          zipProgress.value = `Zipping... ${status.current || ''}/${status.total || ''}`
        }
      } catch {
        clearInterval(poll)
        zipProgress.value = ''
      }
    }, 500)
  } catch (e) {
    zipProgress.value = ''
    console.error('Download zip failed:', e)
  }
}

// Close dropdown on outside click
function closeMore(e: MouseEvent) {
  if (showMore.value) showMore.value = false
}

onMounted(() => document.addEventListener('click', closeMore))
onUnmounted(() => document.removeEventListener('click', closeMore))
</script>

<template>
  <Teleport to="body">
    <Transition name="slide-up">
      <div
        v-if="gallery.hasSelection"
        class="fixed bottom-0 left-0 right-0 z-[3000] flex items-center justify-between px-6 py-3 bg-neutral-900/95 backdrop-blur-sm border-t border-neutral-700"
      >
        <!-- Left: count + deselect -->
        <div class="flex items-center gap-3">
          <button
            class="text-neutral-400 hover:text-white text-xl"
            title="Deselect all"
            @click="gallery.clearSelection()"
          >&#10005;</button>
          <span class="text-white text-sm font-medium">
            {{ gallery.selectedCount }} file{{ gallery.selectedCount !== 1 ? 's' : '' }} selected
          </span>
          <span v-if="zipProgress" class="text-xs text-white/50 ml-2">{{ zipProgress }}</span>
        </div>

        <!-- Right: actions -->
        <div class="flex items-center gap-2 relative">
          <button
            v-if="canCompare"
            class="sel-btn text-blue-400"
            title="Compare selected images"
            @click="showCompare = true"
          >⚖️</button>

          <button
            class="sel-btn text-yellow-400"
            title="Favorite selected"
            @click="favoriteSelected"
          >&#9733;</button>

          <button
            class="sel-btn text-red-400"
            title="Delete selected"
            @click="deleteSelected"
          >&#128465;</button>

          <!-- More menu -->
          <button
            class="sel-btn text-white border border-neutral-600 rounded-lg px-3"
            title="More actions"
            @click.stop="showMore = !showMore"
          >&#8942;</button>

          <!-- Dropdown -->
          <div
            v-if="showMore"
            class="absolute bottom-full right-0 mb-2 bg-neutral-800 border border-neutral-600 rounded-xl shadow-2xl overflow-hidden min-w-[200px]"
            @click.stop
          >
            <button
              v-if="canCompare"
              class="more-item"
              @click="showCompare = true; showMore = false"
            >
              <span>⚖️</span> Compare
            </button>
            <button class="more-item" @click="copySelected">
              <span>Cc</span> Copy to Folder...
            </button>
            <button class="more-item" @click="moveSelected">
              <span>&#128193;</span> Move to Folder...
            </button>
            <button class="more-item" @click="downloadZip">
              <span>&#128230;</span> Download as Zip
            </button>
            <button class="more-item" @click="unfavoriteSelected">
              <span>&#9734;</span> Remove Favorite
            </button>
            <hr class="border-neutral-700" />
            <button class="more-item" @click="gallery.selectAll(); showMore = false">
              <span>&#9745;</span> Select All Files
            </button>
            <button class="more-item" @click="gallery.clearSelection(); showMore = false">
              <span>&#9744;</span> Deselect All Files
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Compare overlay -->
    <CompareViewer
      v-if="showCompare && compareFiles.a && compareFiles.b"
      :file-a="compareFiles.a"
      :file-b="compareFiles.b"
      @close="showCompare = false"
    />

    <!-- Move to folder dialog -->
    <FolderPickerDialog
      v-if="showMoveDialog"
      title="&#10132; Move Files to Folder"
      @select="handleMoveConfirm"
      @close="showMoveDialog = false"
    />

    <!-- Copy to folder dialog -->
    <FolderPickerDialog
      v-if="showCopyDialog"
      title="&#128203; Copy Files to Folder"
      @select="handleCopyConfirm"
      @close="showCopyDialog = false"
    />
  </Teleport>
</template>

<style scoped>
@reference "tailwindcss";
.sel-btn {
  @apply p-2 rounded-lg hover:bg-neutral-700 transition-colors cursor-pointer text-lg;
}
.more-item {
  @apply w-full text-left px-4 py-3 text-white text-sm hover:bg-neutral-700 transition-colors flex items-center gap-3 cursor-pointer;
}
.slide-up-enter-active,
.slide-up-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
