import { onMounted, onUnmounted } from 'vue'

export interface LightboxKeyActions {
  close: () => void
  next: () => void
  prev: () => void
  delete: () => void
  download: () => void
  rename: () => void
  downloadWorkflow: () => void
  copyWorkflow: () => void
  openNewTab: () => void
  nodeSummary: () => void
  toggleFavorite: () => void
  zoomIn: () => void
  zoomOut: () => void
  resetZoom: () => void
  cyclePanStep: () => void
  pan: (dx: number, dy: number) => void
  toggleUi: () => void
  toggleHelp: () => void
  openStoryboard: () => void
  isOpen: () => boolean
}

/**
 * Registers keyboard shortcuts while the lightbox is active.
 * Call from the LightboxViewer setup.
 */
export function useLightboxKeys(actions: LightboxKeyActions) {
  function handler(e: KeyboardEvent) {
    if (!actions.isOpen()) return

    // Don't capture if user is typing in an input
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

    const key = e.key.toLowerCase()

    switch (key) {
      case 'escape':
        e.preventDefault()
        actions.close()
        break
      case 'v':
        e.preventDefault()
        actions.close()
        break
      case 'arrowleft':
        e.preventDefault()
        actions.prev()
        break
      case 'arrowright':
        e.preventDefault()
        actions.next()
        break
      case 'd':
      case 'delete':
        e.preventDefault()
        actions.delete()
        break
      case 's':
        e.preventDefault()
        actions.download()
        break
      case 'r':
        e.preventDefault()
        actions.rename()
        break
      case 'w':
        e.preventDefault()
        actions.downloadWorkflow()
        break
      case 'c':
        e.preventDefault()
        actions.copyWorkflow()
        break
      case 'o':
        e.preventDefault()
        actions.openNewTab()
        break
      case 'n':
        e.preventDefault()
        actions.nodeSummary()
        break
      case 'f':
        e.preventDefault()
        actions.toggleFavorite()
        break
      case '+':
      case '=':
        e.preventDefault()
        actions.zoomIn()
        break
      case '-':
      case '_':
        e.preventDefault()
        actions.zoomOut()
        break
      case '0':
        e.preventDefault()
        actions.resetZoom()
        break
      case '.':
        e.preventDefault()
        actions.cyclePanStep()
        break
      // Numpad pan
      case '8':
        e.preventDefault(); actions.pan(0, 1); break
      case '2':
        e.preventDefault(); actions.pan(0, -1); break
      case '4':
        e.preventDefault(); actions.pan(1, 0); break
      case '6':
        e.preventDefault(); actions.pan(-1, 0); break
      case '7':
        e.preventDefault(); actions.pan(1, 1); break
      case '9':
        e.preventDefault(); actions.pan(-1, 1); break
      case '1':
        e.preventDefault(); actions.pan(1, -1); break
      case '3':
        e.preventDefault(); actions.pan(-1, -1); break
      case 'h':
        e.preventDefault()
        actions.toggleUi()
        break
      case '?':
        e.preventDefault()
        actions.toggleHelp()
        break
      case 'e':
        e.preventDefault()
        actions.openStoryboard()
        break
    }
  }

  onMounted(() => document.addEventListener('keydown', handler))
  onUnmounted(() => document.removeEventListener('keydown', handler))
}
