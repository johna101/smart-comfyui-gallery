<script setup lang="ts">
import { onMounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'

const gallery = useGalleryStore()

onMounted(() => {
  gallery.initFromServer()
  console.log(
    '%c🖼️ SmartGallery Vue mounted',
    'color: #28a745; font-weight: bold; font-size: 14px;'
  )
  console.log(`  Folders: ${Object.keys(gallery.folders).length}`)
  console.log(`  Files: ${gallery.files.length}`)
  console.log(`  Current folder: ${gallery.currentFolderKey}`)
})
</script>

<template>
  <!-- Vue components will be mounted here incrementally.
       During migration, this is mostly empty — the legacy HTML
       still handles rendering. Vue takes over component by component. -->
  <div id="vue-root">
    <!-- Phase 2: LightboxViewer will go here -->
  </div>
</template>
