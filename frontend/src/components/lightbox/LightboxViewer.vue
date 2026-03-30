<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import { fileApi, mediaApi } from '@/api/gallery'
import { useLightboxZoom } from '@/composables/useLightboxZoom'
import { useLightboxKeys } from '@/composables/useLightboxKeys'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import { useToast } from '@/composables/useToast'
import { Copy, X } from 'lucide-vue-next'
import LightboxHeader from './LightboxHeader.vue'
import LightboxMedia from './LightboxMedia.vue'
import StoryboardViewer from '@/components/storyboard/StoryboardViewer.vue'
import type { GalleryFile } from '@/types/gallery'

const gallery = useGalleryStore()
const ui = useUiStore()
const zoom = useLightboxZoom()
const { navigateToFolder } = useFolderNavigation()
const toast = useToast()

// --- State ---
const uiHidden = ref(false)
const showHelp = ref(false)
const showMeta = ref(false)
const mediaRef = ref<InstanceType<typeof LightboxMedia> | null>(null)

// --- Computed ---
const currentFile = computed<GalleryFile | null>(() => {
  if (!ui.lightboxOpen || ui.lightboxIndex < 0) return null
  return gallery.filteredFiles[ui.lightboxIndex] ?? null
})

const fileCount = computed(() => gallery.filteredFiles.length)

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

// --- Navigation ---
function navigate(direction: number) {
  if (fileCount.value === 0) return
  const newIndex = (ui.lightboxIndex + direction + fileCount.value) % fileCount.value
  ui.openLightbox(gallery.filteredFiles[newIndex].id, newIndex)
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

    // Remove from underlying store (filteredFiles recomputes automatically)
    gallery.removeFile(file.id)

    if (gallery.filteredFiles.length === 0) {
      close()
      return
    }

    // Navigate to next (or wrap to last)
    const idx = Math.min(ui.lightboxIndex, gallery.filteredFiles.length - 1)
    ui.openLightbox(gallery.filteredFiles[idx].id, idx)
    toast.show('File deleted')
  } catch (e) {
    toast.show('Delete failed')
  }
}

async function toggleFavorite() {
  const file = currentFile.value
  if (!file) return

  try {
    const res = await fileApi.toggleFavorite(file.id)
    file.is_favorite = res.is_favorite ? 1 : 0
    toast.show(res.is_favorite ? 'Favorited' : 'Unfavorited')
  } catch {
    toast.show('Failed to toggle favorite')
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
      toast.show(`Renamed to ${res.new_name}`)
    })
    .catch(() => toast.show('Rename failed'))
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
    toast.show('Workflow copied to clipboard')
  } catch {
    toast.show('Copy failed')
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

// --- Inject to ComfyUI ---
async function sendToInput() {
  const file = currentFile.value
  if (!file) return
  if (!gallery.hasInputPath) { toast.show('ComfyUI input path not configured'); return }

  try {
    const res = await fileApi.injectInput(file.id)
    toast.show(`Sent to input: ${res.filename}`)
  } catch (e: any) {
    toast.show(e.message || 'Failed to send to input')
  }
}

async function sendWorkflow() {
  const file = currentFile.value
  if (!file?.has_workflow) return
  if (!gallery.hasWorkflowsPath) { toast.show('ComfyUI workflows path not configured'); return }

  // Pre-fill with source filename stem + today's date
  const stem = file.name.replace(/\.[^.]+$/, '')
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const suggested = `${stem}_${today}`

  const name = prompt('Workflow name for ComfyUI:', suggested)
  if (name === null) return // cancelled

  try {
    const res = await fileApi.injectWorkflow(file.id, name || undefined)
    toast.show(`Workflow sent: ${res.filename}`)
  } catch (e: any) {
    toast.show(e.message || 'Failed to send workflow')
  }
}

function navigateToFolderFromLightbox(folderKey: string) {
  close()
  navigateToFolder(folderKey)
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

function toggleMeta() {
  showMeta.value = !showMeta.value
}

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.show('Copied to clipboard')
  } catch {
    toast.show('Copy failed')
  }
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
    toast.show(`Pan step: ${step}px`)
  },
  pan: (dx, dy) => zoom.panByStep(dx, dy),
  toggleUi,
  toggleHelp,
  toggleMeta,
  openStoryboard: storyboard,
  sendToInput,
  sendWorkflow,
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
          @navigate-folder="navigateToFolderFromLightbox"
          @toggle-meta="toggleMeta"
          @send-to-input="sendToInput"
          @send-workflow="sendWorkflow"
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

          <!-- Metadata panel -->
          <Transition name="slide-right">
            <div
              v-if="showMeta && currentFile && !uiHidden"
              class="absolute left-0 top-0 bottom-0 w-[360px] max-w-[50%] z-30 overflow-y-auto
                bg-black/70 backdrop-blur-md border-r border-white/10"
            >
              <div class="p-4 space-y-4 text-sm">
                <div class="flex items-center justify-between">
                  <h3 class="text-white font-medium">File Info</h3>
                  <button
                    class="text-white/40 hover:text-white cursor-pointer"
                    @click="showMeta = false"
                  ><X :size="18" /></button>
                </div>

                <!-- Basic info -->
                <div class="space-y-1.5 text-white/70">
                  <div><span class="text-white/40">Name:</span> {{ currentFile.name }}</div>
                  <div v-if="currentFile.dimensions"><span class="text-white/40">Size:</span> {{ currentFile.dimensions }}</div>
                  <div v-if="currentFile.duration"><span class="text-white/40">Duration:</span> {{ currentFile.duration }}</div>
                  <div><span class="text-white/40">Type:</span> {{ currentFile.type }}</div>
                  <div v-if="currentFile.has_workflow" class="text-green-400 text-xs">✓ Has workflow</div>
                </div>

                <!-- Prompt -->
                <div v-if="currentFile.workflow_prompt">
                  <div class="flex items-center justify-between mb-1">
                    <h4 class="text-white/50 text-xs uppercase tracking-wide">Prompt</h4>
                    <button
                      class="text-white/30 hover:text-white text-xs cursor-pointer"
                      title="Copy prompt"
                      @click="copyToClipboard(currentFile.workflow_prompt)"
                    ><Copy :size="12" /></button>
                  </div>
                  <div class="text-white/80 text-xs leading-relaxed whitespace-pre-wrap bg-white/5 rounded-lg p-3 max-h-[40vh] overflow-y-auto">
                    {{ currentFile.workflow_prompt }}
                  </div>
                </div>

                <!-- Workflow files -->
                <div v-if="currentFile.workflow_files">
                  <div class="flex items-center justify-between mb-1">
                    <h4 class="text-white/50 text-xs uppercase tracking-wide">Workflow Files</h4>
                    <button
                      class="text-white/30 hover:text-white text-xs cursor-pointer"
                      title="Copy all"
                      @click="copyToClipboard(currentFile.workflow_files.replaceAll(' ||| ', '\n'))"
                    ><Copy :size="12" /></button>
                  </div>
                  <div class="bg-white/5 rounded-lg p-2 max-h-[30vh] overflow-y-auto space-y-0.5">
                    <div
                      v-for="(item, i) in currentFile.workflow_files.split(' ||| ').filter(Boolean)"
                      :key="i"
                      class="flex items-center gap-2 group/wf px-1.5 py-1 rounded hover:bg-white/5"
                    >
                      <span class="text-white/80 text-xs flex-1 truncate" :title="item">{{ item }}</span>
                      <button
                        class="text-white/20 hover:text-white text-xs shrink-0 opacity-0 group-hover/wf:opacity-100 transition-opacity cursor-pointer"
                        title="Copy"
                        @click="copyToClipboard(item)"
                      ><Copy :size="12" /></button>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </Transition>

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
                <span class="text-white/50">I</span><span>File Info & Prompt</span>
                <span class="text-white/50">Q</span><span>Send to ComfyUI Input</span>
                <span class="text-white/50">Shift+W</span><span>Send Workflow to ComfyUI</span>
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

/* Fade */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide right */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}
</style>
