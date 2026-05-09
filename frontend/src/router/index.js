import { createRouter, createWebHistory } from 'vue-router'
import {
  canAccessReferralsAdmin,
  defaultPathAfterLogin,
  isAdminRole,
} from '../auth/permissions.js'
import {
  consumeCabinetSsoFragment,
  getAccessToken,
  getSessionRole,
  isAdminJwtRequired,
} from '../auth/session.js'

/**
 * Ленивые импорты вью: каждый роут — отдельный chunk.
 * Посетитель лендинга `/` не грузит админку и Chart.js.
 */
const HomeView = () => import('../views/HomeView.vue')
const UserLoginView = () => import('../views/UserLoginView.vue')
const UserRegisterView = () => import('../views/UserRegisterView.vue')
const LinkFromTelegramView = () => import('../views/LinkFromTelegramView.vue')
const UserCabinetView = () => import('../views/UserCabinetView.vue')
const SubscriptionOpenView = () => import('../views/SubscriptionOpenView.vue')
const AdminTablesPage = () => import('../views/AdminTablesPage.vue')
const ReferralFunnelView = () => import('../views/ReferralFunnelView.vue')
const ReferralTokensAdminPage = () =>
  import('../views/ReferralTokensAdminPage.vue')
const RegistrationsByDateStaffView = () =>
  import('../views/RegistrationsByDateStaffView.vue')
const ServerAnalyticsView = () => import('../views/ServerAnalyticsView.vue')
const UserAnalyticsView = () => import('../views/UserAnalyticsView.vue')
const UsersAnalyticsStaffView = () =>
  import('../views/UsersAnalyticsStaffView.vue')

const AdminHttpRequestLogsView = () =>
  import('../views/AdminHttpRequestLogsView.vue')
const AdminSubscriptionUserAgentStatsView = () =>
  import('../views/AdminSubscriptionUserAgentStatsView.vue')
const AdminServersReachabilityView = () =>
  import('../views/AdminServersReachabilityView.vue')
const AdminPaymentsStaffView = () =>
  import('../views/AdminPaymentsStaffView.vue')
const AdminTasksStaffView = () => import('../views/AdminTasksStaffView.vue')

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
    redirect: { name: 'cabinet' },
  },
  {
    path: '/sub/:token/open/:client',
    name: 'subscription-open',
    component: SubscriptionOpenView,
  },
  {
    path: '/admin/logs',
    name: 'admin-http-logs',
    component: AdminHttpRequestLogsView,
  },
  {
    path: '/admin/referrals',
    name: 'admin-referrals',
    component: ReferralTokensAdminPage,
  },
  {
    path: '/admin/payments',
    name: 'admin-payments-staff',
    component: AdminPaymentsStaffView,
  },
  {
    path: '/admin/tasks',
    name: 'admin-tasks-staff',
    component: AdminTasksStaffView,
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
    path: '/admin/users/subscription-user-agent-stats',
    name: 'admin-subscription-user-agent-stats',
    component: AdminSubscriptionUserAgentStatsView,
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
    path: '/admin/servers/reachability',
    name: 'admin-servers-reachability',
    component: AdminServersReachabilityView,
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
  if (consumeCabinetSsoFragment(to.name)) {
    return next({ name: 'cabinet', replace: true })
  }

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
      const isHttpLogsStaff = to.name === 'admin-http-logs'
      const isSubscriptionUaStatsStaff =
        to.name === 'admin-subscription-user-agent-stats'
      const isPaymentsStaff = to.name === 'admin-payments-staff'
      const isTasksStaff = to.name === 'admin-tasks-staff'
      if (
        isReferralsRoute ||
        isUsersAnalyticsStaff ||
        isMarketingFunnel ||
        isRegistrationsByDate ||
        isHttpLogsStaff ||
        isSubscriptionUaStatsStaff ||
        isPaymentsStaff ||
        isTasksStaff
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
