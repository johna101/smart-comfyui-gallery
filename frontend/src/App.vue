<script setup lang="ts">
import { onMounted } from 'vue'
import { useGalleryStore } from '@/stores/gallery'
import FolderSidebar from '@/components/sidebar/FolderSidebar.vue'
import GalleryToolbar from '@/components/toolbar/GalleryToolbar.vue'
import LightboxViewer from '@/components/lightbox/LightboxViewer.vue'
import GalleryGrid from '@/components/gallery/GalleryGrid.vue'
import SelectionBar from '@/components/gallery/SelectionBar.vue'

const gallery = useGalleryStore()

onMounted(() => {
  gallery.initFromServer()
  console.log(
    '%c🖼️ SmartGallery Vue',
    'color: #28a045; font-weight: bold; font-size: 14px;',
    `${Object.keys(gallery.folders).length} folders, ${gallery.files.length} files`
  )
})
</script>

<template>
  <div id="vue-root" class="fixed inset-0 flex overflow-hidden bg-neutral-950">
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
