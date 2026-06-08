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
import { fetchJson } from '../api/client.js'

/**
 * Ленивые импорты вью: каждый роут — отдельный chunk.
 * Посетитель лендинга `/` не грузит админку и Chart.js.
 */
const HomeView = () => import('../views/HomeView.vue')
const UserLoginView = () => import('../views/UserLoginView.vue')
const UserRegisterView = () => import('../views/UserRegisterView.vue')
const LinkFromTelegramView = () => import('../views/LinkFromTelegramView.vue')
const UserCabinetView = () => import('../views/UserCabinetView.vue')
const CabinetInstructionsView = () =>
  import('../views/CabinetInstructionsView.vue')
const CabinetSupportView = () => import('../views/CabinetSupportView.vue')
const CabinetPayView = () => import('../views/CabinetPayView.vue')
const CabinetPayReturnView = () => import('../views/CabinetPayReturnView.vue')
const CabinetPayReturnBotView = () => import('../views/CabinetPayReturnBotView.vue')
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
const AdminFinanceStaffView = () =>
  import('../views/AdminFinanceStaffView.vue')
const AdminTasksStaffView = () => import('../views/AdminTasksStaffView.vue')
const AdminSupportStaffView = () => import('../views/AdminSupportStaffView.vue')
const LegalDocumentView = () => import('../views/LegalDocumentView.vue')

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: UserLoginView },
  { path: '/register', name: 'register', component: UserRegisterView },
  {
    path: '/terms',
    name: 'legal-terms',
    component: LegalDocumentView,
    meta: { legalDoc: 'terms' },
  },
  {
    path: '/privacy',
    name: 'legal-privacy',
    component: LegalDocumentView,
    meta: { legalDoc: 'privacy' },
  },
  {
    path: '/consent',
    name: 'legal-consent',
    component: LegalDocumentView,
    meta: { legalDoc: 'consent' },
  },
  {
    path: '/refund',
    name: 'legal-refund',
    component: LegalDocumentView,
    meta: { legalDoc: 'refund' },
  },
  {
    path: '/cookies',
    name: 'legal-cookies',
    component: LegalDocumentView,
    meta: { legalDoc: 'cookies' },
  },
  {
    path: '/link-from-telegram',
    name: 'link-from-telegram',
    component: LinkFromTelegramView,
  },
  { path: '/cabinet', name: 'cabinet', component: UserCabinetView },
  {
    path: '/cabinet/instructions',
    name: 'cabinet-instructions',
    component: CabinetInstructionsView,
  },
  {
    path: '/cabinet/support',
    name: 'cabinet-support',
    component: CabinetSupportView,
  },
  {
    path: '/cabinet/pay',
    name: 'cabinet-pay',
    component: CabinetPayView,
  },
  {
    path: '/cabinet/pay/return/bot',
    name: 'cabinet-pay-return-bot',
    component: CabinetPayReturnBotView,
  },
  {
    path: '/cabinet/pay/return',
    name: 'cabinet-pay-return',
    component: CabinetPayReturnView,
  },
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
    path: '/admin/finance',
    name: 'admin-finance-staff',
    component: AdminFinanceStaffView,
  },
  {
    path: '/admin/tasks',
    name: 'admin-tasks-staff',
    component: AdminTasksStaffView,
  },
  {
    path: '/admin/support',
    name: 'admin-support-staff',
    component: AdminSupportStaffView,
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
  { path: '/admin/users', redirect: '/admin/users/analytics' },
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
        : { path: '/admin/users/analytics' },
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    }
    if (to.hash) {
      return { el: to.hash, behavior: 'smooth' }
    }
    return { top: 0, left: 0 }
  },
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

  if (
    (to.name === 'cabinet' ||
      to.name === 'cabinet-instructions' ||
      to.name === 'cabinet-support' ||
      to.name === 'cabinet-pay' ||
      to.name === 'cabinet-pay-return') &&
    !token
  ) {
    return next({
      name: 'login',
      query: { redirect: to.fullPath },
    })
  }

  if ((to.name === 'login' || to.name === 'register') && token) {
    if (isAdminRole(role)) {
      return next({ path: '/admin/users/analytics' })
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
      const isUserPerAnalytics = to.name === 'admin-user-analytics'
      const isMarketingFunnel = to.name === 'admin-funnel'
      const isRegistrationsByDate = to.name === 'admin-users-registrations-by-date'
      const isHttpLogsStaff = to.name === 'admin-http-logs'
      const isSubscriptionUaStatsStaff =
        to.name === 'admin-subscription-user-agent-stats'
      const isPaymentsStaff = to.name === 'admin-payments-staff'
      const isFinanceStaff = to.name === 'admin-finance-staff'
      const isTasksStaff = to.name === 'admin-tasks-staff'
      const isSupportStaff = to.name === 'admin-support-staff'
      if (
        isReferralsRoute ||
        isUsersAnalyticsStaff ||
        isUserPerAnalytics ||
        isMarketingFunnel ||
        isRegistrationsByDate ||
        isHttpLogsStaff ||
        isSubscriptionUaStatsStaff ||
        isPaymentsStaff ||
        isFinanceStaff ||
        isTasksStaff ||
        isSupportStaff
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
