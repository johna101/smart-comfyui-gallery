<script setup lang="ts">
import { useScanProgress } from '@/composables/useEventStream'

const scan = useScanProgress()
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="scan.scanning" class="scan-overlay">
        <div class="scan-card">
          <div class="scan-spinner" />
          <div class="scan-text">
            <template v-if="scan.phase === 'started' || scan.total === 0">
              Scanning files...
            </template>
            <template v-else>
              Processing {{ scan.processed.toLocaleString() }} / {{ scan.total.toLocaleString() }} files
            </template>
          </div>
          <div v-if="scan.total > 0" class="scan-bar-track">
            <div
              class="scan-bar-fill"
              :style="{ width: `${Math.min(100, (scan.processed / scan.total) * 100)}%` }"
            />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
@reference "tailwindcss";

.scan-overlay {
  @apply fixed inset-0 z-[9999] flex items-center justify-center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.scan-card {
  @apply flex flex-col items-center gap-4 px-10 py-8 rounded-2xl;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  min-width: 320px;
}

.scan-spinner {
  @apply w-8 h-8 rounded-full;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: #60a5fa;
  animation: spin 0.8s linear infinite;
}

.scan-text {
  @apply text-sm text-neutral-300 text-center;
}

.scan-bar-track {
  @apply w-full h-1.5 rounded-full overflow-hidden;
  background: rgba(255, 255, 255, 0.1);
}

.scan-bar-fill {
  @apply h-full rounded-full;
  background: #60a5fa;
  transition: width 0.3s ease;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
