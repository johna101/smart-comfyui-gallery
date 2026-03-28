/**
 * SSE event stream composable.
 * Connects to the server's event endpoint and applies targeted state updates
 * to the gallery store based on mutation events (file/folder operations).
 *
 * One connection per browser tab. EventSource handles auto-reconnection.
 */

import { onMounted, onUnmounted, reactive } from 'vue'
import { useGalleryStore } from '@/stores/gallery'

/** Reactive scan progress state — shared across components via useScanProgress() */
const scanProgress = reactive({
  scanning: false,
  processed: 0,
  total: 0,
  phase: '' as string
})

export function useScanProgress() {
  return scanProgress
}

export function useEventStream() {
  let eventSource: EventSource | null = null
  let refetchTimer: ReturnType<typeof setTimeout> | null = null
  const gallery = useGalleryStore()

  /** Debounced loadFolder to coalesce rapid SSE events */
  function debouncedRefetch(forceRefresh = false, delayMs = 300) {
    if (refetchTimer) clearTimeout(refetchTimer)
    refetchTimer = setTimeout(() => {
      const params = forceRefresh ? { force_refresh: 'true' } : undefined
      gallery.loadFolder(gallery.currentFolderKey, params)
      refetchTimer = null
    }, delayMs)
  }

  /** Check if a folder_key is relevant to the current view */
  function isFolderRelevant(folderKey: string): boolean {
    if (!folderKey) return false
    if (folderKey === gallery.currentFolderKey) return true
    // In recursive mode, changes to child folders are relevant
    if (gallery.isRecursive && gallery.ancestorKeys.includes(folderKey)) return true
    return false
  }

  function connect() {
    eventSource = new EventSource('/galleryout/api/events')

    // --- File events: surgical updates ---

    eventSource.addEventListener('files_deleted', (e) => {
      const data = JSON.parse(e.data)
      // Remove files from current view (idempotent — no-op if already gone)
      data.file_ids?.forEach((id: string) => gallery.removeFile(id))
    })

    eventSource.addEventListener('files_moved', (e) => {
      const data = JSON.parse(e.data)
      // Remove from current view (source folder)
      data.file_ids?.forEach((id: string) => gallery.removeFile(id))
      // If viewing destination folder, refetch to show new files
      if (isFolderRelevant(data.dest_folder_key)) {
        debouncedRefetch()
      }
    })

    eventSource.addEventListener('files_copied', (e) => {
      const data = JSON.parse(e.data)
      if (isFolderRelevant(data.dest_folder_key)) {
        debouncedRefetch()
      }
    })

    eventSource.addEventListener('file_renamed', (e) => {
      const data = JSON.parse(e.data)
      if (isFolderRelevant(data.folder_key)) {
        // Remove old entry, refetch to get the new one
        gallery.removeFile(data.old_id)
        debouncedRefetch()
      }
    })

    eventSource.addEventListener('files_favorited', (e) => {
      const data = JSON.parse(e.data)
      const favValue = data.is_favorite ? 1 : 0
      data.file_ids?.forEach((id: string) => {
        gallery.updateFile(id, { is_favorite: favValue })
      })
    })

    eventSource.addEventListener('files_uploaded', (e) => {
      const data = JSON.parse(e.data)
      if (isFolderRelevant(data.folder_key)) {
        debouncedRefetch()
      }
    })

    // --- Folder events: tree refresh ---
    // All folder mutations affect the sidebar tree, so force-refresh the folder map

    const folderEvents = [
      'folder_created', 'folder_renamed', 'folder_moved',
      'folder_deleted', 'folder_mounted', 'folder_unmounted'
    ]
    for (const eventType of folderEvents) {
      eventSource.addEventListener(eventType, () => {
        debouncedRefetch(true) // force_refresh to get updated folder tree
      })
    }

    // --- Rescan events ---

    eventSource.addEventListener('rescan_completed', (e) => {
      const data = JSON.parse(e.data)
      if (isFolderRelevant(data.folder_key)) {
        debouncedRefetch()
      }
    })

    // --- Filesystem watcher events ---

    eventSource.addEventListener('files_detected', (e) => {
      const data = JSON.parse(e.data)
      if (isFolderRelevant(data.folder_key)) {
        debouncedRefetch()
      }
    })

    eventSource.addEventListener('files_removed', (e) => {
      const data = JSON.parse(e.data)
      data.file_ids?.forEach((id: string) => gallery.removeFile(id))
    })

    eventSource.addEventListener('file_moved_external', (e) => {
      const data = JSON.parse(e.data)
      gallery.removeFile(data.old_file_id)
      if (isFolderRelevant(data.folder_key)) {
        debouncedRefetch()
      }
    })

    // --- Scan progress events ---

    eventSource.addEventListener('scan_progress', (e) => {
      const data = JSON.parse(e.data)
      if (data.phase === 'complete') {
        scanProgress.scanning = false
        scanProgress.processed = 0
        scanProgress.total = 0
        scanProgress.phase = ''
        // Refresh current view to pick up any changes from the scan
        debouncedRefetch(true)
      } else {
        scanProgress.scanning = true
        scanProgress.processed = data.processed ?? 0
        scanProgress.total = data.total ?? 0
        scanProgress.phase = data.phase ?? 'scanning'
      }
    })

    // EventSource auto-reconnects on error with exponential backoff
    eventSource.onerror = () => {
      // No action needed — browser handles reconnection.
      // On reconnect, the next mutation event will push through.
      // Stale state self-corrects on next user navigation.
    }
  }

  onMounted(() => connect())

  onUnmounted(() => {
    if (refetchTimer) clearTimeout(refetchTimer)
    eventSource?.close()
    eventSource = null
  })
}
