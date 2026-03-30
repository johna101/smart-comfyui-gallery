<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { folderApi } from '@/api/gallery'
import { RefreshCcw } from 'lucide-vue-next'

const props = defineProps<{
  jobId: string
}>()

const emit = defineEmits<{
  complete: []
  error: []
}>()

const current = ref(0)
const total = ref(0)
const status = ref('running')
let pollTimer: ReturnType<typeof setInterval> | null = null

async function checkStatus() {
  try {
    const data = await folderApi.checkRescanStatus(props.jobId)
    current.value = data.current
    total.value = data.total
    status.value = data.status

    if (data.status === 'complete' || data.status === 'done') {
      stopPolling()
      emit('complete')
    }
  } catch (e) {
    stopPolling()
    emit('error')
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  checkStatus()
  pollTimer = setInterval(checkStatus, 1000)
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="px-4 py-2 border-t border-white/5 flex items-center gap-3">
    <div class="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
      <div
        class="h-full bg-green-500 rounded-full transition-all duration-300"
        :style="{ width: total > 0 ? `${(current / total) * 100}%` : '0%' }"
      />
    </div>
    <span class="text-xs text-white/50 whitespace-nowrap">
      <RefreshCcw :size="12" class="inline-block animate-spin" /> Rescanning {{ current }}/{{ total }}
    </span>
  </div>
</template>
