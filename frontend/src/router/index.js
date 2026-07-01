import { createRouter, createWebHistory } from 'vue-router'
import { defaultPathAfterLogin, isAdminRole } from '../auth/permissions.js'
import {
  consumeCabinetSsoFragment,
  clearSession,
  getAccessToken,
  getSessionRole,
} from '../auth/session.js'
import { ensureIpBlockStatus } from '../auth/ipBlock.js'
import { buildSeoPageRoutes } from '../content/seo/index.js'

/**
 * ВНИМАНИЕ: с момента переноса админки на отдельный домен (frontend-admin, ADMIN_SITE_ADDRESS)
 * публичный SPA больше НЕ содержит роутов /admin/*. Файлы во frontend/src/views/Admin*.vue,
 * components/Admin*.vue и т.п. физически остаются (их через vite alias @legacy-* импортирует
 * frontend-admin), но здесь они не роутятся и не попадают в клиентский бандл (tree-shaking
 * по import chunks — админские import()'ы удалены отсюда).
 *
 * Всё, что осталось: лендинг, кабинет пользователя, аутентификация клиента, юридические
 * страницы, SEO-лендинги и подписка.
 */
const HomeView = () => import('../views/HomeView.vue')
const UserLoginView = () => import('../views/UserLoginView.vue')
const UserRegisterView = () => import('../views/UserRegisterView.vue')
const VerifyEmailView = () => import('../views/VerifyEmailView.vue')
const EmailVerificationPendingView = () =>
  import('../views/EmailVerificationPendingView.vue')
const LinkFromTelegramView = () => import('../views/LinkFromTelegramView.vue')
const UserCabinetView = () => import('../views/UserCabinetView.vue')
const CabinetInstructionsView = () =>
  import('../views/CabinetInstructionsView.vue')
const CabinetSupportView = () => import('../views/CabinetSupportView.vue')
const CabinetPayView = () => import('../views/CabinetPayView.vue')
const CabinetPayReturnView = () => import('../views/CabinetPayReturnView.vue')
const CabinetPayReturnBotView = () => import('../views/CabinetPayReturnBotView.vue')
const SubscriptionOpenView = () => import('../views/SubscriptionOpenView.vue')
const LegalDocumentView = () => import('../views/LegalDocumentView.vue')
const BlockedIpView = () => import('../views/BlockedIpView.vue')
const seoPageRoutes =
  import.meta.env.VITE_DISABLE_SEO_PAGES === 'true' ? [] : buildSeoPageRoutes()

const routes = [
  {
    path: '/blocked',
    name: 'blocked',
    component: BlockedIpView,
    meta: { minimalChrome: true },
  },
  { path: '/', name: 'home', component: HomeView, meta: { seoPage: true, seoPath: '/' } },
  { path: '/login', name: 'login', component: UserLoginView, meta: { noindex: true } },
  { path: '/register', name: 'register', component: UserRegisterView, meta: { noindex: true } },
  {
    path: '/verify-email',
    name: 'verify-email',
    component: VerifyEmailView,
    meta: { noindex: true },
  },
  {
    path: '/verify-email-pending',
    name: 'verify-email-pending',
    component: EmailVerificationPendingView,
    meta: { noindex: true },
  },
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
    meta: { legalDoc: 'consent', noindex: true },
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
    path: '/marketing',
    name: 'legal-marketing',
    component: LegalDocumentView,
    meta: { legalDoc: 'marketing', noindex: true },
  },
  ...seoPageRoutes,
  {
    path: '/link-from-telegram',
    name: 'link-from-telegram',
    component: LinkFromTelegramView,
    meta: { noindex: true },
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
  // Любые попытки перейти на /admin/* — редиректим на главную (админка переехала на ADMIN_SITE_ADDRESS).
  {
    path: '/admin/:pathMatch(.*)*',
    redirect: { name: 'login' },
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

router.beforeEach(async (to, _from, next) => {
  if (consumeCabinetSsoFragment(to.name)) {
    return next({ name: 'cabinet', replace: true })
  }

  const ipBlocked = await ensureIpBlockStatus()
  if (ipBlocked && to.name !== 'blocked') {
    return next({ name: 'blocked', replace: true })
  }
  if (!ipBlocked && to.name === 'blocked') {
    return next({ path: '/', replace: true })
  }

  const token = getAccessToken()
  const role = getSessionRole()

  // Устаревший JWT с ролью admin/manager (из users до переноса админки) — сбрасываем.
  const isCabinetRoute =
    to.name === 'cabinet' ||
    to.name === 'cabinet-instructions' ||
    to.name === 'cabinet-support' ||
    to.name === 'cabinet-pay' ||
    to.name === 'cabinet-pay-return'
  if (isCabinetRoute && token && (isAdminRole(role) || role === 'manager')) {
    clearSession()
    return next({
      name: 'login',
      query: { redirect: to.fullPath },
    })
  }

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
    if (isAdminRole(role) || role === 'manager') {
      // На публичном сайте для admin/manager кабинета нет. Сессию не сбрасываем
      // (её отдал старый /api/auth/login), но UI-навигация ведёт на главную.
      return next({ path: '/' })
    }
    return next({ path: defaultPathAfterLogin(role) })
  }

  return next()
})
