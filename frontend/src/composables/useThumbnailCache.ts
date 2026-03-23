/**
 * Shared in-memory thumbnail cache.
 * Blob URLs persist across folder navigations within the same session.
 * Revisiting a folder shows thumbnails instantly from cache.
 */

const cache = new Map<string, string>()

// Cap to prevent unbounded memory growth
const MAX_ENTRIES = 2000

export function useThumbnailCache() {
  function get(url: string): string | undefined {
    return cache.get(url)
  }

  function set(url: string, blobUrl: string) {
    // Evict oldest entries if at capacity
    if (cache.size >= MAX_ENTRIES) {
      const firstKey = cache.keys().next().value
      if (firstKey) {
        const oldBlob = cache.get(firstKey)
        if (oldBlob) URL.revokeObjectURL(oldBlob)
        cache.delete(firstKey)
      }
    }
    cache.set(url, blobUrl)
  }

  function has(url: string): boolean {
    return cache.has(url)
  }

  return { get, set, has }
}
