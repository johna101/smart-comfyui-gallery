<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGalleryStore } from '@/stores/gallery'
import { useEventStream } from '@/composables/useEventStream'
import FolderSidebar from '@/components/sidebar/FolderSidebar.vue'
import GalleryToolbar from '@/components/toolbar/GalleryToolbar.vue'
import LightboxViewer from '@/components/lightbox/LightboxViewer.vue'
import GalleryGrid from '@/components/gallery/GalleryGrid.vue'
import SelectionBar from '@/components/gallery/SelectionBar.vue'

const gallery = useGalleryStore()
useEventStream()
const router = useRouter()
const route = useRoute()

// Handle back/forward navigation — when URL changes externally
watch(
  () => route.params.folderKey as string,
  (newKey, oldKey) => {
    if (newKey && newKey !== oldKey && newKey !== gallery.currentFolderKey) {
      const queryParams = Object.keys(route.query).length
        ? Object.fromEntries(Object.entries(route.query).map(([k, v]) => [k, String(v)]))
        : undefined
      gallery.loadFolder(newKey, queryParams)
    }
  }
)

onMounted(() => {
  gallery.initFromServer()

  // Replace the initial URL to match what Flask served
  router.replace({
    name: 'folder',
    params: { folderKey: gallery.currentFolderKey },
  })

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
