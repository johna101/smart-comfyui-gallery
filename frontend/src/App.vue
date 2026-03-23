<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import { usePreferencesStore } from '@/stores/preferences'
import LightboxViewer from '@/components/lightbox/LightboxViewer.vue'
import GalleryGrid from '@/components/gallery/GalleryGrid.vue'
import SelectionBar from '@/components/gallery/SelectionBar.vue'

const gallery = useGalleryStore()
const ui = useUiStore()
const preferences = usePreferencesStore()

onMounted(() => {
  gallery.initFromServer()
  console.log(
    '%c🖼️ SmartGallery Vue mounted',
    'color: #28a045; font-weight: bold; font-size: 14px;'
  )
  console.log(`  Folders: ${Object.keys(gallery.folders).length}`)
  console.log(`  Files: ${gallery.files.length}`)
  console.log(`  Current folder: ${gallery.currentFolderKey}`)

  // --- Hide legacy gallery elements ---
  const legacyGallery = document.getElementById('gallery-container')
  const legacyLoadMore = document.getElementById('load-more-container')
  const legacySelectionBar = document.getElementById('selection-bar')
  if (legacyGallery) legacyGallery.style.display = 'none'
  if (legacyLoadMore) legacyLoadMore.style.display = 'none'
  if (legacySelectionBar) legacySelectionBar.style.display = 'none'

  // --- Legacy JS bridge ---
  // Expose function for legacy openLightbox to call into Vue
  ;(window as any).__vueOpenLightbox = (fileId: string) => {
    const index = gallery.files.findIndex(f => f.id === fileId)
    if (index >= 0) {
      ui.openLightbox(fileId, index)
      return true
    }
    return false
  }

  ;(window as any).__vueCloseLightbox = () => {
    ui.closeLightbox()
  }

  // Bridge: legacy focus mode toggle → Vue preferences
  ;(window as any).__vueSetFocusMode = (active: boolean) => {
    preferences.focusMode = active
  }

  console.log('  Legacy bridge: registered')
})
</script>

<template>
  <div id="vue-root">
    <GalleryGrid />
    <SelectionBar />
    <LightboxViewer />
  </div>
</template>
