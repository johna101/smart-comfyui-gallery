import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/** Transient UI state — not persisted. */
export const useUiStore = defineStore('ui', () => {
  // --- Lightbox ---
  const lightboxOpen = ref(false)
  const lightboxIndex = ref(-1)
  const lightboxFileId = ref<string | null>(null)

  // --- Modals ---
  const currentModal = ref<string | null>(null) // 'upload' | 'rescan' | 'mount' | 'compare' | etc.

  // --- Selection bar ---
  const selectionBarVisible = computed(() => {
    // Will be driven by gallery store's selectedFiles.size > 0
    return false
  })

  // --- Actions ---
  function openLightbox(fileId: string, index: number) {
    lightboxFileId.value = fileId
    lightboxIndex.value = index
    lightboxOpen.value = true
  }

  function closeLightbox() {
    lightboxOpen.value = false
    lightboxIndex.value = -1
    lightboxFileId.value = null
  }

  function openModal(name: string) {
    currentModal.value = name
  }

  function closeModal() {
    currentModal.value = null
  }

  return {
    lightboxOpen, lightboxIndex, lightboxFileId,
    currentModal, selectionBarVisible,
    openLightbox, closeLightbox, openModal, closeModal,
  }
})
