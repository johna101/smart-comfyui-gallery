import { ref, readonly } from 'vue'

// Singleton reactive state — shared across all consumers
const message = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

/**
 * Global toast notification composable.
 * All callers share the same reactive state — only one toast visible at a time.
 */
export function useToast() {
  function show(msg: string, duration = 2000) {
    message.value = msg
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { message.value = '' }, duration)
  }

  return {
    /** Current toast message (empty string = hidden) */
    message: readonly(message),
    /** Show a toast for `duration` ms (default 2000) */
    show,
  }
}
