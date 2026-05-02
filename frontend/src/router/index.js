import { createRouter, createWebHistory } from 'vue-router'
import {
  canAccessReferralsAdmin,
  defaultPathAfterLogin,
  isAdminRole,
} from '../auth/permissions.js'
import { getAccessToken, getSessionRole, isAdminJwtRequired } from '../auth/session.js'
import AdminTablesPage from '../views/AdminTablesPage.vue'
import ReferralFunnelView from '../views/ReferralFunnelView.vue'
import ReferralTokensAdminPage from '../views/ReferralTokensAdminPage.vue'
import RegistrationsByDateStaffView from '../views/RegistrationsByDateStaffView.vue'
import HomeView from '../views/HomeView.vue'
import ServerAnalyticsView from '../views/ServerAnalyticsView.vue'
import UserAnalyticsView from '../views/UserAnalyticsView.vue'
import UsersAnalyticsStaffView from '../views/UsersAnalyticsStaffView.vue'
import UserCabinetView from '../views/UserCabinetView.vue'
import UserLoginView from '../views/UserLoginView.vue'
import UserRegisterView from '../views/UserRegisterView.vue'
import LinkFromTelegramView from '../views/LinkFromTelegramView.vue'
import ClientAppDownloadView from '../views/ClientAppDownloadView.vue'
import SubscriptionOpenView from '../views/SubscriptionOpenView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: UserLoginView },
  { path: '/register', name: 'register', component: UserRegisterView },
  {
    path: '/link-from-telegram',
    name: 'link-from-telegram',
    component: LinkFromTelegramView,
  },
  { path: '/cabinet', name: 'cabinet', component: UserCabinetView },
  {
    path: '/apps/:client',
    name: 'client-app-download',
    component: ClientAppDownloadView,
  },
  {
    path: '/sub/:token/open/:client',
    name: 'subscription-open',
    component: SubscriptionOpenView,
  },
  {
    path: '/admin/referrals',
    name: 'admin-referrals',
    component: ReferralTokensAdminPage,
  },
  {
    path: '/admin/funnel',
    name: 'admin-funnel',
    component: ReferralFunnelView,
  },
  {
    path: '/admin/users/analytics',
    name: 'admin-users-staff-analytics',
    component: UsersAnalyticsStaffView,
  },
  {
    path: '/admin/users/registrations-by-date',
    name: 'admin-users-registrations-by-date',
    component: RegistrationsByDateStaffView,
  },
  {
    path: '/admin/users/:userId/analytics',
    name: 'admin-user-analytics',
    component: UserAnalyticsView,
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: AdminTablesPage,
  },
  {
    path: '/admin/servers',
    name: 'admin-servers',
    component: AdminTablesPage,
  },
  {
    path: '/admin/analytics',
    name: 'admin-analytics',
    component: ServerAnalyticsView,
  },
  { path: '/admin/users-analytics', redirect: '/admin/users/analytics' },
  {
    path: '/admin',
    redirect: (to) =>
      to.query.tab === 'servers'
        ? { path: '/admin/servers' }
        : { path: '/admin/users' },
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
    if (isAdminRole(role)) {
      return next({ path: '/admin/users' })
    }
    if (role === 'manager') {
      return next({ path: '/admin/referrals' })
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
      const isReferralsRoute = to.name === 'admin-referrals'
      const isUsersAnalyticsStaff = to.name === 'admin-users-staff-analytics'
      const isMarketingFunnel = to.name === 'admin-funnel'
      const isRegistrationsByDate = to.name === 'admin-users-registrations-by-date'
      if (
        isReferralsRoute ||
        isUsersAnalyticsStaff ||
        isMarketingFunnel ||
        isRegistrationsByDate
      ) {
        if (!canAccessReferralsAdmin(role)) {
          return next({ path: '/cabinet' })
        }
      } else if (!isAdminRole(role)) {
        return next({
          path: defaultPathAfterLogin(role),
        })
      }
    }
  }

  return next()
})
