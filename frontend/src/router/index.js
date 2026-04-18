import { createRouter, createWebHistory } from 'vue-router'
import { fetchJson } from '../api/client.js'
import {
  getAdminToken,
  isAdminAuthRequired,
} from '../auth/session.js'
import AdminLoginView from '../views/AdminLoginView.vue'
import HomeView from '../views/HomeView.vue'
import UsersPage from '../views/UsersPage.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  {
    path: '/admin/login',
    name: 'admin-login',
    component: AdminLoginView,
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: UsersPage,
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

function isAdminProtectedRoute(to) {
  if (to.path === '/admin/login') return false
  return to.path.startsWith('/admin/')
}

router.beforeEach(async (to, _from, next) => {
  const isAdminSection = isAdminProtectedRoute(to)

  if (isAdminSection) {
    const required = await isAdminAuthRequired(() =>
      fetchJson('/api/auth/status'),
    )
    if (required && !getAdminToken()) {
      return next({
        name: 'admin-login',
        query: { redirect: to.fullPath },
      })
    }
  }

  if (to.name === 'admin-login') {
    const required = await isAdminAuthRequired(() =>
      fetchJson('/api/auth/status'),
    )
    if (!required) {
      return next({ path: '/' })
    }
    if (getAdminToken()) {
      const r = to.query.redirect
      return next(typeof r === 'string' && r ? r : '/admin/users')
    }
  }

  return next()
})
