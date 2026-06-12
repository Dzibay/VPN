/**
 * Общее состояние и данные лендинга (главная + SEO-страницы).
 */
import {
  computed,
  inject,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
} from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Building2,
  CheckCircle2,
  Gauge,
  Clock,
  Gift,
  Globe,
  Headphones,
  HelpCircle,
  Lock,
  MapPin,
  MessageCircle,
  Monitor,
  RefreshCw,
  Rocket,
  Route,
  Send,
  Shield,
  ShieldCheck,
  Smartphone,
  Star,
  Wifi,
  Zap,
} from 'lucide-vue-next'
import { getAccessToken, getSessionRole } from '../auth/session.js'
import { defaultPathAfterLogin } from '../auth/permissions.js'
import { sitePublicUrl, fetchJson } from '../api/client.js'
import { LEGAL_FOOTER_LINKS, SUPPORT_TELEGRAM } from '../content/legal.js'
import { buildLandingPlans, useYookassaPricing } from './useYookassaPricing.js'

export const LANDING_PAGE_KEY = Symbol('landingPage')

/** @type {const} */
export const HOME_IMAGES = {
  bgMap: '/images/home/hero-bg-map.png',
  appMockup: '/images/home/hero-app-mockup.png',
  trustAvatars: '/images/home/trust-avatars.png',
  logoWordmark: '/images/home/header-logo.png',
  logoWordmarkDark: '/images/home/header-logo-white.png',
}

export function createLandingPageContext() {
  const router = useRouter()
  const hasToken = ref(false)
  const sessionRole = ref(null)

  function refreshAuth() {
    hasToken.value = Boolean(getAccessToken())
    sessionRole.value = getSessionRole()
  }

  const isLoggedIn = computed(() => hasToken.value)
  const loggedInHomeCtaPath = computed(() =>
    defaultPathAfterLogin(sessionRole.value),
  )

  router.afterEach(refreshAuth)

  const footerHighlights = [
    { icon: Shield, title: 'Надёжность', text: 'Шифрование военного уровня и защита данных' },
    { icon: Zap, title: 'Скорость', text: 'Стабильное соединение без потери скорости' },
    { icon: Globe, title: 'Доступность', text: 'Сервисы и сайты доступны по всему миру' },
    { icon: MessageCircle, title: 'Поддержка', text: 'Мы рядом 24/7 и готовы помочь в любой момент' },
  ]

  const footerPayBrands = [
    { src: '/images/pay-brands/visa.png', alt: 'Visa' },
    { src: '/images/pay-brands/mastercard.png', alt: 'Mastercard' },
    { src: '/images/pay-brands/mir.png', alt: 'Мир' },
  ]

  const heroMiniFeatures = [
    { icon: Lock, title: 'Защита данных', text: 'Шифрование военного уровня' },
    { icon: Globe, title: 'Доступ без границ', text: 'Обход блокировок и ограничений' },
    { icon: Zap, title: 'Высокая скорость', text: 'Стабильное соединение без потери скорости' },
  ]

  const whyChooseFeatures = [
    { icon: Shield, title: 'Надёжная защита', text: 'Шифрование AES-256 защищает ваши данные в любой сети.' },
    { icon: Globe, title: 'Доступ к любому контенту', text: 'Смотрите, слушайте и играйте без ограничений из любой точки мира.' },
    { icon: Zap, title: 'Стабильная скорость', text: 'Оптимизированные серверы обеспечивают высокую скорость соединения.' },
    { icon: Monitor, title: 'До 5 устройств', text: 'Используйте VPN на всех ваших устройствах одновременно.' },
    { icon: Headphones, title: 'Поддержка 24/7', text: 'Наша команда всегда готова помочь вам в любое время.' },
  ]

  const HOW_APP_ICONS = { vpn: '/images/home/how/vpn', direct: '/images/home/how/direct' }

  const howVpnApps = [
    { id: 'youtube', label: 'YouTube', icon: `${HOW_APP_ICONS.vpn}/youtube.png` },
    { id: 'instagram', label: 'Instagram', icon: `${HOW_APP_ICONS.vpn}/instagram.png` },
    { id: 'gemini', label: 'Google Gemini', icon: `${HOW_APP_ICONS.vpn}/google-gemini.png` },
    { id: 'claude', label: 'Claude AI', icon: `${HOW_APP_ICONS.vpn}/claude.png` },
    { id: 'chatgpt', label: 'ChatGPT', icon: `${HOW_APP_ICONS.vpn}/chatgpt.png` },
    { id: 'telegram', label: 'Telegram', icon: `${HOW_APP_ICONS.vpn}/telegram.png` },
  ]

  const howDirectApps = [
    { id: 'sber', label: 'Сбербанк', icon: `${HOW_APP_ICONS.direct}/sberbank.png` },
    { id: 'tbank', label: 'Т-Банк', icon: `${HOW_APP_ICONS.direct}/tbank.png` },
    { id: 'gosuslugi', label: 'Госуслуги', icon: `${HOW_APP_ICONS.direct}/gosuslugi.png` },
    { id: 'kinopoisk', label: 'Кинопоиск', icon: `${HOW_APP_ICONS.direct}/kinopoisk.png` },
    { id: 'yandex-eda', label: 'Яндекс Еда', icon: `${HOW_APP_ICONS.direct}/yandex-eda.png` },
    { id: 'wildberries', label: 'Wildberries', icon: `${HOW_APP_ICONS.direct}/wildberries.png` },
  ]

  const howVpnPerks = [
    { icon: Shield, text: 'Максимальная конфиденциальность' },
    { icon: Zap, text: 'Быстрое соединение' },
    { icon: Globe, text: 'Доступ по всему миру' },
  ]

  const howDirectPerks = [
    { icon: Gauge, text: 'Без потери скорости' },
    { icon: Building2, text: 'Банки и госуслуги' },
    { icon: Wifi, text: 'Стабильный домашний IP' },
  ]

  const howHighlights = [
    {
      icon: Route,
      title: 'Автоматический выбор маршрута',
      text: 'Подорожник сам определяет, какой трафик пустить в туннель, а какой — напрямую',
    },
    {
      icon: CheckCircle2,
      title: 'Никаких сложных настроек',
      text: 'Включили VPN — split tunneling уже работает, списки сервисов обновляются на нашей стороне',
    },
  ]

  const trialFeatures = [
    { icon: Zap, title: 'Без привязки банковской карты', text: 'Никаких скрытых платежей и обязательств' },
    { icon: ShieldCheck, title: 'Полный доступ ко всем функциям', text: 'Все серверы, все устройства, без ограничений' },
    { icon: Smartphone, title: 'До 5 устройств одновременно', text: 'Подключайте все ваши устройства' },
  ]

  const trialVisualOrbit = [
    { icon: Globe, pos: 'tl' },
    { icon: Zap, pos: 'tr' },
    { icon: Lock, pos: 'bl' },
    { icon: Monitor, pos: 'br' },
  ]

  const planIncludes = [
    'Все функции Подорожник VPN',
    'Шифрование VLESS и умная маршрутизация',
    'До 5 устройств на одной подписке',
    'Поддержка 24/7',
  ]

  const pricingTrustTop = [
    { icon: ShieldCheck, text: 'Полный доступ ко всем функциям' },
    { icon: Globe, text: 'Стабильное соединение на всех серверах' },
    { icon: Smartphone, text: 'До 5 устройств на одной подписке' },
  ]

  const pricingBenefitsBottom = [
    { icon: Rocket, title: 'Молниеносная скорость', text: 'Без потери качества' },
    { icon: Lock, title: 'Без логов и слежки', text: 'Ваша приватность под защитой' },
    { icon: Globe, title: 'Проверенные локации', text: 'Стабильный доступ к нужным сервисам' },
    { icon: RefreshCw, title: 'Простое управление', text: 'Удобные приложения для всех платформ' },
  ]

  const LANDING_PLAN_MONTHS = [1, 6, 12]
  const LANDING_PLAN_META = {
    1: { displayName: 'Ежемесячная', periodBadge: '1 месяц', tagline: 'Идеально, чтобы попробовать сервис', ctaGuest: 'Оформить подписку' },
    6: { displayName: 'Полгода', periodBadge: '6 месяцев', tagline: 'Оптимальный баланс цены и срока', popular: true, ctaGuest: 'Подключить на полгода' },
    12: { displayName: 'Годовая', periodBadge: '12 месяцев', tagline: 'Максимальная выгода на длительный срок', ctaGuest: 'Подключить на год' },
  }

  const { loading: pricingLoading, tariffs, load: loadYookassaTariffs } = useYookassaPricing()
  const plans = computed(() => buildLandingPlans(tariffs.value, LANDING_PLAN_MONTHS, LANDING_PLAN_META))

  const faqs = [
    { q: 'Нужно ли выключать ВПН для оплаты картой?', a: 'Нет. Подорожник настроен так, что банковские приложения (Сбер, Т-Банк и др.) и Госуслуги работают через ваше прямое соединение, минуя VPN-сервер.' },
    { q: 'Будет ли работать Gemini и ChatGPT?', a: 'Да, все популярные ИИ-сервисы, включая Google Gemini, включены в список умной маршрутизации и открываются без проблем.' },
    { q: 'На каких устройствах работает Подорожник VPN?', a: 'Windows, macOS, Android, iOS, Linux и даже Android TV. Подключайтесь через клиенты с поддержкой VLESS — например V2Ray или Happ.' },
    { q: 'Сколько устройств можно подключить?', a: 'По одной подписке вы можете подключить до 5 устройств одновременно без потери скорости.' },
  ]

  const activeFaq = ref(null)
  const siteLinks = ref(null)

  function telegramUrlFromHandle(handle) {
    const user = String(handle || '').trim().replace(/^@/, '')
    return user ? `https://t.me/${user}` : null
  }

  const supportTelegramUrl = computed(() => {
    const fromApi = siteLinks.value?.support_telegram_url
    if (typeof fromApi === 'string' && fromApi.trim()) return fromApi.trim()
    return telegramUrlFromHandle(SUPPORT_TELEGRAM)
  })

  const supportTelegramLabel = computed(() => {
    const url = supportTelegramUrl.value
    if (!url) return SUPPORT_TELEGRAM
    const m = url.match(/t\.me\/([^/?#]+)/i)
    return m?.[1] ? `@${m[1]}` : SUPPORT_TELEGRAM
  })

  const footerProductLinks = computed(() => {
    const links = [
      { href: '#benefits', label: 'Преимущества' },
      { href: '#pricing', label: 'Тарифы' },
      { href: '#how', label: 'Устройства' },
      { href: '#faq', label: 'FAQ' },
    ]
    const supportUrl = supportTelegramUrl.value
    links.push(
      supportUrl
        ? { href: supportUrl, label: 'Поддержка', external: true }
        : { href: '#faq-support', label: 'Поддержка' },
    )
    return links
  })

  async function loadSiteLinks() {
    try {
      siteLinks.value = await fetchJson('/api/public/site-links')
    } catch {
      siteLinks.value = null
    }
  }

  const faqTrustHighlights = [
    { icon: Zap, title: 'Быстрые ответы', text: 'Не тратьте время на поиск' },
    { icon: ShieldCheck, title: 'Проверенная информация', text: 'Только актуальные данные' },
    { icon: MessageCircle, title: 'Помощь 24/7', text: 'Мы всегда рядом' },
    { icon: Lock, title: 'Конфиденциальность', text: 'Ваши данные под защитой' },
  ]

  const finalCtaFeatures = [
    { icon: Route, title: 'Умная маршрутизация', text: 'Зарубежное через VPN, своё — напрямую' },
    { icon: Shield, title: 'Фоновая защита', text: 'Работает незаметно и стабильно' },
    { icon: Lock, title: 'Без лишних действий', text: 'Никаких переключений и сложных настроек' },
  ]

  const finalVisualPins = [{ pos: 'tl' }, { pos: 'tr' }, { pos: 'bl' }, { pos: 'br' }]

  function toggleFaq(index) {
    activeFaq.value = activeFaq.value === index ? null : index
  }

  let faqLdEl = null

  function injectLandingJsonLd() {
    const origin = typeof window !== 'undefined' ? window.location.origin : sitePublicUrl()
    const base = origin?.replace(/\/$/, '') || ''
    const structured = {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'FAQPage',
          mainEntity: faqs.map((item) => ({
            '@type': 'Question',
            name: item.q,
            acceptedAnswer: { '@type': 'Answer', text: item.a },
          })),
        },
        {
          '@type': 'Organization',
          name: 'Подорожник VPN',
          ...(base ? { url: `${base}/` } : {}),
          description:
            'VPN-сервис с умным split tunneling и протоколом VLESS: зарубежные сервисы через защищённый туннель, российские банки и госуслуги — напрямую.',
        },
      ],
    }
    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.setAttribute('data-landing-faq-ld', '')
    script.textContent = JSON.stringify(structured)
    document.head.appendChild(script)
    faqLdEl = script
  }

  onMounted(() => {
    refreshAuth()
    void loadYookassaTariffs()
    void loadSiteLinks()
    injectLandingJsonLd()
  })

  onBeforeUnmount(() => {
    faqLdEl?.remove()
    faqLdEl = null
  })

  return {
    HOME_IMAGES,
    ArrowRight,
    Building2,
    CheckCircle2,
    Gauge,
    Clock,
    Gift,
    Globe,
    Headphones,
    HelpCircle,
    Lock,
    MapPin,
    MessageCircle,
    Monitor,
    RefreshCw,
    Rocket,
    Route,
    Send,
    Shield,
    ShieldCheck,
    Smartphone,
    Star,
    Wifi,
    Zap,
    LEGAL_FOOTER_LINKS,
    footerHighlights,
    footerPayBrands,
    heroMiniFeatures,
    whyChooseFeatures,
    howVpnApps,
    howDirectApps,
    howVpnPerks,
    howDirectPerks,
    howHighlights,
    trialFeatures,
    trialVisualOrbit,
    planIncludes,
    pricingTrustTop,
    pricingBenefitsBottom,
    pricingLoading,
    plans,
    faqs,
    activeFaq,
    toggleFaq,
    faqTrustHighlights,
    supportTelegramUrl,
    supportTelegramLabel,
    footerProductLinks,
    finalCtaFeatures,
    finalVisualPins,
    isLoggedIn,
    loggedInHomeCtaPath,
  }
}

/** @returns {ReturnType<typeof createLandingPageContext>} */
export function provideLandingPage() {
  const ctx = createLandingPageContext()
  provide(LANDING_PAGE_KEY, ctx)
  return ctx
}

/** @returns {ReturnType<typeof createLandingPageContext>} */
export function useLandingPageContext() {
  const ctx = inject(LANDING_PAGE_KEY)
  if (!ctx) {
    throw new Error('useLandingPageContext() вызван вне provideLandingPage()')
  }
  return ctx
}
