<script setup lang="ts">
import { onMounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import { usePreferencesStore } from '@/stores/preferences'
import FolderSidebar from '@/components/sidebar/FolderSidebar.vue'
import GalleryToolbar from '@/components/toolbar/GalleryToolbar.vue'
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

  // --- Hide legacy elements replaced by Vue ---
  const hide = (id: string) => {
    const el = document.getElementById(id)
    if (el) el.style.display = 'none'
  }
  hide('gallery-container')
  hide('load-more-container')
  hide('selection-bar')

  // Hide legacy sidebar
  const legacySidebar = document.querySelector('.sidebar') as HTMLElement
  if (legacySidebar) legacySidebar.style.display = 'none'

  // Hide legacy drop zone (replaced by Vue move dialog)
  hide('drag-drop-overlay')
  hide('drop-zone-panel')

  // Hide legacy toolbars (replaced by Vue GalleryToolbar)
  document.querySelectorAll('.toolbar-container').forEach(el => {
    ;(el as HTMLElement).style.display = 'none'
  })
  // Hide legacy search/filter panel
  hide('desktop-search-panel')

  // --- Legacy JS bridge ---
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

  ;(window as any).__vueSetFocusMode = (active: boolean) => {
    preferences.focusMode = active
  }

  console.log('  Legacy bridge: registered')
})
</script>

<template>
  <div id="vue-root" class="fixed inset-0 flex overflow-hidden z-[100] bg-neutral-950">
    <FolderSidebar />
    <div class="flex-1 flex flex-col overflow-hidden">
      <GalleryToolbar />
      <div class="flex-1 overflow-y-auto">
        <GalleryGrid />
      </div>
    </div>
    <SelectionBar />
    <LightboxViewer />
  </div>
</template>
