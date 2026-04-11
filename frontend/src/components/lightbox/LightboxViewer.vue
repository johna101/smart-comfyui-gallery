<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import { fileApi, mediaApi } from '@/api/gallery'
import { useLightboxZoom } from '@/composables/useLightboxZoom'
import { useLightboxKeys } from '@/composables/useLightboxKeys'
import { useFolderNavigation } from '@/composables/useFolderNavigation'
import { useToast } from '@/composables/useToast'
import { Copy, X, ExternalLink, ChevronDown } from 'lucide-vue-next'
import type { CivitAIResource } from '@/types/gallery'
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

const civitaiResources = computed<CivitAIResource[]>(() => {
  const raw = currentFile.value?.civitai_resources
  if (!raw) return []
  try { return JSON.parse(raw) } catch { return [] }
})

function airToUrl(air: string): string | null {
  const match = air.match(/urn:air:\w+:\w+:civitai:(\d+)@(\d+)/)
  if (!match) return null
  return `https://civitai.com/models/${match[1]}?modelVersionId=${match[2]}`
}

function airType(air: string): string {
  const match = air.match(/urn:air:\w+:(\w+):/)
  return match ? match[1] : 'unknown'
}

// --- Generation params (on-demand fetch from node_summary API) ---
interface GenerationParam {
  key: string
  display: string
  value: string | number
  type: string
  group: 'core' | 'extended'
  order: number
}

interface LoraInfo {
  name: string
  path: string
  weight: number
  enabled: boolean
  hash?: string
  civitai?: { modelName: string; versionName: string; air?: string; modelVersionId?: number }
}

const metaCache = ref<Record<string, { generation_params: GenerationParam[], negative_prompt: string, lora_info: LoraInfo[] }>>({})
const showExtendedParams = ref(false)
const showPositivePrompt = ref(true)
const showNegativePrompt = ref(false)
const metaLoading = ref(false)

const generationParams = computed<GenerationParam[]>(() => {
  const fileId = currentFile.value?.id
  if (!fileId || !metaCache.value[fileId]) return []
  return metaCache.value[fileId].generation_params || []
})

const coreParams = computed(() => generationParams.value.filter(p => p.group === 'core'))
const extendedParams = computed(() => generationParams.value.filter(p => p.group === 'extended'))

const cachedNegativePrompt = computed(() => {
  const fileId = currentFile.value?.id
  if (!fileId || !metaCache.value[fileId]) return ''
  return metaCache.value[fileId].negative_prompt || ''
})

const cachedLoraInfo = computed<LoraInfo[]>(() => {
  const fileId = currentFile.value?.id
  if (!fileId || !metaCache.value[fileId]) return []
  return metaCache.value[fileId].lora_info || []
})

async function fetchMetaIfNeeded() {
  const file = currentFile.value
  if (!file?.has_workflow) return
  if (metaCache.value[file.id]) return

  metaLoading.value = true
  try {
    const resp = await mediaApi.getNodeSummary(file.id)
    if (resp.status === 'success' && resp.meta) {
      metaCache.value[file.id] = {
        generation_params: (resp.meta.generation_params as GenerationParam[]) || [],
        negative_prompt: (resp.meta.negative_prompt as string) || '',
        lora_info: (resp.meta.lora_info as LoraInfo[]) || [],
      }
    }
  } catch { /* silent */ }
  metaLoading.value = false
}

function formatParamValue(param: GenerationParam): string {
  if (param.type === 'float' && typeof param.value === 'number') {
    return param.value % 1 === 0 ? param.value.toFixed(1) : String(param.value)
  }
  if (param.type === 'int' && typeof param.value === 'number' && param.key !== 'Seed') {
    return param.value.toLocaleString()
  }
  return String(param.value)
}

// --- Bind zoom container ref from media component ---
watch(mediaRef, (comp) => {
  zoom.containerEl.value = comp?.rootRef ?? null
}, { immediate: true })

// --- Fetch meta when panel opens or file changes while panel is open ---
watch([showMeta, () => ui.lightboxIndex], () => {
  if (showMeta.value) fetchMetaIfNeeded()
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
                  <div v-if="currentFile.has_workflow" class="text-workflow text-xs">✓ Has workflow</div>
                </div>

                <!-- Generation Parameters -->
                <div v-if="coreParams.length > 0">
                  <h4 class="text-white/50 text-xs uppercase tracking-wide mb-1.5">Generation</h4>
                  <div class="bg-white/5 rounded-lg p-2.5 space-y-1">
                    <!-- Core params — always visible -->
                    <div
                      v-for="param in coreParams"
                      :key="param.key"
                      class="flex items-baseline justify-between gap-2 px-1 py-0.5"
                    >
                      <span class="text-white/40 text-xs shrink-0">{{ param.display }}</span>
                      <span
                        class="text-white/80 text-xs text-right truncate"
                        :class="{ 'font-mono': param.type === 'hash' }"
                        :title="String(param.value)"
                      >{{ formatParamValue(param) }}</span>
                    </div>

                    <!-- Extended params — toggle -->
                    <template v-if="extendedParams.length > 0">
                      <button
                        class="flex items-center gap-1 text-white/30 hover:text-white/60 text-[10px] uppercase tracking-wide pt-1 cursor-pointer w-full"
                        @click="showExtendedParams = !showExtendedParams"
                      >
                        <ChevronDown
                          :size="12"
                          class="transition-transform"
                          :class="{ '-rotate-90': !showExtendedParams }"
                        />
                        {{ showExtendedParams ? 'Less' : 'More' }} ({{ extendedParams.length }})
                      </button>

                      <template v-if="showExtendedParams">
                        <div
                          v-for="param in extendedParams"
                          :key="param.key"
                          class="flex items-baseline justify-between gap-2 px-1 py-0.5"
                        >
                          <span class="text-white/40 text-xs shrink-0">{{ param.display }}</span>
                          <span
                            class="text-white/80 text-xs text-right truncate"
                            :class="{ 'font-mono text-white/50': param.type === 'hash' }"
                            :title="String(param.value)"
                          >{{ formatParamValue(param) }}</span>
                        </div>
                      </template>
                    </template>
                  </div>
                </div>

                <!-- Prompt (collapsible, starts expanded) -->
                <div v-if="currentFile.workflow_prompt">
                  <div class="flex items-center justify-between mb-1">
                    <button
                      class="flex items-center gap-1 text-white/50 text-xs uppercase tracking-wide cursor-pointer hover:text-white/70"
                      @click="showPositivePrompt = !showPositivePrompt"
                    >
                      <ChevronDown :size="12" class="transition-transform" :class="{ '-rotate-90': !showPositivePrompt }" />
                      Prompt
                    </button>
                    <button
                      class="text-white/30 hover:text-white text-xs cursor-pointer"
                      title="Copy prompt"
                      @click="copyToClipboard(currentFile.workflow_prompt)"
                    ><Copy :size="12" /></button>
                  </div>
                  <div v-if="showPositivePrompt" class="text-white/80 text-xs leading-relaxed whitespace-pre-wrap bg-white/5 rounded-lg p-3 max-h-[40vh] overflow-y-auto">
                    {{ currentFile.workflow_prompt }}
                  </div>
                </div>

                <!-- Negative Prompt (collapsible, starts collapsed) -->
                <div v-if="cachedNegativePrompt">
                  <div class="flex items-center justify-between mb-1">
                    <button
                      class="flex items-center gap-1 text-white/50 text-xs uppercase tracking-wide cursor-pointer hover:text-white/70"
                      @click="showNegativePrompt = !showNegativePrompt"
                    >
                      <ChevronDown :size="12" class="transition-transform" :class="{ '-rotate-90': !showNegativePrompt }" />
                      Negative Prompt
                    </button>
                    <button
                      class="text-white/30 hover:text-white text-xs cursor-pointer"
                      title="Copy negative prompt"
                      @click="copyToClipboard(cachedNegativePrompt)"
                    ><Copy :size="12" /></button>
                  </div>
                  <div v-if="showNegativePrompt" class="text-white/60 text-xs leading-relaxed whitespace-pre-wrap bg-white/5 rounded-lg p-3 max-h-[20vh] overflow-y-auto">
                    {{ cachedNegativePrompt }}
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

                <!-- LoRAs -->
                <div v-if="cachedLoraInfo.length > 0">
                  <h4 class="text-white/50 text-xs uppercase tracking-wide mb-1">LoRAs</h4>
                  <div class="bg-white/5 rounded-lg p-2 space-y-1">
                    <div
                      v-for="(lora, i) in cachedLoraInfo"
                      :key="i"
                      class="flex items-start gap-2 px-1.5 py-1.5 rounded hover:bg-white/5"
                      :class="{ 'opacity-40': !lora.enabled }"
                    >
                      <span
                        class="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded mt-0.5"
                        :class="lora.enabled ? 'bg-amber-500/20 text-amber-300' : 'bg-white/10 text-white/40 line-through'"
                      >{{ lora.weight }}</span>
                      <div class="flex-1 min-w-0">
                        <template v-if="lora.civitai && airToUrl(lora.civitai.air || '')">
                          <a
                            :href="airToUrl(lora.civitai.air!)!"
                            target="_blank"
                            rel="noopener"
                            class="text-white/90 text-xs hover:text-blue-300 transition-colors flex items-center gap-1"
                          >
                            <span class="truncate">{{ lora.civitai.modelName || lora.name }}</span>
                            <ExternalLink :size="10" class="shrink-0 opacity-50" />
                          </a>
                          <div class="text-white/40 text-[10px]">{{ lora.civitai.versionName }}</div>
                        </template>
                        <template v-else>
                          <span class="text-white/80 text-xs truncate block">{{ lora.name }}</span>
                        </template>
                        <div v-if="!lora.enabled" class="text-white/30 text-[10px]">disabled</div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- CivitAI Resources -->
                <div v-if="civitaiResources.length > 0">
                  <h4 class="text-white/50 text-xs uppercase tracking-wide mb-1">CivitAI Resources</h4>
                  <div class="bg-white/5 rounded-lg p-2 space-y-1">
                    <div
                      v-for="(resource, i) in civitaiResources"
                      :key="i"
                      class="flex items-start gap-2 px-1.5 py-1.5 rounded hover:bg-white/5"
                    >
                      <span
                        class="shrink-0 text-[10px] font-medium uppercase px-1.5 py-0.5 rounded mt-0.5"
                        :class="{
                          'bg-blue-500/20 text-blue-300': airType(resource.air) === 'checkpoint',
                          'bg-amber-500/20 text-amber-300': airType(resource.air) === 'lora',
                          'bg-purple-500/20 text-purple-300': airType(resource.air) === 'embedding',
                          'bg-white/10 text-white/50': !['checkpoint', 'lora', 'embedding'].includes(airType(resource.air))
                        }"
                      >{{ airType(resource.air) }}</span>
                      <div class="flex-1 min-w-0">
                        <a
                          v-if="airToUrl(resource.air)"
                          :href="airToUrl(resource.air)!"
                          target="_blank"
                          rel="noopener"
                          class="text-white/90 text-xs hover:text-blue-300 transition-colors flex items-center gap-1"
                        >
                          <span class="truncate">{{ resource.modelName }}</span>
                          <ExternalLink :size="10" class="shrink-0 opacity-50" />
                        </a>
                        <span v-else class="text-white/80 text-xs truncate block">{{ resource.modelName }}</span>
                        <div class="text-white/40 text-[10px]">
                          {{ resource.versionName }}
                          <span v-if="resource.weight != null && resource.weight !== 1.0" class="text-white/30">
                            @ {{ resource.weight }}
                          </span>
                        </div>
                      </div>
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
