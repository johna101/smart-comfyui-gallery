<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { GalleryFile } from '@/types/gallery'
import { mediaApi } from '@/api/gallery'

const props = defineProps<{
  fileA: GalleryFile
  fileB: GalleryFile
}>()

const emit = defineEmits<{ close: [] }>()

// State
const sliderPos = ref(50)
const zoom = ref(1)
const rotation = ref(0)
const isDraggingHandle = ref(false)
const stageRef = ref<HTMLElement | null>(null)
const showDiff = ref(true)
const diffOnlyMode = ref(true)
const diffLoaded = ref(false)
const diffData = ref<Array<{ key: string; val_a: string; val_b: string; is_diff: boolean }>>([])

const visibleDiff = computed(() =>
  diffOnlyMode.value ? diffData.value.filter(r => r.is_diff) : diffData.value
)
const diffCount = computed(() => diffData.value.filter(r => r.is_diff).length)

// Media URLs
const urlA = computed(() =>
  props.fileA.type === 'video' ? mediaApi.streamUrl(props.fileA.id) : mediaApi.fileUrl(props.fileA.id)
)
const urlB = computed(() =>
  props.fileB.type === 'video' ? mediaApi.streamUrl(props.fileB.id) : mediaApi.fileUrl(props.fileB.id)
)

const isVideo = computed(() => props.fileA.type === 'video' || props.fileB.type === 'video')

const transform = computed(() =>
  `scale(${zoom.value}) rotate(${rotation.value}deg)`
)

const clipStyle = computed(() => ({
  clipPath: `inset(0 ${100 - sliderPos.value}% 0 0)`,
}))

// Resolution helper
function resString(file: GalleryFile) {
  const parts: string[] = []
  if (file.dimensions) parts.push(file.dimensions)
  if (file.size) {
    const kb = file.size / 1024
    parts.push(kb > 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`)
  }
  return parts.join(' · ')
}

// Slider drag
function onSliderMove(clientX: number) {
  if (!stageRef.value) return
  const rect = stageRef.value.getBoundingClientRect()
  const pct = ((clientX - rect.left) / rect.width) * 100
  sliderPos.value = Math.max(0, Math.min(100, pct))
}

function onPointerDown(e: PointerEvent) {
  // Only the slider handle area triggers drag
  const handle = (e.target as HTMLElement).closest('.cmp-handle-zone')
  if (handle) {
    isDraggingHandle.value = true
    stageRef.value?.setPointerCapture(e.pointerId)
    onSliderMove(e.clientX)
    e.preventDefault()
  }
}

function onPointerMove(e: PointerEvent) {
  if (isDraggingHandle.value) {
    onSliderMove(e.clientX)
  }
}

function onPointerUp() {
  isDraggingHandle.value = false
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  // All scroll/pinch = zoom (centered)
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  zoom.value = Math.max(0.1, Math.min(10, zoom.value * delta))
}

// Controls
function zoomIn() { zoom.value = Math.min(10, zoom.value + 0.2) }
function zoomOut() { zoom.value = Math.max(0.1, zoom.value - 0.2) }
function resetView() { zoom.value = 1; rotation.value = 0 }
function rotate() { rotation.value = (rotation.value + 90) % 360 }

// Keyboard
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { emit('close'); return }
  if (e.key === '+' || e.key === '=') zoomIn()
  if (e.key === '-') zoomOut()
  if (e.key === '0') resetView()
  if (e.key === 'r' || e.key === 'R') rotate()
  if (e.key === 'i' || e.key === 'I') showDiff.value = !showDiff.value
}

// Video sync
const vidARef = ref<HTMLVideoElement | null>(null)
const vidBRef = ref<HTMLVideoElement | null>(null)

function syncVideos() {
  const a = vidARef.value
  const b = vidBRef.value
  if (!a || !b) return

  const events = ['play', 'pause', 'seeking', 'seeked', 'timeupdate']
  let syncing = false

  const sync = (src: HTMLVideoElement, tgt: HTMLVideoElement) => {
    if (syncing) return
    syncing = true
    if (!src.paused && tgt.paused) tgt.play()
    if (src.paused && !tgt.paused) tgt.pause()
    if (Math.abs(src.currentTime - tgt.currentTime) > 0.1) tgt.currentTime = src.currentTime
    syncing = false
  }

  events.forEach(evt => {
    a.addEventListener(evt, () => sync(a, b))
    b.addEventListener(evt, () => sync(b, a))
  })
}

// Load diff data
async function loadDiff() {
  try {
    const res = await mediaApi.compareFiles(props.fileA.id, props.fileB.id)
    diffData.value = res.diff || []
  } catch { /* ignore */ }
  diffLoaded.value = true
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  loadDiff()
  if (isVideo.value) {
    // Wait for refs to mount
    setTimeout(syncVideos, 100)
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black flex flex-col">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-2 bg-black/80 border-b border-white/10 shrink-0">
      <h3 class="text-white text-sm font-medium">⚖️ Compare</h3>

      <div class="flex items-center gap-2">
        <button class="cmp-btn" @click="rotate" title="Rotate (R)">🔄</button>
        <div class="w-px h-5 bg-white/20" />
        <button class="cmp-btn" @click="zoomOut" title="Zoom Out (-)">−</button>
        <button class="cmp-btn" @click="zoomIn" title="Zoom In (+)">+</button>
        <button class="cmp-btn" @click="resetView" title="Reset (0)">Reset</button>
        <div class="w-px h-5 bg-white/20" />
        <button
          class="cmp-btn"
          :class="{ 'bg-blue-600/30': showDiff }"
          @click="showDiff = !showDiff"
          title="Parameter Diff (I)"
        >📝 Diff{{ diffCount > 0 ? ` (${diffCount})` : '' }}</button>
        <button
          class="text-white/70 hover:text-white text-xl ml-2 cursor-pointer"
          @click="emit('close')"
          title="Close (Esc)"
        >✕</button>
      </div>
    </div>

    <!-- Stage -->
    <div
      ref="stageRef"
      class="flex-1 relative overflow-hidden select-none"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="onPointerUp"
      @wheel.prevent="onWheel"
    >
      <!-- Layer B (full width, behind) -->
      <div class="absolute inset-0 flex items-center justify-center">
        <video
          v-if="fileB.type === 'video'"
          ref="vidBRef"
          :src="urlB"
          class="max-w-full max-h-full object-contain"
          :style="{ transform }"
          autoplay loop muted playsinline
        />
        <img
          v-else
          :src="urlB"
          class="max-w-full max-h-full object-contain"
          :style="{ transform }"
          draggable="false"
        />
        <div class="absolute top-4 right-4 bg-black/60 text-white/70 text-xs px-2 py-1 rounded">
          B: {{ fileB.name }} <span class="text-white/40">{{ resString(fileB) }}</span>
        </div>
      </div>

      <!-- Layer A (clipped, on top) -->
      <div class="absolute inset-0 flex items-center justify-center" :style="clipStyle">
        <video
          v-if="fileA.type === 'video'"
          ref="vidARef"
          :src="urlA"
          class="max-w-full max-h-full object-contain"
          :style="{ transform }"
          autoplay loop muted playsinline
        />
        <img
          v-else
          :src="urlA"
          class="max-w-full max-h-full object-contain"
          :style="{ transform }"
          draggable="false"
        />
        <div class="absolute top-4 left-4 bg-black/60 text-blue-400 text-xs px-2 py-1 rounded">
          A: {{ fileA.name }} <span class="text-white/40">{{ resString(fileA) }}</span>
        </div>
      </div>

      <!-- Handle with wide hit zone -->
      <div
        class="cmp-handle-zone"
        :style="{ left: `${sliderPos}%` }"
      >
        <div class="cmp-handle">
          <div class="cmp-handle-grip">⟨⟩</div>
        </div>
      </div>
    </div>

    <!-- Diff panel -->
    <Transition name="slide-up">
      <div
        v-if="showDiff"
        class="shrink-0 max-h-[35%] overflow-y-auto bg-neutral-900/95 border-t border-white/10 pb-20"
      >
        <!-- No workflow data -->
        <div v-if="diffLoaded && !diffData.length" class="px-4 py-3 text-white/40 text-sm">
          No workflow metadata available for comparison.
        </div>

        <!-- Diff table -->
        <template v-else-if="diffData.length">
          <div class="flex items-center gap-3 px-3 py-2 bg-neutral-800 sticky top-0 z-10">
            <span class="text-xs text-white/50">
              {{ diffCount }} difference{{ diffCount !== 1 ? 's' : '' }}
              <span v-if="!diffOnlyMode"> / {{ diffData.length }} total</span>
            </span>
            <button
              class="text-xs px-2 py-0.5 rounded border cursor-pointer transition-colors"
              :class="diffOnlyMode
                ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-300'
                : 'border-white/10 bg-white/5 text-white/50 hover:text-white'"
              @click="diffOnlyMode = !diffOnlyMode"
            >
              {{ diffOnlyMode ? 'Diffs only' : 'Show all' }}
            </button>
          </div>
          <table class="w-full text-xs">
            <thead class="sticky top-[36px] bg-neutral-800">
              <tr>
                <th class="text-left px-3 py-1.5 text-white/50 w-1/5">Parameter</th>
                <th class="text-left px-3 py-1.5 text-blue-400 w-2/5">A: {{ fileA.name }}</th>
                <th class="text-left px-3 py-1.5 text-white/70 w-2/5">B: {{ fileB.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in visibleDiff"
                :key="row.key"
                :class="row.is_diff ? 'bg-yellow-500/5' : ''"
              >
                <td class="px-3 py-1.5 text-white/50 font-medium">{{ row.key }}</td>
                <td class="px-3 py-1.5 text-white/80 break-all">{{ row.val_a || '—' }}</td>
                <td class="px-3 py-1.5 text-white/80 break-all">{{ row.val_b || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <!-- Loading -->
        <div v-else class="px-4 py-3 text-white/30 text-sm">Loading metadata...</div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.cmp-btn {
  @apply px-2.5 py-1 rounded text-sm text-white/70 bg-white/5
    hover:bg-white/10 hover:text-white transition-colors cursor-pointer
    border border-white/10;
}

/* Wide invisible hit zone for easy grabbing */
.cmp-handle-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 40px;
  transform: translateX(-50%);
  cursor: col-resize;
  z-index: 10;
}

.cmp-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 3px;
  transform: translateX(-50%);
  background: white;
  box-shadow: 0 0 8px rgba(0, 0, 0, 0.5);
  pointer-events: none;
}

.cmp-handle-grip {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: white;
  color: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
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
