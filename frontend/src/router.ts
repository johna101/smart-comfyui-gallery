import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/galleryout/view/:folderKey',
      name: 'folder',
      // No component — App.vue is always the layout.
      // The route just drives which folder is loaded via the store.
      component: { template: '' },
    },
    {
      // Catch-all: redirect to root folder
      path: '/:pathMatch(.*)*',
      redirect: '/galleryout/view/_root_',
    },
  ],
})

export default router
