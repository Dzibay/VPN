import { createRouter, createWebHistory } from 'vue-router'
import { getAccessToken, getSessionRole, isAdminJwtRequired } from '../auth/session.js'
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
  return to.path.startsWith('/admin')
}

router.beforeEach(async (to, _from, next) => {
  const token = getAccessToken()
  const role = getSessionRole()

  if (to.name === 'cabinet' && !token) {
    return next({
      name: 'login',
      query: { redirect: to.fullPath },
    })
  }

  if ((to.name === 'login' || to.name === 'register') && token) {
    if (role === 'admin') {
      return next({ path: '/admin' })
    }
    return next({ path: '/cabinet' })
  }

  const isAdminSection = isAdminProtectedRoute(to)

  if (isAdminSection) {
    const required = await isAdminJwtRequired()
    if (required) {
      if (!token) {
        return next({
          name: 'login',
          query: { redirect: to.fullPath },
        })
      }
      if (role !== 'admin') {
        return next({ path: '/cabinet' })
      }
    }
  }

  return next()
})
