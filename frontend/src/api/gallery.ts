// API service — typed wrappers for all /galleryout/* endpoints.
// Each function returns parsed JSON. Errors throw.

import type { GalleryFile } from '@/types/gallery'

const BASE = '/galleryout'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

function post<T>(url: string, body: Record<string, unknown>): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// --- Files ---
export const fileApi = {
  loadMore: (offset: number, folderKey: string) =>
    request<{ files: GalleryFile[] }>(`${BASE}/load_more?offset=${offset}&folder_key=${folderKey}`),

  toggleFavorite: (fileId: string) =>
    post<{ status: string; is_favorite: boolean }>(`${BASE}/toggle_favorite/${fileId}`, {}),

  deleteFile: (fileId: string) =>
    post<{ status: string; message: string }>(`${BASE}/delete/${fileId}`, {}),

  renameFile: (fileId: string, newName: string) =>
    post<{ status: string; new_name: string; new_id: string }>(`${BASE}/rename_file/${fileId}`, { new_name: newName }),

  checkMetadata: (fileId: string) =>
    request<{ status: string; has_workflow: boolean; has_ai_caption: boolean; ai_caption: string }>(`${BASE}/check_metadata/${fileId}`),
}

// --- Batch operations ---
export const batchApi = {
  moveBatch: (fileIds: string[], destinationFolder: string) =>
    post<{ status: string; message: string }>(`${BASE}/move_batch`, { file_ids: fileIds, destination_folder: destinationFolder }),

  copyBatch: (fileIds: string[], destinationFolder: string, keepFavorites: boolean) =>
    post<{ status: string; message: string }>(`${BASE}/copy_batch`, { file_ids: fileIds, destination_folder: destinationFolder, keep_favorites: keepFavorites }),

  deleteBatch: (fileIds: string[]) =>
    post<{ status: string; message: string }>(`${BASE}/delete_batch`, { file_ids: fileIds }),

  favoriteBatch: (fileIds: string[], status: boolean) =>
    post<{ status: string; message: string }>(`${BASE}/favorite_batch`, { file_ids: fileIds, status }),

  prepareZip: (fileIds: string[]) =>
    post<{ status: string; job_id: string }>(`${BASE}/prepare_batch_zip`, { file_ids: fileIds }),

  checkZipStatus: (jobId: string) =>
    request<{ status: string; download_url?: string }>(`${BASE}/check_zip_status/${jobId}`),
}

// --- Folders ---
export const folderApi = {
  createFolder: (parentKey: string, folderName: string) =>
    post<{ status: string; message: string }>(`${BASE}/create_folder`, { parent_key: parentKey, folder_name: folderName }),

  renameFolder: (folderKey: string, newName: string) =>
    post<{ status: string; message: string }>(`${BASE}/rename_folder/${folderKey}`, { new_name: newName }),

  moveFolder: (folderKey: string, destinationFolder: string) =>
    post<{ status: string; message: string }>(`${BASE}/move_folder/${folderKey}`, { destination_folder: destinationFolder }),

  deleteFolder: (folderKey: string) =>
    post<{ status: string; message: string }>(`${BASE}/delete_folder/${folderKey}`, {}),

  mountFolder: (linkName: string, targetPath: string) =>
    post<{ status: string; message: string }>(`${BASE}/mount_folder`, { link_name: linkName, target_path: targetPath }),

  unmountFolder: (folderKey: string) =>
    post<{ status: string; message: string }>(`${BASE}/unmount_folder`, { folder_key: folderKey }),

  browseFilesystem: (path: string) =>
    post<{ current_path: string; parent_path: string; folders: Array<{ name: string; path: string }> }>(`${BASE}/api/browse_filesystem`, { path }),

  searchOptions: (scope: string, folderKey: string, recursive: boolean) =>
    request<{ extensions: string[]; prefixes: string[] }>(`${BASE}/api/search_options?scope=${scope}&folder_key=${folderKey}&recursive=${recursive}`),

  rescanFolder: (folderKey: string, mode: string) =>
    post<{ status: string; job_id: string; total: number }>(`${BASE}/rescan_folder`, { folder_key: folderKey, mode }),

  checkRescanStatus: (jobId: string) =>
    request<{ status: string; current: number; total: number }>(`${BASE}/check_rescan_status/${jobId}`),
}

// --- Media ---
// --- Navigation ---
export const navApi = {
  /** Fetch folder data for SPA navigation (no page reload) */
  fetchFolder: (folderKey: string, params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : ''
    return request<{
      files: GalleryFile[]
      totalFiles: number
      totalFolderFiles: number
      totalDbFiles: number
      folders: Record<string, unknown>
      currentFolderKey: string
      currentFolderInfo: Record<string, unknown>
      breadcrumbs: Array<{ key: string; display_name: string }>
      ancestorKeys: string[]
      availableExtensions: string[]
      availablePrefixes: string[]
      activeFiltersCount: number
      currentScope: string
      isRecursive: boolean
      appVersion: string
      ffmpegAvailable: boolean
      streamThreshold: number
    }>(`${BASE}/api/folder/${folderKey}${qs}`)
  },
}

export const mediaApi = {
  getNodeSummary: (fileId: string) =>
    request<{ status: string; summary: unknown[]; meta: Record<string, unknown> }>(`${BASE}/node_summary/${fileId}`),

  compareFiles: (idA: string, idB: string) =>
    post<{ status: string; diff: Array<{ key: string; val_a: string; val_b: string; is_diff: boolean }> }>(`${BASE}/api/compare_files`, { id_a: idA, id_b: idB }),

  /** Returns raw URL strings — not fetched, used as src attributes */
  fileUrl: (fileId: string) => `${BASE}/file/${fileId}`,
  thumbnailUrl: (fileId: string) => `${BASE}/thumbnail/${fileId}`,
  downloadUrl: (fileId: string) => `${BASE}/download/${fileId}`,
  workflowUrl: (fileId: string) => `${BASE}/workflow/${fileId}`,
  streamUrl: (fileId: string) => `${BASE}/stream/${fileId}`,
  storyboardUrl: (fileId: string) => `${BASE}/storyboard/${fileId}`,
}
