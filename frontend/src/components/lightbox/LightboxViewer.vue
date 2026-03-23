<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import { fileApi, mediaApi } from '@/api/gallery'
import { useLightboxZoom } from '@/composables/useLightboxZoom'
import { useLightboxKeys } from '@/composables/useLightboxKeys'
import LightboxHeader from './LightboxHeader.vue'
import LightboxMedia from './LightboxMedia.vue'
import StoryboardViewer from '@/components/storyboard/StoryboardViewer.vue'
import type { GalleryFile } from '@/types/gallery'

const gallery = useGalleryStore()
const ui = useUiStore()
const zoom = useLightboxZoom()

// --- State ---
const uiHidden = ref(false)
const showHelp = ref(false)
const notification = ref('')
const notificationTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const mediaRef = ref<InstanceType<typeof LightboxMedia> | null>(null)

// --- Computed ---
const currentFile = computed<GalleryFile | null>(() => {
  if (!ui.lightboxOpen || ui.lightboxIndex < 0) return null
  return gallery.files[ui.lightboxIndex] ?? null
})

const fileCount = computed(() => gallery.files.length)

const positionLabel = computed(() => {
  if (ui.lightboxIndex < 0) return ''
  return `${ui.lightboxIndex + 1} / ${fileCount.value}`
})

// --- Reset zoom on file change ---
watch(() => ui.lightboxIndex, () => {
  zoom.resetZoom()
  showHelp.value = false
})

// --- Prevent body scroll when open ---
watch(() => ui.lightboxOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})

// --- Notifications ---
function showNotification(msg: string) {
  notification.value = msg
  if (notificationTimer.value) clearTimeout(notificationTimer.value)
  notificationTimer.value = setTimeout(() => { notification.value = '' }, 2000)
}

// --- Navigation ---
function navigate(direction: number) {
  if (fileCount.value === 0) return
  const newIndex = (ui.lightboxIndex + direction + fileCount.value) % fileCount.value
  ui.openLightbox(gallery.files[newIndex].id, newIndex)
}

// --- Actions ---
function close() {
  if (showHelp.value) {
    showHelp.value = false
    return
  }
  ui.closeLightbox()
}

async function deleteFile() {
  const file = currentFile.value
  if (!file) return
  if (!confirm(`Delete "${file.name}"?`)) return

  try {
    await fileApi.deleteFile(file.id)
    const idx = ui.lightboxIndex

    // Remove from store
    gallery.files.splice(idx, 1)

    if (gallery.files.length === 0) {
      close()
      return
    }

    // Navigate to next (or wrap to last)
    const newIdx = idx >= gallery.files.length ? gallery.files.length - 1 : idx
    ui.openLightbox(gallery.files[newIdx].id, newIdx)
    showNotification('File deleted')
  } catch (e) {
    showNotification('Delete failed')
  }
}

async function toggleFavorite() {
  const file = currentFile.value
  if (!file) return

  try {
    const res = await fileApi.toggleFavorite(file.id)
    file.is_favorite = res.is_favorite ? 1 : 0
    showNotification(res.is_favorite ? '★ Favorited' : '☆ Unfavorited')
  } catch {
    showNotification('Failed to toggle favorite')
  }
}

function rename() {
  const file = currentFile.value
  if (!file) return
  const newName = prompt('New filename:', file.name)
  if (!newName || newName === file.name) return

  fileApi.renameFile(file.id, newName)
    .then(res => {
      file.name = res.new_name
      showNotification(`Renamed to ${res.new_name}`)
    })
    .catch(() => showNotification('Rename failed'))
}

function download() {
  if (!currentFile.value) return
  window.open(mediaApi.downloadUrl(currentFile.value.id), '_blank')
}

function downloadWorkflow() {
  if (!currentFile.value?.has_workflow) return
  window.open(mediaApi.workflowUrl(currentFile.value.id), '_blank')
}

async function copyWorkflow() {
  if (!currentFile.value?.has_workflow) return
  try {
    const res = await fetch(mediaApi.workflowUrl(currentFile.value.id))
    const text = await res.text()
    await navigator.clipboard.writeText(text)
    showNotification('Workflow copied to clipboard')
  } catch {
    showNotification('Copy failed')
  }
}

function openNewTab() {
  if (!currentFile.value) return
  window.open(mediaApi.fileUrl(currentFile.value.id), '_blank')
}

function nodeSummary() {
  // For now, delegate to legacy — the node summary modal is complex
  if (!currentFile.value?.has_workflow) return
  const event = new CustomEvent('vue:nodeSummary', { detail: { fileId: currentFile.value.id } })
  window.dispatchEvent(event)
}

const showStoryboard = ref(false)

const videoWasPlaying = ref(false)

function storyboard() {
  if (!currentFile.value) return
  // Pause video while viewing storyboard
  const video = mediaRef.value?.videoRef
  if (video && !video.paused) {
    videoWasPlaying.value = true
    video.pause()
  } else {
    videoWasPlaying.value = false
  }
  showStoryboard.value = true
}

function closeStoryboard() {
  showStoryboard.value = false
  // Resume video if it was playing before
  if (videoWasPlaying.value) {
    const video = mediaRef.value?.videoRef
    if (video) video.play()
    videoWasPlaying.value = false
  }
}

function toggleUi() {
  uiHidden.value = !uiHidden.value
}

function toggleHelp() {
  showHelp.value = !showHelp.value
}

// --- Keyboard shortcuts ---
useLightboxKeys({
  isOpen: () => ui.lightboxOpen,
  close,
  next: () => navigate(1),
  prev: () => navigate(-1),
  delete: deleteFile,
  download,
  rename,
  downloadWorkflow,
  copyWorkflow,
  openNewTab,
  nodeSummary,
  toggleFavorite,
  zoomIn: () => zoom.zoomIn(),
  zoomOut: () => zoom.zoomOut(),
  resetZoom: () => zoom.resetZoom(),
  cyclePanStep: () => {
    const step = zoom.cyclePanStep()
    showNotification(`Pan step: ${step}px`)
  },
  pan: (dx, dy) => zoom.panByStep(dx, dy),
  toggleUi,
  toggleHelp,
  openStoryboard: storyboard,
})
</script>

<template>
  <Teleport to="body">
    <Transition name="lightbox">
      <div
        v-if="ui.lightboxOpen && currentFile"
        class="fixed inset-0 z-[4000] bg-black/95 flex flex-col"
        @click.self="close"
      >
        <!-- Header -->
        <LightboxHeader
          :file="currentFile"
          :zoom-percent="zoom.zoomPercent.value"
          :ui-hidden="uiHidden"
          @close="close"
          @delete="deleteFile"
          @rename="rename"
          @toggle-favorite="toggleFavorite"
          @toggle-ui="toggleUi"
          @zoom-in="zoom.zoomIn()"
          @zoom-out="zoom.zoomOut()"
          @node-summary="nodeSummary"
          @copy-workflow="copyWorkflow"
          @storyboard="storyboard"
        />

        <!-- Media area -->
        <div class="flex-1 relative min-h-0">
          <LightboxMedia
            ref="mediaRef"
            :file="currentFile"
            :transform-style="zoom.transformStyle.value"
            :is-dragging="zoom.isDragging.value"
            @drag-start="zoom.onDragStart"
            @drag-move="zoom.onDragMove"
            @drag-end="zoom.onDragEnd"
            @wheel="zoom.onWheel"
          />

          <!-- Navigation arrows -->
          <button
            v-if="fileCount > 1"
            class="absolute left-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white text-5xl z-30 p-2 transition-colors"
            title="Previous (←)"
            @click="navigate(-1)"
          >
            ‹
          </button>
          <button
            v-if="fileCount > 1"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white text-5xl z-30 p-2 transition-colors"
            title="Next (→)"
            @click="navigate(1)"
          >
            ›
          </button>
        </div>

        <!-- Bottom bar -->
        <div class="flex items-center justify-between px-4 py-2 text-white/60 text-sm">
          <span>{{ positionLabel }}</span>
          <button
            v-if="uiHidden"
            class="text-white/40 hover:text-white text-xs"
            @click="toggleUi"
          >
            Show UI (H)
          </button>
          <span v-else class="text-white/30">? for shortcuts</span>
        </div>

        <!-- Notification toast -->
        <Transition name="toast">
          <div
            v-if="notification"
            class="fixed bottom-16 left-1/2 -translate-x-1/2 bg-white/15 backdrop-blur-sm text-white px-4 py-2 rounded-lg text-sm z-50"
          >
            {{ notification }}
          </div>
        </Transition>

        <!-- Help overlay -->
        <Transition name="fade">
          <div
            v-if="showHelp"
            class="absolute inset-0 bg-black/80 z-40 flex items-center justify-center"
            @click="showHelp = false"
          >
            <div
              class="bg-neutral-900 border border-white/10 rounded-xl p-6 max-w-md text-sm"
              @click.stop
            >
              <h3 class="text-white text-lg font-semibold mb-4">Keyboard Shortcuts (Vue)</h3>
              <div class="grid grid-cols-2 gap-y-1 gap-x-6 text-white/80">
                <span class="text-white/50">←/→</span><span>Previous / Next</span>
                <span class="text-white/50">Esc / V</span><span>Close</span>
                <span class="text-white/50">F</span><span>Toggle Favorite</span>
                <span class="text-white/50">D / Del</span><span>Delete</span>
                <span class="text-white/50">S</span><span>Download</span>
                <span class="text-white/50">R</span><span>Rename</span>
                <span class="text-white/50">W</span><span>Download Workflow</span>
                <span class="text-white/50">C</span><span>Copy Workflow</span>
                <span class="text-white/50">N</span><span>Node Summary</span>
                <span class="text-white/50">O</span><span>Open in New Tab</span>
                <span class="text-white/50">E</span><span>Storyboard</span>
                <span class="text-white/50">+/-/0</span><span>Zoom In/Out/Reset</span>
                <span class="text-white/50">Numpad</span><span>Pan image</span>
                <span class="text-white/50">.</span><span>Cycle pan step</span>
                <span class="text-white/50">H</span><span>Toggle UI</span>
                <span class="text-white/50">?</span><span>This help</span>
              </div>
              <button
                class="mt-4 w-full text-center text-white/50 hover:text-white py-2"
                @click="showHelp = false"
              >
                Close
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>

    <!-- Storyboard overlay -->
    <StoryboardViewer
      v-if="showStoryboard && currentFile"
      :file="currentFile"
      @close="closeStoryboard"
    />
  </Teleport>
</template>

<style scoped>
/* Lightbox enter/leave */
.lightbox-enter-active,
.lightbox-leave-active {
  transition: opacity 0.2s ease;
}
.lightbox-enter-from,
.lightbox-leave-to {
  opacity: 0;
}

/* Toast */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 10px);
}

/* Fade */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
