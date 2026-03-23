<script setup lang="ts">
import { ref } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { batchApi } from '@/api/gallery'

const gallery = useGalleryStore()
const showMore = ref(false)

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
  // Bridge to legacy folder picker
  const ids = getSelectedIds()
  window.dispatchEvent(new CustomEvent('vue:moveFiles', { detail: { fileIds: ids } }))
  showMore.value = false
}

function copySelected() {
  const ids = getSelectedIds()
  window.dispatchEvent(new CustomEvent('vue:copyFiles', { detail: { fileIds: ids } }))
  showMore.value = false
}

async function downloadZip() {
  const ids = getSelectedIds()
  showMore.value = false
  try {
    const prepRes = await batchApi.prepareZip(ids)
    if (!prepRes.job_id) return

    // Poll for completion
    const poll = setInterval(async () => {
      const status = await batchApi.checkZipStatus(prepRes.job_id)
      if (status.status === 'complete' && status.download_url) {
        clearInterval(poll)
        window.open(status.download_url, '_blank')
      } else if (status.status === 'error') {
        clearInterval(poll)
        console.error('Zip failed:', status.message)
      }
    }, 1000)
  } catch (e) {
    console.error('Download zip failed:', e)
  }
}

function closeMore(e: MouseEvent) {
  // Close dropdown if clicked outside
  if (showMore.value) showMore.value = false
}
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
        </div>

        <!-- Right: actions -->
        <div class="flex items-center gap-2 relative">
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
