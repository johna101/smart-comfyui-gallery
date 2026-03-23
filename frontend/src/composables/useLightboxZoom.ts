import { ref, computed } from 'vue'

export function useLightboxZoom() {
  const zoom = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  const panStep = ref(50)

  const transformStyle = computed(() =>
    `translate(${translateX.value}px, ${translateY.value}px) scale(${zoom.value})`
  )

  const zoomPercent = computed(() => Math.round(zoom.value * 100))

  function zoomIn(amount = 0.1) {
    zoom.value = Math.min(10, zoom.value + amount)
  }

  function zoomOut(amount = 0.1) {
    zoom.value = Math.max(0.1, zoom.value - amount)
  }

  function resetZoom() {
    zoom.value = 1
    translateX.value = 0
    translateY.value = 0
  }

  function pan(dx: number, dy: number) {
    translateX.value += dx
    translateY.value += dy
  }

  function panByStep(dx: number, dy: number) {
    pan(dx * panStep.value, dy * panStep.value)
  }

  function cyclePanStep(): number {
    const steps = [50, 100, 150, 200]
    const idx = steps.indexOf(panStep.value)
    panStep.value = steps[(idx + 1) % steps.length]
    return panStep.value
  }

  /** Mouse wheel zoom handler */
  function onWheel(e: WheelEvent) {
    e.preventDefault()
    const amount = e.ctrlKey ? 0.2 : 0.1
    if (e.deltaY < 0) zoomIn(amount)
    else zoomOut(amount)
  }

  /** Mouse drag state for panning */
  const isDragging = ref(false)
  let dragStartX = 0
  let dragStartY = 0
  let dragStartTranslateX = 0
  let dragStartTranslateY = 0

  function onDragStart(e: MouseEvent) {
    if (e.button !== 0) return
    isDragging.value = true
    dragStartX = e.clientX
    dragStartY = e.clientY
    dragStartTranslateX = translateX.value
    dragStartTranslateY = translateY.value
  }

  function onDragMove(e: MouseEvent) {
    if (!isDragging.value) return
    translateX.value = dragStartTranslateX + (e.clientX - dragStartX)
    translateY.value = dragStartTranslateY + (e.clientY - dragStartY)
  }

  function onDragEnd() {
    isDragging.value = false
  }

  return {
    zoom, translateX, translateY, panStep,
    transformStyle, zoomPercent, isDragging,
    zoomIn, zoomOut, resetZoom, pan, panByStep, cyclePanStep,
    onWheel, onDragStart, onDragMove, onDragEnd,
  }
}
