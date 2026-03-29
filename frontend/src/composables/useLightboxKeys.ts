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
  toggleMeta: () => void
  openStoryboard: () => void
  sendToInput: () => void
  sendWorkflow: () => void
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

    // Don't intercept browser shortcuts (Cmd+R, Ctrl+R, etc.)
    if (e.metaKey || e.ctrlKey || e.altKey) return

    // Handle Shift+ combos before the main switch (which assumes no modifiers)
    if (e.shiftKey) {
      switch (key) {
        case 'w':
          e.preventDefault()
          actions.sendWorkflow()
          return
        case '?':
          // Allow ? which is Shift+/ on most keyboards
          e.preventDefault()
          actions.toggleHelp()
          return
      }
      return // Ignore other Shift+ combos
    }

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
      case 'q':
        e.preventDefault()
        actions.sendToInput()
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
      case 'i':
        e.preventDefault()
        actions.toggleMeta()
        break
    }
  }

  onMounted(() => document.addEventListener('keydown', handler))
  onUnmounted(() => document.removeEventListener('keydown', handler))
}
