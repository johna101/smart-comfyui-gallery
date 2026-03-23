import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

// Router stub — routes will be added in Phase 6
const router = createRouter({
  history: createWebHistory(),
  routes: [],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Mount into the dedicated Vue container (not the main #app used by legacy code)
app.mount('#vue-app')
