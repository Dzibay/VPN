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
import { sitePublicUrl, fetchJson } from '../api/client.js'
import { LEGAL_FOOTER_LINKS } from '../content/legal.js'
import { applyProjectLegalFromSiteLinks, getProjectLegalTokens } from './useProjectLegal.js'
import { trialDaysLabel } from '../content/legal/constants.js'
import { buildLandingPlans, useYookassaPricing } from './useYookassaPricing.js'
import { isHalyalBrand } from '../brand/brandAssets.js'

export const LANDING_PAGE_KEY = Symbol('landingPage')

const brandName = 'Halyal VPN'

const landingCopy = {
  brandName,
  heroBadge: 'Чистый • Быстрый • Надёжный',
  heroTitle: 'VPN для спокойного доступа к нужным сервисам',
  heroLead:
    'Halyal VPN помогает пользоваться зарубежными сервисами через защищённый канал, а привычные российские приложения оставляет работать напрямую.',
  heroCharityNote:
    '10% с каждого платежа мы направляем на поддержку благотворительных проектов',
  heroPrimaryCta: 'Перейти в кабинет',
  heroSecondaryCta: 'Посмотреть тарифы',
  heroSocialCount: 'Пользователи выбирают Halyal VPN за стабильность',
  whyTitle: 'Почему выбирают Halyal VPN?',
  howEyebrow: 'Умная маршрутизация',
  howTitlePrefix: 'Два маршрута в одном',
  howLead:
    'Halyal VPN автоматически разделяет трафик: зарубежные сервисы идут через защищённый туннель, а российские банки, госуслуги и локальные приложения — напрямую.',
  howVpnBadge: 'Туннель',
  howVpnTitle: 'Через VPN',
  howVpnDesc: 'Видео, соцсети, ИИ-сервисы и зарубежные сайты',
  howDirectBadge: 'Прямой IP',
  howDirectTitle: 'Напрямую (РФ)',
  howDirectDesc: 'Банки, госуслуги и локальные сервисы без лишних обходов',
  trialLead: 'Попробуйте Halyal VPN без ограничений и сложных настроек',
  trialProofStrong: 'Стабильность, скорость и понятное подключение',
  trialProofText: 'то, за что пользователи выбирают Halyal VPN каждый день',
  pricingLead:
    'Halyal VPN объединяет скорость, приватность и удобное подключение. Выберите подписку, которая подходит именно вам.',
  pricingBenefitsAria: 'Преимущества Halyal VPN',
  faqLead:
    'Коротко о том, как устроен Halyal VPN и чего ждать после регистрации. Если не нашли ответ — мы всегда на связи.',
  finalTitle: 'Подключите VPN один раз и пользуйтесь интернетом спокойно',
  finalLead:
    'Halyal VPN берёт маршрутизацию на себя: нужные зарубежные сервисы открываются через туннель, а локальные приложения продолжают работать привычно.',
  footerDesc:
    'VPN с умной маршрутизацией: зарубежные сервисы через защищённый канал, российские — без постоянного переключения.',
  footerCopyright: '© 2026 Halyal VPN. Все права защищены.',
  orgDescription:
    'VPN-сервис Halyal VPN: защищённый доступ к зарубежным сервисам и удобная работа с российскими приложениями без лишних переключений.',
}

export const heroTags = ['Чистый', 'Быстрый', 'Надёжный']

/** @type {const} */
export const HOME_IMAGES = {
  heroBg: '/images/halyal/hero-bg.png',
  bgMap: '/images/halyal/hero-bg.png',
  finalVisual: '/icons/halyal-logo.png',
  appMockup: '/images/halyal/hero-bg.png',
  trustAvatars: '/images/home/trust-avatars.png',
  logoWordmark: '/icons/halyal-logo.png',
  logoWordmarkDark: '/icons/halyal-logo.png',
}

export function createLandingPageContext() {
  const router = useRouter()
  const hasToken = ref(false)
  const sessionRole = ref(null)

  function refreshAuth() {
    hasToken.value = Boolean(getAccessToken())
    sessionRole.value = getSessionRole()
  }

  const isLoggedIn = computed(
    () => hasToken.value && sessionRole.value === 'user',
  )
  /** Всегда /cabinet — кнопки «Перейти в кабинет» на лендинге. */
  const loggedInHomeCtaPath = '/cabinet'

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
      text: `${brandName} сам определяет, какой трафик пустить в туннель, а какой — напрямую`,
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
    `Все функции ${brandName}`,
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
    { q: 'Нужно ли выключать ВПН для оплаты картой?', a: `Нет. ${brandName} настроен так, что банковские приложения (Сбер, Т-Банк и др.) и Госуслуги работают через ваше прямое соединение, минуя VPN-сервер.` },
    { q: 'Будет ли работать Gemini и ChatGPT?', a: 'Да, все популярные ИИ-сервисы, включая Google Gemini, включены в список умной маршрутизации и открываются без проблем.' },
    { q: `На каких устройствах работает ${brandName}?`, a: 'Windows, macOS, Android, iOS, Linux и даже Android TV. Подключайтесь через клиенты Happ, V2Ray и другие приложения с поддержкой современных протоколов, включая VLESS.' },
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
    const handle = getProjectLegalTokens().supportTelegram || getProjectLegalTokens().telegramBot
    return telegramUrlFromHandle(handle)
  })

  const supportTelegramLabel = computed(() => {
    const url = supportTelegramUrl.value
    const fallback = getProjectLegalTokens().supportTelegram || getProjectLegalTokens().telegramBot
    if (!url) return fallback
    const m = url.match(/t\.me\/([^/?#]+)/i)
    return m?.[1] ? `@${m[1]}` : fallback
  })

  const footerSeoLinks = [
    { to: '/vpn-dlya-youtube', label: 'VPN для YouTube' },
    { to: '/vpn-dlya-gemini', label: 'VPN для Gemini' },
    { to: '/vpn-dlya-telegram', label: 'VPN для Telegram' },
    { to: '/vpn-dlya-android', label: 'VPN для Android' },
    { to: '/vpn-dlya-iphone', label: 'VPN для iPhone' },
  ]

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
      applyProjectLegalFromSiteLinks(siteLinks.value?.legal)
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

  const trialTitle = computed(() => {
    void siteLinks.value
    const days = getProjectLegalTokens().trialDays
    return `${trialDaysLabel(days)} бесплатно`
  })

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
          name: brandName,
          ...(base ? { url: `${base}/` } : {}),
          description: landingCopy.orgDescription,
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
    brandName,
    isHalyalBrand,
    landingCopy,
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
    heroTags,
    heroMiniFeatures,
    whyChooseFeatures,
    howVpnApps,
    howDirectApps,
    howVpnPerks,
    howDirectPerks,
    howHighlights,
    trialFeatures,
    trialVisualOrbit,
    trialTitle,
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
    footerSeoLinks,
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
