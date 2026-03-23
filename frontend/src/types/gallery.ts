// Type definitions for SmartGallery data structures

export interface GalleryFile {
  id: string
  path: string
  mtime: number
  name: string
  type: 'image' | 'animated_image' | 'video' | 'audio' | 'unknown'
  duration: string
  dimensions: string
  has_workflow: number
  is_favorite: number
  size: number
  last_scanned: number
  workflow_files: string
  workflow_prompt: string
  ai_caption?: string
  ai_last_scanned?: number
  score?: number // AI search score
}

export interface FolderInfo {
  display_name: string
  path: string
  real_path?: string
  relative_path: string
  parent: string | null
  children: string[]
  mtime: number
  is_watched: boolean
  is_explicitly_watched: boolean
  is_mount: boolean
}

export interface FoldersMap {
  [key: string]: FolderInfo
}

export interface Breadcrumb {
  key: string
  display_name: string
}

/** Data injected by Flask via window.__GALLERY_DATA__ */
export interface GalleryBootstrapData {
  folders: FoldersMap
  files: GalleryFile[]
  currentFolderKey: string
  currentFolderInfo: FolderInfo
  totalFiles: number
  totalFolderFiles: number
  totalDbFiles: number
  breadcrumbs: Breadcrumb[]
  ancestorKeys: string[]
  availableExtensions: string[]
  availablePrefixes: string[]
  prefixLimitReached: boolean
  selectedExtensions: string[]
  selectedPrefixes: string[]
  protectedFolderKeys: string[]
  showFavorites: boolean
  enableAiSearch: boolean
  isAiSearch: boolean
  aiQuery: string
  isGlobalSearch: boolean
  activeFiltersCount: number
  currentScope: string
  isRecursive: boolean
  appVersion: string
  githubUrl: string
  updateAvailable: boolean
  remoteVersion: string | null
  ffmpegAvailable: boolean
  streamThreshold: number
}

declare global {
  interface Window {
    __GALLERY_DATA__?: GalleryBootstrapData
  }
}
