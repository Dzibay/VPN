import { createRouter, createWebHistory } from 'vue-router'
import { fetchJson } from '../api/client.js'
import {
  getAdminToken,
  getUserToken,
  isAdminAuthRequired,
} from '../auth/session.js'
import AdminLoginView from '../views/AdminLoginView.vue'
import AdminTablesPage from '../views/AdminTablesPage.vue'
import HomeView from '../views/HomeView.vue'
import ServerAnalyticsView from '../views/ServerAnalyticsView.vue'
import UserAnalyticsView from '../views/UserAnalyticsView.vue'
import UserCabinetView from '../views/UserCabinetView.vue'
import UserLoginView from '../views/UserLoginView.vue'
import UserRegisterView from '../views/UserRegisterView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: UserLoginView },
  { path: '/register', name: 'register', component: UserRegisterView },
  { path: '/cabinet', name: 'cabinet', component: UserCabinetView },
  {
    path: '/admin/login',
    name: 'admin-login',
    component: AdminLoginView,
  },
  {
    path: '/admin',
    name: 'admin-data',
    component: AdminTablesPage,
  },
  {
    path: '/admin/users/:userId/analytics',
    name: 'admin-user-analytics',
    component: UserAnalyticsView,
  },
  {
    path: '/admin/analytics',
    name: 'admin-analytics',
    component: ServerAnalyticsView,
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

function isAdminProtectedRoute(to) {
  if (to.path === '/admin/login') return false
  return to.path.startsWith('/admin')
}

router.beforeEach(async (to, _from, next) => {
  if (to.name === 'cabinet' && !getUserToken()) {
    return next({
      name: 'login',
      query: { redirect: to.fullPath },
    })
  }

  if ((to.name === 'login' || to.name === 'register') && getUserToken()) {
    return next({ path: '/cabinet' })
  }

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
      return next(typeof r === 'string' && r ? r : '/admin')
    }
  }

  return next()
})
