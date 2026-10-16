import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'subscriptions', component: () => import('./views/Subscriptions.vue') },
    { path: '/new', name: 'new', component: () => import('./views/SubscriptionEdit.vue') },
    { path: '/sub/:id', name: 'subscription', component: () => import('./views/SubscriptionDetail.vue'), props: true },
    { path: '/sub/:id/edit', name: 'edit', component: () => import('./views/SubscriptionEdit.vue'), props: true },
    { path: '/jobs', name: 'jobs', component: () => import('./views/Jobs.vue') },
    { path: '/sources', name: 'sources', component: () => import('./views/Sources.vue') },
    { path: '/settings', name: 'settings', component: () => import('./views/Settings.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')
