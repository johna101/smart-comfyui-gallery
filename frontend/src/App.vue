<script setup lang="ts">
import { onMounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import { useUiStore } from '@/stores/ui'
import LightboxViewer from '@/components/lightbox/LightboxViewer.vue'

const gallery = useGalleryStore()
const ui = useUiStore()

onMounted(() => {
  gallery.initFromServer()
  console.log(
    '%c🖼️ SmartGallery Vue mounted',
    'color: #28a045; font-weight: bold; font-size: 14px;'
  )
  console.log(`  Folders: ${Object.keys(gallery.folders).length}`)
  console.log(`  Files: ${gallery.files.length}`)
  console.log(`  Current folder: ${gallery.currentFolderKey}`)

  // --- Legacy JS bridge ---
  // Expose function for legacy openLightbox to call into Vue
  ;(window as any).__vueOpenLightbox = (fileId: string) => {
    const index = gallery.files.findIndex(f => f.id === fileId)
    if (index >= 0) {
      ui.openLightbox(fileId, index)
      return true // Signal that Vue handled it
    }
    return false // File not found in Vue store, let legacy handle it
  }

  ;(window as any).__vueCloseLightbox = () => {
    ui.closeLightbox()
  }

  console.log('  Legacy bridge: __vueOpenLightbox registered')
})
</script>

<template>
  <div id="vue-root">
    <LightboxViewer />
  </div>
</template>
