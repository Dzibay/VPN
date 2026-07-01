import { createRouter, createWebHistory } from 'vue-router'
import { hasStaffToken, getStaffProfile } from '../auth/staffSession.js'
import { canAccessRoute, defaultRouteForRole } from '../auth/roleAccess.js'

// ==== Родные view панели ====
const StaffLoginView = () => import('../views/StaffLoginView.vue')
const DashboardView = () => import('../views/DashboardView.vue')
const ProjectsAdminView = () => import('../views/ProjectsAdminView.vue')
const ProjectDetailView = () => import('../views/ProjectDetailView.vue')
const StaffUsersAdminView = () => import('../views/StaffUsersAdminView.vue')
const ProjectTariffsView = () => import('../views/ProjectTariffsView.vue')

// ==== Legacy admin view из ../frontend/src/views ====
// Работают через bridge: staff-JWT синхронизируется в vpn_access_token,
// глобальный fetch-interceptor добавляет X-Admin-Project.
const AdminPaymentsStaffView = () => import('@legacy-views/AdminPaymentsStaffView.vue')
const AdminFinanceStaffView = () => import('@legacy-views/AdminFinanceStaffView.vue')
const AdminTasksStaffView = () => import('@legacy-views/AdminTasksStaffView.vue')
const AdminSupportStaffView = () => import('@legacy-views/AdminSupportStaffView.vue')
const AdminTrafficStaffView = () => import('@legacy-views/AdminTrafficStaffView.vue')
const AdminHttpRequestLogsView = () => import('@legacy-views/AdminHttpRequestLogsView.vue')
const AdminBlockedIpsView = () => import('@legacy-views/AdminBlockedIpsView.vue')
const AdminSubscriptionUserAgentStatsView = () =>
  import('@legacy-views/AdminSubscriptionUserAgentStatsView.vue')
const AdminServersReachabilityView = () =>
  import('@legacy-views/AdminServersReachabilityView.vue')
const AdminTablesPage = () => import('@legacy-views/AdminTablesPage.vue')
const ServerAnalyticsView = () => import('@legacy-views/ServerAnalyticsView.vue')
const UsersAnalyticsStaffView = () => import('@legacy-views/UsersAnalyticsStaffView.vue')
const UserAnalyticsView = () => import('@legacy-views/UserAnalyticsView.vue')
const RegistrationsByDateStaffView = () =>
  import('@legacy-views/RegistrationsByDateStaffView.vue')
const ReferralFunnelView = () => import('@legacy-views/ReferralFunnelView.vue')
const ReferralTokensAdminPage = () => import('@legacy-views/ReferralTokensAdminPage.vue')
const SeoPagesAdminView = () => import('@legacy-views/SeoPagesAdminView.vue')

/**
 * meta.access соответствует правам из legacy `adminNavConfig.js`:
 *   - 'staff'            — все staff-роли (super_admin | admin | manager)
 *   - 'admin'            — super_admin | admin (в legacy это было admin_only)
 *   - 'super_admin_only' — только super_admin
 */
const routes = [
  { path: '/login', name: 'staff-login', component: StaffLoginView, meta: { public: true } },
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'staff-dashboard', component: DashboardView, meta: { access: 'staff' } },
  { path: '/admin/summary', redirect: '/dashboard' },

  // ==== Управление проектами / персоналом (только super_admin) ====
  { path: '/projects', name: 'staff-projects', component: ProjectsAdminView, meta: { access: 'super_admin_only' } },
  { path: '/projects/:id', name: 'staff-project-detail', component: ProjectDetailView, props: true, meta: { access: 'super_admin_only' } },
  { path: '/projects/:id/tariffs', name: 'staff-project-tariffs', component: ProjectTariffsView, props: true, meta: { access: 'super_admin_only' } },
  { path: '/staff-users', name: 'staff-users', component: StaffUsersAdminView, meta: { access: 'super_admin_only' } },

  // ==== Данные проекта (per-project через X-Admin-Project) ====
  { path: '/admin/payments', name: 'admin-payments', component: AdminPaymentsStaffView, meta: { access: 'staff' } },
  { path: '/admin/finance', name: 'admin-finance', component: AdminFinanceStaffView, meta: { access: 'staff' } },
  { path: '/admin/tasks', name: 'admin-tasks', component: AdminTasksStaffView, meta: { access: 'staff' } },
  { path: '/admin/support', name: 'admin-support', component: AdminSupportStaffView, meta: { access: 'staff' } },
  { path: '/admin/referrals', name: 'admin-referrals', component: ReferralTokensAdminPage, meta: { access: 'staff' } },
  { path: '/admin/funnel', name: 'admin-funnel', component: ReferralFunnelView, meta: { access: 'staff' } },
  { path: '/admin/seo-pages', name: 'admin-seo-pages', component: SeoPagesAdminView, meta: { access: 'staff' } },

  // Пользователи и аналитика (per-project).
  { path: '/admin/users', redirect: '/admin/users/analytics' },
  { path: '/admin/users/analytics', name: 'admin-users-analytics', component: UsersAnalyticsStaffView, meta: { access: 'staff' } },
  { path: '/admin/users/registrations-by-date', name: 'admin-users-regs', component: RegistrationsByDateStaffView, meta: { access: 'staff' } },
  { path: '/admin/users/subscription-user-agent-stats', name: 'admin-users-uastats', component: AdminSubscriptionUserAgentStatsView, meta: { access: 'staff' } },
  { path: '/admin/users/:userId/analytics', name: 'admin-user-analytics', component: UserAnalyticsView, props: true, meta: { access: 'staff' } },

  // Трафик и логи.
  { path: '/admin/traffic', name: 'admin-traffic', component: AdminTrafficStaffView, meta: { access: 'admin' } },
  { path: '/admin/logs', name: 'admin-http-logs', component: AdminHttpRequestLogsView, meta: { access: 'staff' } },
  { path: '/admin/blocked-ips', name: 'admin-blocked-ips', component: AdminBlockedIpsView, meta: { access: 'admin' } },

  // ==== Инфраструктура (общая, project-агностично) ====
  { path: '/infra/servers', name: 'infra-servers', component: AdminTablesPage, meta: { access: 'admin' } },
  { path: '/infra/servers/reachability', name: 'infra-servers-reach', component: AdminServersReachabilityView, meta: { access: 'admin' } },
  { path: '/infra/analytics', name: 'infra-analytics', component: ServerAnalyticsView, meta: { access: 'admin' } },

  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: (_to, _from, saved) => saved || { top: 0 },
})

router.beforeEach((to, _from, next) => {
  if (to.meta?.public) return next()
  if (!hasStaffToken()) {
    return next({
      name: 'staff-login',
      query: { redirect: to.fullPath !== '/dashboard' ? to.fullPath : undefined },
    })
  }
  const role = getStaffProfile()?.role || null
  const access = to.meta?.access
  if (access && !canAccessRoute(role, access)) {
    return next({ path: defaultRouteForRole(role) })
  }
  return next()
})
