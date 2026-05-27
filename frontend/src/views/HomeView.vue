<script setup>
/**
 * Картинки для первых двух секций — положите в frontend/public/images/home/:
 *   hero-bg-map.png      — точечная карта мира на фоне hero (опционально)
 *   hero-app-mockup.png  — макет приложения справа (обязательно для макета)
 *   trust-avatars.png    — 4 аватара для блока «10 000+ пользователей» (опционально)
 *   how/vpn/*.png        — иконки в секции «Умная маршрутизация» (см. public/images/home/how/README.txt)
 *   how/direct/*.png
 */
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
} from 'vue'
import { RouterLink, useRouter } from 'vue-router'
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
import AppActionButton from '../components/AppActionButton.vue'
import { getAccessToken, getSessionRole } from '../auth/session.js'
import { defaultPathAfterLogin } from '../auth/permissions.js'
import { sitePublicUrl, fetchJson } from '../api/client.js'
import { LEGAL_FOOTER_LINKS, SUPPORT_TELEGRAM } from '../content/legal.js'
import { buildLandingPlans, useYookassaPricing } from '../composables/useYookassaPricing.js'

/** @type {const} */
const HOME_IMAGES = {
  bgMap: '/images/home/hero-bg-map.png',
  appMockup: '/images/home/hero-app-mockup.png',
  trustAvatars: '/images/home/trust-avatars.png',
  logoWordmark: '/images/home/header-logo.png',
}

const footerHighlights = [
  {
    icon: Shield,
    title: 'Надёжность',
    text: 'Шифрование военного уровня и защита данных',
  },
  {
    icon: Zap,
    title: 'Скорость',
    text: 'Стабильное соединение без потери скорости',
  },
  {
    icon: Globe,
    title: 'Доступность',
    text: 'Сервисы и сайты доступны по всему миру',
  },
  {
    icon: MessageCircle,
    title: 'Поддержка',
    text: 'Мы рядом 24/7 и готовы помочь в любой момент',
  },
]

const footerPayBrands = [
  { src: '/images/pay-brands/visa.png', alt: 'Visa' },
  { src: '/images/pay-brands/mastercard.png', alt: 'Mastercard' },
  { src: '/images/pay-brands/mir.png', alt: 'Мир' },
]

const heroMiniFeatures = [
  {
    icon: Lock,
    title: 'Защита данных',
    text: 'Шифрование военного уровня',
  },
  {
    icon: Globe,
    title: 'Доступ без границ',
    text: 'Обход блокировок и ограничений',
  },
  {
    icon: Zap,
    title: 'Высокая скорость',
    text: 'Стабильное соединение без потери скорости',
  },
]

const whyChooseFeatures = [
  {
    icon: Shield,
    title: 'Надёжная защита',
    text: 'Шифрование AES-256 защищает ваши данные в любой сети.',
  },
  {
    icon: Globe,
    title: 'Доступ к любому контенту',
    text: 'Смотрите, слушайте и играйте без ограничений из любой точки мира.',
  },
  {
    icon: Zap,
    title: 'Стабильная скорость',
    text: 'Оптимизированные серверы обеспечивают высокую скорость соединения.',
  },
  {
    icon: Monitor,
    title: 'До 5 устройств',
    text: 'Используйте VPN на всех ваших устройствах одновременно.',
  },
  {
    icon: Headphones,
    title: 'Поддержка 24/7',
    text: 'Наша команда всегда готова помочь вам в любое время.',
  },
]

const router = useRouter()
const hasToken = ref(false)
const sessionRole = ref(null)

function refreshAuth() {
  hasToken.value = Boolean(getAccessToken())
  sessionRole.value = getSessionRole()
}

const isLoggedIn = computed(() => hasToken.value)

/** После входа: клиент → /cabinet, admin/manager → старт админки. */
const loggedInHomeCtaPath = computed(() =>
  defaultPathAfterLogin(sessionRole.value),
)

router.afterEach(refreshAuth)

/** Иконки приложений — положите PNG в public/images/home/how/ (см. README там). */
const HOW_APP_ICONS = {
  vpn: '/images/home/how/vpn',
  direct: '/images/home/how/direct',
}

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
  {
    icon: Zap,
    title: 'Без привязки банковской карты',
    text: 'Никаких скрытых платежей и обязательств',
  },
  {
    icon: ShieldCheck,
    title: 'Полный доступ ко всем функциям',
    text: 'Все серверы, все устройства, без ограничений',
  },
  {
    icon: Smartphone,
    title: 'До 5 устройств одновременно',
    text: 'Подключайте все ваши устройства',
  },
]

const trialVisualOrbit = [
  { icon: Globe, pos: 'tl' },
  { icon: Zap, pos: 'tr' },
  { icon: Lock, pos: 'bl' },
  { icon: Monitor, pos: 'br' },
]

/** Одни и те же возможности на любом сроке — меняется только цена. */
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
  {
    icon: Rocket,
    title: 'Молниеносная скорость',
    text: 'Без потери качества',
  },
  {
    icon: Lock,
    title: 'Без логов и слежки',
    text: 'Ваша приватность под защитой',
  },
  {
    icon: Globe,
    title: 'Проверенные локации',
    text: 'Стабильный доступ к нужным сервисам',
  },
  {
    icon: RefreshCw,
    title: 'Простое управление',
    text: 'Удобные приложения для всех платформ',
  },
]

/** Сроки на лендинге; цены и экономия — из yookassa_tariffs.json через API. */
const LANDING_PLAN_MONTHS = [1, 6, 12]

const LANDING_PLAN_META = {
  1: {
    displayName: 'Ежемесячная',
    periodBadge: '1 месяц',
    tagline: 'Идеально, чтобы попробовать сервис',
    ctaGuest: 'Оформить подписку',
  },
  6: {
    displayName: 'Полгода',
    periodBadge: '6 месяцев',
    tagline: 'Оптимальный баланс цены и срока',
    popular: true,
    ctaGuest: 'Подключить на полгода',
  },
  12: {
    displayName: 'Годовая',
    periodBadge: '12 месяцев',
    tagline: 'Максимальная выгода на длительный срок',
    ctaGuest: 'Подключить на год',
  },
}

const { loading: pricingLoading, tariffs, load: loadYookassaTariffs } =
  useYookassaPricing()

const plans = computed(() =>
  buildLandingPlans(tariffs.value, LANDING_PLAN_MONTHS, LANDING_PLAN_META),
)

const faqs = [
  {
    q: 'Нужно ли выключать ВПН для оплаты картой?',
    a:
      'Нет. Подорожник настроен так, что банковские приложения (Сбер, Т-Банк и др.) и Госуслуги работают через ваше прямое соединение, минуя VPN-сервер.',
  },
  {
    q: 'Будет ли работать Gemini и ChatGPT?',
    a:
      'Да, все популярные ИИ-сервисы, включая Google Gemini, включены в список умной маршрутизации и открываются без проблем.',
  },
  {
    q: 'На каких устройствах работает Подорожник VPN?',
    a:
      'Windows, macOS, Android, iOS, Linux и даже Android TV. Подключайтесь через клиенты с поддержкой VLESS — например V2Ray или Happ.',
  },
  {
    q: 'Сколько устройств можно подключить?',
    a:
      'По одной подписке вы можете подключить до 5 устройств одновременно без потери скорости.',
  },
]

const activeFaq = ref(null)

/** @type {import('vue').Ref<{ support_telegram_url?: string | null } | null>} */
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
  {
    icon: Zap,
    title: 'Быстрые ответы',
    text: 'Не тратьте время на поиск',
  },
  {
    icon: ShieldCheck,
    title: 'Проверенная информация',
    text: 'Только актуальные данные',
  },
  {
    icon: MessageCircle,
    title: 'Помощь 24/7',
    text: 'Мы всегда рядом',
  },
  {
    icon: Lock,
    title: 'Конфиденциальность',
    text: 'Ваши данные под защитой',
  },
]

const finalCtaFeatures = [
  {
    icon: Route,
    title: 'Умная маршрутизация',
    text: 'Зарубежное через VPN, своё — напрямую',
  },
  {
    icon: Shield,
    title: 'Фоновая защита',
    text: 'Работает незаметно и стабильно',
  },
  {
    icon: Lock,
    title: 'Без лишних действий',
    text: 'Никаких переключений и сложных настроек',
  },
]

const finalVisualPins = [
  { pos: 'tl' },
  { pos: 'tr' },
  { pos: 'bl' },
  { pos: 'br' },
]

function toggleFaq(index) {
  activeFaq.value = activeFaq.value === index ? null : index
}

/** JSON-LD FAQ для поисковых систем (Google понимает SPA при рендере). */
let faqLdEl = null

function injectHomeJsonLd() {
  const origin =
    typeof window !== 'undefined' ? window.location.origin : sitePublicUrl()
  const base = origin?.replace(/\/$/, '') || ''

  const structured = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'FAQPage',
        mainEntity: faqs.map((item) => ({
          '@type': 'Question',
          name: item.q,
          acceptedAnswer: {
            '@type': 'Answer',
            text: item.a,
          },
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
  script.setAttribute('data-home-faq-ld', '')
  script.textContent = JSON.stringify(structured)
  document.head.appendChild(script)
  faqLdEl = script
}

onMounted(() => {
  refreshAuth()
  void loadYookassaTariffs()
  void loadSiteLinks()
  injectHomeJsonLd()
})

onBeforeUnmount(() => {
  faqLdEl?.remove()
  faqLdEl = null
})
</script>

<template>
  <div class="home">
    <main id="main-content">
    <!-- HERO -->
    <section id="hero" class="hero hero--landing" aria-labelledby="hero-title">
      <div class="hero__bg" aria-hidden="true">
        <img
          class="hero__bg-map"
          :src="HOME_IMAGES.bgMap"
          alt=""
          width="1200"
          height="700"
          decoding="async"
          @error="($event.target).style.display = 'none'"
        />
      </div>

      <div class="hero__container">
        <div class="hero__content">
          <div class="hero__badge">
            <span class="hero__badge-dot" aria-hidden="true" />
            Быстрый • Безопасный • Надёжный
          </div>

          <h1 id="hero-title" class="hero__title">
            Безопасный интернет<br />
            без ограничений
          </h1>

          <p class="hero__lead">
            VPN-сервис для защиты вашей конфиденциальности, доступа к любым
            сайтам и сервисам по всему миру.
          </p>

          <ul class="hero__features" role="list">
            <li
              v-for="(item, i) in heroMiniFeatures"
              :key="i"
              class="hero__feature"
            >
              <span class="hero__feature-ico" aria-hidden="true">
                <component :is="item.icon" :size="22" :stroke-width="2" />
              </span>
              <span class="hero__feature-text">
                <strong>{{ item.title }}</strong>
                <span>{{ item.text }}</span>
              </span>
            </li>
          </ul>

          <div class="hero__cta">
            <template v-if="isLoggedIn">
              <AppActionButton
                variant="primary"
                large
                elevate-on-hover
                class="hero-cta-btn--trail"
                :to="loggedInHomeCtaPath"
              >
                Перейти в кабинет
                <template #icon>
                  <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
                </template>
              </AppActionButton>
            </template>
            <template v-else>
              <AppActionButton
                variant="primary"
                large
                elevate-on-hover
                class="hero-cta-btn--trail"
                to="/register"
              >
                Начать пользоваться VPN
                <template #icon>
                  <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
                </template>
              </AppActionButton>
              <a class="btn-secondary hero__cta-alt" href="#pricing">
                Выбрать тариф
              </a>
            </template>
          </div>

          <div class="hero__social">
            <div class="hero__social-avatars-wrap">
              <img
                class="hero__social-avatars"
                :src="HOME_IMAGES.trustAvatars"
                alt=""
                width="120"
                height="40"
                decoding="async"
                @error="($event.target).style.display = 'none'"
              />
              <div class="hero__social-fallback" aria-hidden="true">
                <span /><span /><span /><span />
              </div>
            </div>
            <div class="hero__social-copy">
              <p class="hero__social-count">10 000+ пользователей доверяют нам</p>
              <p class="hero__social-rating">
                <span class="hero__stars" aria-hidden="true">
                  <Star
                    v-for="n in 5"
                    :key="n"
                    :size="16"
                    :stroke-width="0"
                    fill="currentColor"
                  />
                </span>
                <span>4.9 из 5</span>
              </p>
            </div>
          </div>
        </div>

        <div class="hero__visual">
          <img
            class="hero__mockup"
            :src="HOME_IMAGES.appMockup"
            alt="Интерфейс VPN: подключение, выбор сервера и скорость"
            width="520"
            height="640"
            decoding="async"
          />
        </div>
      </div>
    </section>

    <!-- ПОЧЕМУ МЫ -->
    <section
      id="benefits"
      class="section section-why"
      aria-labelledby="why-heading"
    >
      <div class="section-inner section-why__inner">
        <h2 id="why-heading" class="section-why__title">
          Почему выбирают наш VPN?
        </h2>

        <div class="why-grid" role="list">
          <article
            v-for="(item, i) in whyChooseFeatures"
            :key="i"
            class="why-card"
            role="listitem"
          >
            <span class="why-card__ico" aria-hidden="true">
              <component :is="item.icon" :size="22" :stroke-width="2" />
            </span>
            <div class="why-card__body">
              <h3 class="why-card__title">{{ item.title }}</h3>
              <p class="why-card__text">{{ item.text }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- КАК РАБОТАЕТ -->
    <section
      id="how"
      class="section section-how"
      aria-labelledby="how-heading"
    >
      <div class="how-decor" aria-hidden="true">
        <svg class="how-decor__routes how-decor__routes--left" viewBox="0 0 320 280" fill="none">
          <path
            d="M24 48 C 80 20, 140 90, 120 150 S 60 220, 140 248"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="4 7"
            stroke-linecap="round"
          />
          <path
            d="M48 200 C 100 170, 180 210, 200 120"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="4 7"
            stroke-linecap="round"
            opacity="0.55"
          />
          <circle cx="120" cy="150" r="5" fill="currentColor" opacity="0.35" />
          <circle cx="200" cy="120" r="4" fill="currentColor" opacity="0.25" />
        </svg>
        <svg class="how-decor__routes how-decor__routes--right" viewBox="0 0 320 280" fill="none">
          <path
            d="M296 56 C 240 24, 170 88, 190 148 S 250 218, 170 246"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="4 7"
            stroke-linecap="round"
          />
          <path
            d="M272 204 C 220 176, 140 214, 120 126"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-dasharray="4 7"
            stroke-linecap="round"
            opacity="0.55"
          />
          <circle cx="190" cy="148" r="5" fill="currentColor" opacity="0.35" />
          <circle cx="120" cy="126" r="4" fill="currentColor" opacity="0.25" />
        </svg>
        <span class="how-decor__pin how-decor__pin--tl">
          <MapPin :size="14" stroke-width="2.2" />
        </span>
        <span class="how-decor__pin how-decor__pin--tr">
          <MapPin :size="14" stroke-width="2.2" />
        </span>
      </div>

      <div class="section-inner how-inner">
        <p class="how-eyebrow">
          <span class="how-eyebrow__dot" aria-hidden="true" />
          Умная маршрутизация
        </p>
        <h2 id="how-heading" class="how-title">
          Две дороги из одного <span class="how-title__accent">VPN</span>
        </h2>
        <p class="how-lead">
          Подорожник делит трафик автоматически: международные сервисы идут через
          зашифрованный канал (VLESS), а привычные российские приложения —
          по вашему обычному IP, без лишних задержек
        </p>

        <div class="how-stage">
          <article class="how-card how-card--vpn">
            <header class="how-card__head">
              <span class="how-card__badge how-card__badge--vpn">
                <Lock :size="12" stroke-width="2.5" aria-hidden="true" />
                Туннель
              </span>
              <h3 class="how-card__title">
                Через <span class="how-card__title-accent">VPN</span>
              </h3>
              <p class="how-card__desc">
                Стриминг, соцсети, ИИ и всё, что за рубежом
              </p>
            </header>

            <div class="how-card__body">
              <div class="how-card__viz how-card__viz--vpn" aria-hidden="true">
                <span class="how-card__ring how-card__ring--3" />
                <span class="how-card__ring how-card__ring--2" />
                <span class="how-card__ring how-card__ring--1" />
                <span class="how-card__hub how-card__hub--vpn">
                  <Globe :size="22" stroke-width="2" />
                </span>
                <span class="how-card__arrow how-card__arrow--vpn" />
              </div>
              <ul class="how-apps how-apps--vpn" role="list">
                <li
                  v-for="app in howVpnApps"
                  :key="app.id"
                  class="how-apps__item"
                >
                  <span class="how-apps__chip">
                    <img
                      class="how-apps__icon"
                      :src="app.icon"
                      alt=""
                      width="28"
                      height="28"
                      loading="lazy"
                      decoding="async"
                      @error="($event.target).classList.add('how-apps__icon--missing')"
                    />
                    <span class="how-apps__label">{{ app.label }}</span>
                  </span>
                </li>
              </ul>
            </div>

            <ul class="how-card__perks" role="list">
              <li
                v-for="(perk, i) in howVpnPerks"
                :key="i"
                class="how-card__perk"
              >
                <component
                  :is="perk.icon"
                  class="how-card__perk-ico"
                  :size="15"
                  stroke-width="2.2"
                  aria-hidden="true"
                />
                <span>{{ perk.text }}</span>
              </li>
            </ul>
          </article>

          <div class="how-split" aria-hidden="true">
            <span class="how-split__line" />
            <span class="how-split__badge">split</span>
            <span class="how-split__line" />
          </div>

          <article class="how-card how-card--direct">
            <header class="how-card__head">
              <span class="how-card__badge how-card__badge--direct">
                <Shield :size="12" stroke-width="2.5" aria-hidden="true" />
                Прямой IP
              </span>
              <h3 class="how-card__title">
                Напрямую <span class="how-card__title-accent">(РФ)</span>
              </h3>
              <p class="how-card__desc">
                Банки, госуслуги и локальные сервисы без обходов
              </p>
            </header>

            <div class="how-card__body">
              <div class="how-card__viz how-card__viz--direct" aria-hidden="true">
                <span class="how-card__ring how-card__ring--3" />
                <span class="how-card__ring how-card__ring--2" />
                <span class="how-card__ring how-card__ring--1" />
                <span class="how-card__hub how-card__hub--direct">
                  <MapPin :size="22" stroke-width="2" />
                </span>
                <span class="how-card__arrow how-card__arrow--direct" />
              </div>
              <ul class="how-apps how-apps--direct" role="list">
                <li
                  v-for="app in howDirectApps"
                  :key="app.id"
                  class="how-apps__item"
                >
                  <span class="how-apps__chip">
                    <img
                      class="how-apps__icon"
                      :src="app.icon"
                      alt=""
                      width="28"
                      height="28"
                      loading="lazy"
                      decoding="async"
                      @error="($event.target).classList.add('how-apps__icon--missing')"
                    />
                    <span class="how-apps__label">{{ app.label }}</span>
                  </span>
                </li>
              </ul>
            </div>

            <ul class="how-card__perks" role="list">
              <li
                v-for="(perk, i) in howDirectPerks"
                :key="i"
                class="how-card__perk"
              >
                <component
                  :is="perk.icon"
                  class="how-card__perk-ico"
                  :size="15"
                  stroke-width="2.2"
                  aria-hidden="true"
                />
                <span>{{ perk.text }}</span>
              </li>
            </ul>
          </article>
        </div>

        <div class="how-highlights">
          <article
            v-for="(item, i) in howHighlights"
            :key="i"
            class="how-highlight"
          >
            <component
              :is="item.icon"
              class="how-highlight__ico"
              :size="22"
              stroke-width="2"
              aria-hidden="true"
            />
            <div class="how-highlight__copy">
              <h3 class="how-highlight__title">{{ item.title }}</h3>
              <p class="how-highlight__text">{{ item.text }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- ПРОБНЫЙ ПЕРИОД -->
    <section
      id="trial"
      class="section section-trial"
      aria-labelledby="trial-title"
    >
      <div class="section-inner">
        <div class="trial-card">
          <div class="trial-card__main">
            <div class="trial-card__copy">
              <span class="trial-card__pill">
                <Gift
                  :size="14"
                  :stroke-width="2.2"
                  aria-hidden="true"
                />
                Пробный период
              </span>
              <h2 id="trial-title" class="trial-card__title">
                3 дня бесплатно
              </h2>
              <p class="trial-card__lead">
                Протестируйте все преимущества Подорожник VPN без ограничений
              </p>
              <ul
                class="trial-card__features"
                aria-label="Что входит в пробный период"
              >
                <li
                  v-for="(item, i) in trialFeatures"
                  :key="i"
                  class="trial-card__feature"
                >
                  <span class="trial-card__feature-ico" aria-hidden="true">
                    <component
                      :is="item.icon"
                      :size="18"
                      :stroke-width="2.2"
                    />
                  </span>
                  <span class="trial-card__feature-text">
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.text }}</span>
                  </span>
                </li>
              </ul>
            </div>

            <div class="trial-card__visual" aria-hidden="true">
              <div class="trial-visual">
                <span class="trial-visual__ring trial-visual__ring--1" />
                <span class="trial-visual__ring trial-visual__ring--2" />
                <span class="trial-visual__ring trial-visual__ring--3" />
                <span class="trial-visual__shield">
                  <ShieldCheck :size="42" :stroke-width="1.6" />
                </span>
                <span
                  v-for="(item, i) in trialVisualOrbit"
                  :key="i"
                  class="trial-visual__tile"
                  :class="`trial-visual__tile--${item.pos}`"
                >
                  <component
                    :is="item.icon"
                    :size="16"
                    :stroke-width="2"
                  />
                </span>
              </div>
            </div>

            <div class="trial-card__cta">
              <RouterLink
                v-if="isLoggedIn"
                class="cta primary large trial-card__cta-btn"
                :to="loggedInHomeCtaPath"
              >
                Перейти в кабинет
                <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
              </RouterLink>
              <RouterLink
                v-else
                class="cta primary large trial-card__cta-btn"
                to="/register"
              >
                Начать бесплатно
                <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
              </RouterLink>
              <p class="trial-card__hint">
                <CheckCircle2
                  :size="15"
                  :stroke-width="2.2"
                  aria-hidden="true"
                />
                Отмена в любой момент — никаких обязательств
              </p>
            </div>
          </div>

          <div class="trial-card__proof" aria-label="Отзывы пользователей">
            <div class="trial-card__proof-users">
              <span class="trial-card__proof-badge" aria-hidden="true">
                <Star :size="18" :stroke-width="2" fill="currentColor" />
              </span>
              <div class="trial-card__proof-copy">
                <strong>Более 10 000 пользователей</strong>
                <span>
                  уже оценили стабильность и скорость соединения Подорожник VPN
                </span>
              </div>
            </div>
            <div class="trial-card__proof-rating">
              <strong class="trial-card__proof-score">4.9 из 5</strong>
              <div class="trial-card__proof-stars" aria-hidden="true">
                <Star
                  v-for="n in 5"
                  :key="n"
                  :size="15"
                  :stroke-width="2"
                  fill="currentColor"
                />
              </div>
              <span class="trial-card__proof-reviews">на основе 2500+ отзывов</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ТАРИФЫ -->
    <section
      id="pricing"
      class="section section-pricing"
      aria-labelledby="pricing-plans-heading"
    >
      <div class="section-inner">
        <div class="pricing-head">
          <p class="pricing-head__eyebrow">
            <span class="pricing-head__eyebrow-dot" aria-hidden="true" />
            Подписка
          </p>
          <h2
            id="pricing-plans-heading"
            class="pricing-head__title"
          >
            Один <span class="pricing-head__accent">VPN</span> — максимум возможностей
          </h2>
          <p class="pricing-head__lead">
            Подорожник VPN объединяет скорость, безопасность и удобство.<br />
            Выберите подписку, которая подходит именно вам.
          </p>

          <div
            class="pricing-trust-bar"
            aria-label="Ключевые условия подписки"
          >
            <span
              v-for="(item, i) in pricingTrustTop"
              :key="i"
              class="pricing-trust-bar__item"
            >
              <component
                :is="item.icon"
                class="pricing-trust-bar__icon"
                :size="17"
                :stroke-width="2.2"
                aria-hidden="true"
              />
              {{ item.text }}
            </span>
          </div>
        </div>

        <p
          v-if="pricingLoading"
          class="pricing-status"
        >
          Загрузка тарифов…
        </p>
        <p
          v-else-if="plans.length === 0"
          class="pricing-status"
          role="status"
        >
          Тарифы временно недоступны. Обновите страницу или напишите в поддержку.
        </p>

        <div
          v-else
          class="pricing-grid"
          role="list"
          aria-labelledby="pricing-plans-heading"
        >
          <article
            v-for="plan in plans"
            :key="plan.id"
            class="pricing-card"
            :class="{ 'pricing-card--popular': plan.popular }"
            role="listitem"
          >
            <div
              v-if="plan.popular"
              class="pricing-card__ribbon"
            >
              {{ plan.ribbonLabel }}
            </div>

            <span class="pricing-card__period-badge">{{ plan.periodBadge }}</span>

            <div class="pricing-card__header">
              <h3 class="pricing-card__name">{{ plan.displayName }}</h3>
              <p class="pricing-card__tagline">{{ plan.tagline }}</p>
            </div>

            <div class="pricing-card__metrics">
              <div class="pricing-card__price-row">
                <span class="pricing-card__monthly-num">{{ plan.monthlyHighlight }}</span>
                <span class="pricing-card__monthly-unit">/ месяц</span>
              </div>

              <p
                v-if="plan.paymentHint"
                class="pricing-card__payment-hint"
              >
                {{ plan.paymentHint }}
              </p>

              <div
                v-else-if="plan.totalPeriodLabel"
                class="pricing-card__billing-row"
              >
                <span class="pricing-card__total-price">{{ plan.totalPeriodLabel }}</span>
                <span
                  v-if="plan.compareAtTotal"
                  class="pricing-card__compare"
                >{{ plan.compareAtTotal }}</span>
                <span
                  v-if="plan.discountPercent"
                  class="pricing-card__discount"
                >−{{ plan.discountPercent }}%</span>
              </div>

              <p
                v-if="plan.savingsLabel"
                class="pricing-card__save"
              >
                {{ plan.savingsLabel }}
              </p>
            </div>

            <hr class="pricing-card__divider" aria-hidden="true">

            <ul
              class="pricing-card__features"
              aria-label="Что входит"
            >
              <li
                v-for="(line, idx) in planIncludes"
                :key="idx"
              >
                <CheckCircle2
                  class="pricing-card__check"
                  :size="16"
                  :stroke-width="2.2"
                  aria-hidden="true"
                />
                {{ line }}
              </li>
            </ul>

            <div class="pricing-card__cta">
              <RouterLink
                v-if="isLoggedIn"
                class="cta secondary pricing-card__btn"
                :to="loggedInHomeCtaPath"
              >
                Перейти в кабинет
              </RouterLink>
              <RouterLink
                v-else
                class="cta pricing-card__btn"
                :class="plan.popular ? 'primary' : 'cta--outline'"
                to="/register"
              >
                {{ plan.ctaGuest }}
              </RouterLink>
            </div>
          </article>
        </div>

        <div
          class="pricing-benefits"
          aria-label="Преимущества Подорожник VPN"
        >
          <article
            v-for="(item, i) in pricingBenefitsBottom"
            :key="i"
            class="pricing-benefits__item"
          >
            <span class="pricing-benefits__icon" aria-hidden="true">
              <component
                :is="item.icon"
                :size="20"
                :stroke-width="2.2"
              />
            </span>
            <span class="pricing-benefits__copy">
              <strong>{{ item.title }}</strong>
              <span>{{ item.text }}</span>
            </span>
          </article>
        </div>

        <p class="pricing-footnote">
          <ShieldCheck
            class="pricing-footnote__icon"
            :size="17"
            :stroke-width="2.2"
            aria-hidden="true"
          />
          Попробуйте бесплатно в течение 3 дней после
          <RouterLink class="pricing-footnote__link" to="/register">регистрации</RouterLink>
        </p>
      </div>
    </section>

    <!-- FAQ -->
    <section
      id="faq"
      class="section section-faq"
      aria-labelledby="faq-heading"
    >
      <div class="section-inner">
        <div class="faq-head">
          <p class="faq-head__eyebrow">
            <Headphones
              :size="14"
              :stroke-width="2.2"
              aria-hidden="true"
            />
            Поддержка
          </p>
          <h2 id="faq-heading" class="faq-head__title">
            Частые вопросы
          </h2>
          <p class="faq-head__lead">
            Коротко о том, как устроен Подорожник VPN и чего ждать после регистрации.
            Если не нашли ответ — мы всегда на связи.
          </p>

          <div
            class="faq-trust-row"
            aria-label="Почему можно доверять ответам"
          >
            <article
              v-for="(item, i) in faqTrustHighlights"
              :key="i"
              class="faq-trust-row__item"
            >
              <span class="faq-trust-row__icon" aria-hidden="true">
                <component
                  :is="item.icon"
                  :size="18"
                  :stroke-width="2.2"
                />
              </span>
              <span class="faq-trust-row__copy">
                <strong>{{ item.title }}</strong>
                <span>{{ item.text }}</span>
              </span>
            </article>
          </div>
        </div>

        <div
          class="faq-shell"
          role="region"
          aria-label="Ответы на частые вопросы"
        >
          <div class="faq-accordion">
            <div
              v-for="(faq, i) in faqs"
              :key="i"
              class="faq-item"
              :class="{ 'is-open': activeFaq === i }"
            >
              <h3 class="faq-item__heading">
                <button
                  type="button"
                  class="faq-question"
                  :aria-expanded="activeFaq === i"
                  :aria-controls="`faq-panel-${i}`"
                  :id="`faq-trigger-${i}`"
                  @click="toggleFaq(i)"
                >
                  <span class="faq-question__mark" aria-hidden="true">
                    <HelpCircle :size="18" :stroke-width="2.2" />
                  </span>
                  <span class="faq-question__text">{{ faq.q }}</span>
                  <span
                    class="faq-icon"
                    aria-hidden="true"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      width="20"
                      height="20"
                      stroke="currentColor"
                      stroke-width="2"
                      fill="none"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </span>
                </button>
              </h3>
              <div
                :id="`faq-panel-${i}`"
                class="faq-answer-wrapper"
                role="region"
                :aria-labelledby="`faq-trigger-${i}`"
              >
                <div
                  class="faq-answer"
                  :aria-hidden="activeFaq !== i"
                >
                  {{ faq.a }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div id="faq-support" class="faq-support">
          <div class="faq-support__copy">
            <span class="faq-support__icon" aria-hidden="true">
              <Headphones :size="22" :stroke-width="2.2" />
            </span>
            <span class="faq-support__text">
              <strong>Не нашли ответ?</strong>
              <span>Напишите нам — мы поможем разобраться</span>
            </span>
          </div>
          <a
            class="cta primary large faq-support__btn"
            :href="supportTelegramUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            Связаться с поддержкой
            <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>

    <!-- ФИНАЛЬНЫЙ CTA -->
    <section
      class="section section-final"
      aria-labelledby="final-cta-heading"
    >
      <div class="section-inner">
        <div class="final-cta-card">
          <div class="final-cta-card__main">
            <span class="final-cta-card__pill">
              <ShieldCheck
                :size="14"
                :stroke-width="2.2"
                aria-hidden="true"
              />
              Следующий шаг
            </span>
            <h2
              id="final-cta-heading"
              class="final-cta-card__title"
            >
              Забудьте про постоянное включение и выключение
              <span class="final-cta-card__accent">VPN</span>
            </h2>
            <p class="final-cta-card__lead">
              Один раз настроили маршруты — дальше интернет ведёт себя предсказуемо:
              зарубежные сервисы через туннель, российские приложения без лишних обходов.
            </p>
            <ul
              class="final-cta-card__features"
              aria-label="Преимущества после настройки"
            >
              <li
                v-for="(item, i) in finalCtaFeatures"
                :key="i"
                class="final-cta-card__feature"
              >
                <span class="final-cta-card__feature-ico" aria-hidden="true">
                  <component
                    :is="item.icon"
                    :size="18"
                    :stroke-width="2.2"
                  />
                </span>
                <span class="final-cta-card__feature-text">
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.text }}</span>
                </span>
              </li>
            </ul>
          </div>

          <div class="final-cta-card__aside">
            <div class="final-visual" aria-hidden="true">
              <img
                class="final-visual__map"
                :src="HOME_IMAGES.bgMap"
                alt=""
                width="480"
                height="280"
                decoding="async"
                @error="($event.target).style.display = 'none'"
              />
              <span class="final-visual__ring final-visual__ring--1" />
              <span class="final-visual__ring final-visual__ring--2" />
              <span class="final-visual__shield">
                <ShieldCheck :size="40" :stroke-width="1.6" />
              </span>
              <span
                v-for="(pin, i) in finalVisualPins"
                :key="i"
                class="final-visual__pin"
                :class="`final-visual__pin--${pin.pos}`"
              >
                <MapPin :size="16" :stroke-width="2.2" fill="currentColor" />
              </span>
            </div>

            <RouterLink
              v-if="isLoggedIn"
              class="cta primary large final-cta-card__btn"
              :to="loggedInHomeCtaPath"
            >
              Открыть кабинет
              <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
            </RouterLink>
            <RouterLink
              v-else
              class="cta primary large final-cta-card__btn"
              to="/register"
            >
              Создать аккаунт
              <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
            </RouterLink>
          </div>
        </div>
      </div>
    </section>

    </main>

    <!-- FOOTER -->
    <footer
      class="footer"
      role="contentinfo"
    >
      <div class="footer-shell">
        <div class="footer-top">
          <div class="footer-brand">
            <img
              class="footer-brand__logo"
              :src="HOME_IMAGES.logoWordmark"
              width="220"
              height="48"
              alt="Подорожник VPN"
              decoding="async"
            />
            <p class="footer-brand__desc">
              Умный VPN на VLESS с split tunneling: зарубежное — через туннель,
              российское — напрямую.
            </p>
            <div class="footer-social" aria-label="Связаться с нами">
              <a
                class="footer-social__btn"
                :href="supportTelegramUrl"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Telegram поддержки"
              >
                <Send :size="17" :stroke-width="2.2" aria-hidden="true" />
              </a>
              <a
                class="footer-social__btn"
                href="#faq"
                aria-label="Раздел поддержки"
              >
                <MessageCircle :size="17" :stroke-width="2.2" aria-hidden="true" />
              </a>
            </div>
          </div>

          <nav
            class="footer-col"
            aria-label="Продукт"
          >
            <h3 class="footer-col__title">
              <span class="footer-col__dot" aria-hidden="true" />
              Продукт
            </h3>
            <ul class="footer-col__list">
              <li
                v-for="(link, i) in footerProductLinks"
                :key="`${link.href}-${i}`"
              >
                <a
                  :href="link.href"
                  :target="link.external ? '_blank' : undefined"
                  :rel="link.external ? 'noopener noreferrer' : undefined"
                >{{ link.label }}</a>
              </li>
            </ul>
          </nav>

          <nav
            class="footer-col"
            aria-label="Документы"
          >
            <h3 class="footer-col__title">
              <span class="footer-col__dot" aria-hidden="true" />
              Документы
            </h3>
            <ul class="footer-col__list">
              <li
                v-for="link in LEGAL_FOOTER_LINKS"
                :key="link.to"
              >
                <RouterLink :to="link.to">{{ link.label }}</RouterLink>
              </li>
            </ul>
          </nav>

          <div class="footer-col footer-col--contacts">
            <h3 class="footer-col__title">
              <span class="footer-col__dot" aria-hidden="true" />
              Контакты
            </h3>
            <ul class="footer-col__contacts">
              <li>
                <Send
                  class="footer-col__contact-ico"
                  :size="16"
                  :stroke-width="2.2"
                  aria-hidden="true"
                />
                <a
                  class="footer-col__contact-link"
                  :href="supportTelegramUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ supportTelegramLabel }}
                </a>
              </li>
              <li>
                <Clock
                  class="footer-col__contact-ico"
                  :size="16"
                  :stroke-width="2.2"
                  aria-hidden="true"
                />
                <span>Поддержка 24/7</span>
              </li>
            </ul>
          </div>
        </div>

        <div
          class="footer-highlights"
          aria-label="Ключевые преимущества сервиса"
        >
          <article
            v-for="(item, i) in footerHighlights"
            :key="i"
            class="footer-highlights__item"
          >
            <span class="footer-highlights__icon" aria-hidden="true">
              <component
                :is="item.icon"
                :size="18"
                :stroke-width="2.2"
              />
            </span>
            <span class="footer-highlights__copy">
              <strong>{{ item.title }}</strong>
              <span>{{ item.text }}</span>
            </span>
          </article>
        </div>

        <div class="footer-bottom">
          <p class="footer-bottom__note">
            <ShieldCheck
              class="footer-bottom__ico"
              :size="15"
              :stroke-width="2.2"
              aria-hidden="true"
            />
            © 2026 Подорожник VPN. Все права защищены.
          </p>
          <p class="footer-bottom__note footer-bottom__note--center">
            <Lock
              class="footer-bottom__ico"
              :size="15"
              :stroke-width="2.2"
              aria-hidden="true"
            />
            Ваши данные под защитой. Мы не храним логи и не передаём вашу информацию третьим лицам.
          </p>
          <div
            class="footer-payments"
            aria-label="Способы оплаты"
          >
            <img
              v-for="brand in footerPayBrands"
              :key="brand.alt"
              class="footer-payments__logo"
              :src="brand.src"
              :alt="brand.alt"
              width="44"
              height="28"
              decoding="async"
            />
          </div>
        </div>
      </div>
    </footer>

  </div>
</template>

<style scoped>
.home {
  --landing-content-max: 84rem;
  flex: 1;
  color: var(--landing-muted);
  display: flex;
  flex-direction: column;

  /* Тёмная тема — по умолчанию, в духе :root */
  --landing-bg: #020203;
  --landing-bg-alt: #060908;
  --landing-surface: #0c100e;
  --landing-card: #0c100e;
  --landing-text: #e8f4ec;
  --landing-muted: #a8b8b0;
  --landing-border: #1a2420;
  --landing-border-subtle: #1a2420;
  --landing-accent: #58d68d;
  --landing-accent-hover: #6fe9a0;
  --landing-accent-soft: rgba(88, 214, 141, 0.16);
  --landing-accent-muted: rgba(88, 214, 141, 0.2);
  --landing-accent-glow: rgba(88, 214, 141, 0.45);
  --landing-on-accent: #000000;
  --landing-blue: #7eb8f0;
  --landing-blue-soft: rgba(126, 184, 240, 0.14);
  --landing-decor: #2a3832;
  --landing-subtle-bg: #0d1411;
  --landing-highlight-bg: #0f1814;
  --landing-shadow: rgba(0, 0, 0, 0.4);
  --landing-shadow-soft: rgba(0, 0, 0, 0.28);
  --landing-pin-surface: rgba(12, 16, 14, 0.92);
  --landing-avatar-border: #0c100e;
  --landing-star: #fbbf24;
  --landing-section-muted-bg: #060908;

  --home-bg: var(--landing-bg);
  --home-text: var(--landing-text);
  --home-muted: var(--landing-muted);
  --home-border: var(--landing-border);
  --home-accent: var(--landing-accent);
  --home-accent-hover: var(--landing-accent-hover);
  --home-accent-soft: var(--landing-accent-soft);
  --home-on-accent: var(--landing-on-accent);
}

@media (prefers-color-scheme: light) {
  .home {
    --landing-bg: #fafcfb;
    --landing-bg-alt: #f3f4f6;
    --landing-surface: #ffffff;
    --landing-card: #ffffff;
    --landing-text: #111827;
    --landing-muted: #6b7280;
    --landing-border: #e5e7eb;
    --landing-border-subtle: #e8ece9;
    --landing-accent: #1d9a5c;
    --landing-accent-hover: #18804d;
    --landing-accent-soft: rgba(29, 154, 92, 0.1);
    --landing-accent-muted: color-mix(in srgb, var(--landing-accent) 20%, transparent);
    --landing-accent-glow: rgba(29, 154, 92, 0.45);
    --landing-on-accent: #ffffff;
    --landing-blue: #4a90e2;
    --landing-blue-soft: rgba(74, 144, 226, 0.1);
    --landing-decor: #d1d9d4;
    --landing-subtle-bg: #f3f4f6;
    --landing-highlight-bg: #f4f7f5;
    --landing-shadow: var(--landing-shadow);
    --landing-shadow-soft: var(--landing-shadow-soft);
    --landing-pin-surface: rgba(255, 255, 255, 0.92);
    --landing-avatar-border: #ffffff;
    --landing-star: #f59e0b;
    --landing-section-muted-bg: #f9fafb;
  }
}

.home :is(section[id]) {
  scroll-margin-top: 4.5rem;
}

.section {
  padding: clamp(3.25rem, 7vw, 5.5rem) 1.25rem;
}

.section-inner {
  max-width: min(var(--landing-content-max, 84rem), 100%);
  margin: 0 auto;
  text-align: center;
}

.cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  text-decoration: none;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
  text-align: center;
}

.cta.large {
  padding: 1rem 2rem;
  font-size: 1.05rem;
  border-radius: 14px;
}

.cta.primary {
  color: var(--on-accent);
  background: var(--accent);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 40%, transparent);
  border: none;
}

.cta.primary:hover {
  background: var(--accent-hover);
  transform: translateY(-2px);
  box-shadow: 0 8px 22px color-mix(in srgb, var(--accent) 45%, transparent);
}

.cta.secondary {
  color: var(--text-h);
  background: color-mix(in srgb, var(--surface-glass) 92%, transparent);
  border: 1px solid var(--card-border);
  backdrop-filter: blur(10px);
}

.cta.secondary:hover {
  border-color: var(--accent-border);
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--surface-glass));
}

.cta--outline {
  background: transparent;
  color: var(--accent);
  border: 2px solid var(--accent-border);
  box-shadow: none;
}

.cta--outline:hover {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  transform: translateY(-2px);
}

/* ——— HERO (макет лендинга, светлая секция) ——— */
.hero--landing {
  --hero-content-max: var(--landing-content-max, 84rem);

  position: relative;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  padding: clamp(1.25rem, 3vh, 2rem) clamp(1rem, 4vw, 2rem) clamp(1rem, 2vh, 1.5rem);
  background: var(--landing-bg);
  color: var(--home-text);
  overflow: hidden;
}

.hero__bg {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 0;
}

.hero__bg-map {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: min(72%, 52rem);
  height: auto;
  max-height: 100%;
  object-fit: contain;
  object-position: right center;
  opacity: 0.48;
}

@media (max-width: 1023px) {
  .hero--landing {
    display: block;
    min-height: auto;
    padding-top: clamp(1rem, 3vw, 1.5rem);
    padding-bottom: clamp(1.5rem, 5vw, 2.25rem);
  }

  .hero__bg {
    inset: 0;
  }

  /* карта — фон всей секции под текстом */
  .hero__bg-map {
    inset: 0;
    left: 0;
    right: 0;
    top: 0;
    bottom: 0;
    width: 100%;
    height: 100%;
    max-width: none;
    max-height: none;
    transform: none;
    object-fit: cover;
    object-position: center center;
    opacity: 0.38;
  }

  .hero__container {
    position: relative;
    z-index: 1;
    flex: none;
    gap: 0;
  }

  .hero__content {
    position: relative;
    z-index: 2;
  }
}

.hero__container {
  position: relative;
  z-index: 1;
  flex: 1;
  width: 100%;
  max-width: min(var(--hero-content-max, 84rem), 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: 2.5rem;
  align-items: center;
}

@media (min-width: 1024px) {
  .hero__container {
    padding-inline: clamp(1rem, 2.5vw, 1.75rem);
    grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
    gap: clamp(1.25rem, 2vw, 2rem);
    align-items: stretch;
  }

  .hero__content {
    align-self: center;
  }

  /* карта за правой колонкой; на средних экранах — выше нижний порог */
  .hero__bg-map {
    right: max(0px, calc((100vw - min(var(--hero-content-max), 100%)) / 2 - 1rem));
    width: max(42rem, min(52vw, 54rem));
    max-height: max(38rem, min(62dvh, 54rem));
    opacity: 0.46;
  }
}

@media (min-width: 1240px) {
  .hero__bg-map {
    width: max(56rem, min(54vw, 56rem));
    max-height: max(40rem, min(65dvh, 56rem));
  }
}



.hero__content {
  position: relative;
  z-index: 2;
  min-width: 0;
  text-align: left;
}

@media (max-width: 1023px) {
  .hero__content {
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .hero__container {
    gap: 0;
  }
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin-bottom: 1.25rem;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--home-accent);
  background: var(--home-accent-soft);
  border: 1px solid var(--landing-accent-muted);
}

.hero__badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--home-accent);
  box-shadow: 0 0 0 0 var(--landing-accent-glow);
  animation: hero-badge-pulse 2s infinite;
}

@keyframes hero-badge-pulse {
  0% {
    box-shadow: 0 0 0 0 var(--landing-accent-glow);
  }
  70% {
    box-shadow: 0 0 0 6px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}

.hero__title {
  margin: 0 0 0.85rem;
  font-family: var(--heading);
  font-size: clamp(1.85rem, 3.4vw, 2.85rem);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.035em;
  color: var(--home-text);
}

.hero__lead {
  margin: 0 0 1.15rem;
  max-width: 32rem;
  font-size: clamp(0.9rem, 1.6vw, 1rem);
  line-height: 1.55;
  color: var(--home-muted);
}

.hero__features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.55rem;
  margin: 0 0 1.25rem;
  padding: 0;
  list-style: none;
  width: 100%;
  max-width: 36rem;
}

@media (max-width: 720px) {
  .hero__features {
    grid-template-columns: 1fr;
    max-width: 20rem;
  }
}

.hero__feature {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.65rem 0.55rem;
  border: 1px solid var(--home-border);
  border-radius: 12px;
  background: var(--landing-surface);
  text-align: left;
}

.hero__feature-ico {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--home-accent);
}

.hero__feature-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--home-muted);
}

.hero__feature-text strong {
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--home-text);
}

.hero__cta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 1.35rem;
}

@media (max-width: 1023px) {
  .hero__cta {
    justify-content: center;
  }
}

.hero-cta-btn--trail {
  flex-direction: row-reverse;
}

.hero__cta-alt {
  padding: 0.85rem 1.35rem;
  min-height: 3rem;
  font-size: 0.95rem;
  border-radius: 12px;
  background: var(--landing-surface);
  border-color: var(--home-border);
  color: var(--home-text);
}

.hero__cta-alt:hover {
  border-color: var(--landing-accent-muted);
  color: var(--home-accent);
  background: var(--landing-surface);
}

.hero__social {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}

@media (max-width: 1023px) {
  .hero__social {
    justify-content: center;
  }
}

.hero__social-avatars-wrap {
  position: relative;
  flex-shrink: 0;
  width: 7.25rem;
  height: 2.5rem;
}

.hero__social-avatars {
  position: relative;
  z-index: 1;
  display: block;
  height: 2.5rem;
  width: auto;
  max-width: 100%;
  object-fit: contain;
}

.hero__social-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
}

.hero__social-fallback span {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  border: 2px solid var(--landing-avatar-border);
  margin-left: -0.55rem;
  background: linear-gradient(135deg, #4b5563, #6b7280);
}

@media (prefers-color-scheme: light) {
  .hero__social-fallback span {
    background: linear-gradient(135deg, #d1d5db, #9ca3af);
  }
}

.hero__social-fallback span:first-child {
  margin-left: 0;
}

.hero__social-copy {
  text-align: left;
}

@media (max-width: 1023px) {
  .hero__social-copy {
    text-align: center;
  }
}

.hero__social-count {
  margin: 0 0 0.2rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--home-text);
}

.hero__social-rating {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--home-muted);
}

.hero__stars {
  display: inline-flex;
  gap: 0.05rem;
  color: var(--landing-star);
}

.hero__visual {
  display: none;
  min-width: 0;
}

@media (min-width: 1024px) {
  .hero__visual {
    display: flex;
    justify-content: center;
    align-items: center;
    align-self: stretch;
    width: 100%;
    min-width: 0;
    min-height: 0;
    margin: 0;
  }
}

.hero__mockup {
  display: block;
  width: auto;
  height: auto;
  max-width: min(100%, 26rem);
  max-height: min(70vh, 26rem);
  object-fit: contain;
  object-position: center center;
  filter: drop-shadow(0 14px 32px var(--landing-shadow));
}

@media (min-width: 1024px) {
  .hero__mockup {
    max-width: min(100%, 24rem);
    max-height: min(100%, 24rem);
  }
}

@media (min-width: 1280px) {
  .hero__mockup {
    max-width: min(100%, 26rem);
    max-height: min(100%, 26rem);
  }
}

/* ——— ПОЧЕМУ ВЫБИРАЮТ ——— */
.section.section-why {
  padding: clamp(3.25rem, 7vw, 5.5rem) clamp(1.25rem, 4vw, 2rem);
  background: var(--home-bg);
  border-top: none;
}

@media (min-width: 1024px) {
  .hero--landing {
    padding-top: clamp(2rem, 5vh, 3rem);
    padding-bottom: clamp(2rem, 4vh, 3rem);
  }
}

.section-why__inner {
  text-align: center;
}

.section-why__title {
  margin: 0 0 clamp(1.5rem, 3vw, 2rem);
  font-family: var(--heading);
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--home-text);
}

.why-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
  text-align: left;
}

@media (max-width: 1100px) {
  .why-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .why-grid {
    grid-template-columns: 1fr;
  }
}

.why-card {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding: 1rem 0.85rem;
  border: 1px solid var(--home-border);
  border-radius: 14px;
  background: var(--landing-surface);
  box-shadow: 0 1px 3px var(--landing-shadow-soft);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.why-card:hover {
  border-color: var(--landing-accent-muted);
  box-shadow: 0 6px 18px var(--landing-shadow);
}

.why-card__ico {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 10px;
  color: var(--home-accent);
  background: var(--home-accent-soft);
}

.why-card__body {
  min-width: 0;
}

.why-card__title {
  margin: 0 0 0.3rem;
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.25;
  color: var(--home-text);
}

.why-card__text {
  margin: 0;
  font-size: 0.72rem;
  line-height: 1.45;
  color: var(--home-muted);
}

/* ——— КАК РАБОТАЕТ ——— */
.section.section-how {
  --how-green: var(--landing-accent);
  --how-green-soft: var(--landing-accent-soft);
  --how-blue: var(--landing-blue);
  --how-blue-soft: var(--landing-blue-soft);
  --how-text: var(--landing-text);
  --how-muted: var(--landing-muted);
  --how-border: var(--landing-border-subtle);
  --how-decor: var(--landing-decor);

  position: relative;
  overflow: hidden;
  background: var(--landing-surface);
  border-block: 1px solid var(--landing-border);
}

.how-decor {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 0;
}

.how-decor__routes {
  position: absolute;
  width: clamp(12rem, 22vw, 18rem);
  height: auto;
  color: var(--how-decor);
  opacity: 0.85;
}

.how-decor__routes--left {
  top: 6%;
  left: -2%;
}

.how-decor__routes--right {
  top: 4%;
  right: -2%;
}

.how-decor__pin {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.65rem;
  height: 1.65rem;
  border-radius: 50%;
  color: var(--how-green);
  background: var(--landing-pin-surface);
  box-shadow: 0 1px 4px var(--landing-shadow-soft);
}

.how-decor__pin--tl {
  top: 18%;
  left: 14%;
}

.how-decor__pin--tr {
  top: 14%;
  right: 12%;
}

@media (max-width: 720px) {
  .how-decor__routes--right,
  .how-decor__pin {
    display: none;
  }

  .how-decor__routes--left {
    opacity: 0.5;
    width: 9rem;
  }
}

.how-inner {
  position: relative;
  z-index: 1;
}

.how-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 0 0.85rem;
  padding: 0.35rem 0.85rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--how-green);
  background: var(--how-green-soft);
  border-radius: var(--radius-pill);
}

.how-eyebrow__dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: var(--how-green);
}

.how-title {
  font-family: var(--heading);
  margin: 0 0 1rem;
  font-size: clamp(1.85rem, 4.2vw, 2.65rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.12;
  color: var(--how-text);
}

.how-title__accent {
  color: var(--how-green);
}

.how-lead {
  max-width: 42rem;
  margin: 0 auto 2.25rem;
  font-size: 1.05rem;
  line-height: 1.65;
  color: var(--how-muted);
}

.how-stage {
  display: grid;
  gap: 1rem;
  align-items: stretch;
  text-align: left;
}

.how-card--vpn {
  grid-area: vpn;
}

.how-split {
  grid-area: split;
}

.how-card--direct {
  grid-area: direct;
}

@media (min-width: 960px) {
  .how-stage {
    grid-template-columns: minmax(0, 1fr) 2.75rem minmax(0, 1fr);
    grid-template-areas: 'vpn split direct';
    gap: 0;
    align-items: stretch;
  }

  .how-card--vpn {
    border-top-right-radius: 12px;
    border-bottom-right-radius: 12px;
  }

  .how-card--direct {
    border-top-left-radius: 12px;
    border-bottom-left-radius: 12px;
  }
}

@media (max-width: 959px) {
  .how-stage {
    grid-template-areas:
      'vpn'
      'split'
      'direct';
  }
}

.how-card {
  display: flex;
  flex-direction: column;
  padding: clamp(1.25rem, 2.5vw, 1.65rem);
  border-radius: 20px;
  background: var(--landing-surface);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 12px 32px var(--landing-shadow);
}

.how-card--vpn {
  border: 1px solid color-mix(in srgb, var(--how-blue) 35%, var(--how-border));
}

.how-card--direct {
  border: 1px solid color-mix(in srgb, var(--how-green) 35%, var(--how-border));
}

.how-card__head {
  margin-bottom: 1.1rem;
}

.how-card__badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.6rem;
  padding: 0.28rem 0.7rem;
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  border-radius: var(--radius-pill);
}

.how-card__badge--vpn {
  color: var(--how-blue);
  background: var(--how-blue-soft);
  border: 1px solid color-mix(in srgb, var(--how-blue) 28%, transparent);
}

.how-card__badge--direct {
  color: var(--how-green);
  background: var(--how-green-soft);
  border: 1px solid color-mix(in srgb, var(--how-green) 28%, transparent);
}

.how-card__title {
  margin: 0 0 0.3rem;
  font-family: var(--heading);
  font-size: clamp(1.15rem, 2vw, 1.35rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--how-text);
}

.how-card__title-accent {
  color: var(--how-green);
}

.how-card__desc {
  margin: 0;
  font-size: 0.88rem;
  line-height: 1.5;
  color: var(--how-muted);
}

.how-card__body {
  display: flex;
  align-items: center;
  gap: clamp(0.75rem, 2vw, 1.25rem);
  margin-bottom: 1.15rem;
  min-height: 7.5rem;
}

.how-card__viz {
  position: relative;
  flex-shrink: 0;
  width: 5.5rem;
  height: 5.5rem;
}

.how-card__ring {
  position: absolute;
  inset: 0;
  margin: auto;
  border-radius: 50%;
  border: 1px solid var(--landing-border-subtle);
}

.how-card__ring--1 {
  width: 3.25rem;
  height: 3.25rem;
}

.how-card__ring--2 {
  width: 4.35rem;
  height: 4.35rem;
  opacity: 0.75;
}

.how-card__ring--3 {
  width: 5.5rem;
  height: 5.5rem;
  opacity: 0.45;
}

.how-card__hub {
  position: absolute;
  inset: 0;
  margin: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.65rem;
  height: 2.65rem;
  border-radius: 50%;
  z-index: 1;
}

.how-card__hub--vpn {
  color: var(--how-green);
  background: var(--how-green-soft);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--landing-accent) 6%, transparent);
}

.how-card__hub--direct {
  color: var(--how-green);
  background: var(--how-green-soft);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--landing-accent) 6%, transparent);
}

.how-card__arrow {
  position: absolute;
  top: 50%;
  right: -0.35rem;
  width: 2.25rem;
  height: 1px;
  transform: translateY(-50%);
}

.how-card__arrow--vpn {
  background: linear-gradient(90deg, color-mix(in srgb, var(--how-blue) 55%, transparent), transparent);
}

.how-card__arrow--vpn::after {
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  width: 0.35rem;
  height: 0.35rem;
  border-top: 1.5px solid var(--how-blue);
  border-right: 1.5px solid var(--how-blue);
  transform: translateY(-50%) rotate(45deg);
  opacity: 0.65;
}

.how-card__arrow--direct {
  background: linear-gradient(90deg, color-mix(in srgb, var(--how-green) 55%, transparent), transparent);
}

.how-card__arrow--direct::after {
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  width: 0.35rem;
  height: 0.35rem;
  border-top: 1.5px solid var(--how-green);
  border-right: 1.5px solid var(--how-green);
  transform: translateY(-50%) rotate(45deg);
  opacity: 0.65;
}

.how-apps {
  list-style: none;
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem;
  padding: 0;
  margin: 0;
}

@media (min-width: 520px) {
  .how-apps--vpn {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.how-apps--direct {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (min-width: 1100px) {
  .how-apps--direct {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.how-apps__item {
  min-width: 0;
}

.how-apps__chip {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  min-height: 2.35rem;
  padding: 0.35rem 0.5rem;
  border-radius: 10px;
  border: 1px solid var(--how-border);
  background: var(--landing-surface);
  box-shadow: 0 1px 2px var(--landing-shadow-soft);
  box-sizing: border-box;
}

.how-apps__icon {
  flex-shrink: 0;
  width: 1.65rem;
  height: 1.65rem;
  object-fit: contain;
}

.how-apps__icon--missing {
  width: 0;
  height: 0;
  margin: 0;
  padding: 0;
  border: 0;
  overflow: hidden;
}

.how-apps__label {
  min-width: 0;
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1.2;
  color: var(--how-text);
  text-align: left;
}

.how-apps--direct .how-apps__label {
  font-size: 0.64rem;
}

.how-card__perks {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1rem;
  padding: 0.85rem 0 0;
  margin: auto 0 0;
  border-top: 1px solid var(--how-border);
}

.how-card__perk {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.72rem;
  line-height: 1.3;
  color: var(--how-muted);
}

.how-card__perk-ico {
  flex-shrink: 0;
  color: var(--how-green);
}

.how-split {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  padding: 0.15rem 0;
  box-sizing: border-box;
}

@media (min-width: 960px) {
  .how-split {
    flex-direction: column;
    gap: 0.35rem;
    width: 2.75rem;
    max-width: 2.75rem;
    min-width: 2.75rem;
    padding: 0;
    justify-self: center;
    align-self: stretch;
  }
}

.how-split__line {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  border-top: 1px dashed var(--landing-decor);
}

@media (min-width: 960px) {
  .how-split__line {
    flex: 1 1 0;
    width: 0;
    min-width: 0;
    border-top: none;
    border-left: 1px dashed var(--landing-decor);
  }
}

.how-split__badge {
  flex-shrink: 0;
  margin: 0.35rem 0;
  padding: 0.4rem 0.55rem;
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--how-green);
  background: var(--landing-surface);
  border: 1px solid var(--how-border);
  border-radius: var(--radius-pill);
  box-shadow: 0 2px 8px var(--landing-shadow);
}

.how-highlights {
  display: grid;
  gap: 0.85rem;
  margin-top: clamp(1.5rem, 3vw, 2rem);
  text-align: left;
}

@media (min-width: 720px) {
  .how-highlights {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem;
  }
}

.how-highlight {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  padding: 1.1rem 1.15rem;
  border-radius: 16px;
  background: var(--landing-highlight-bg);
  border: 1px solid var(--how-border);
}

.how-highlight__ico {
  flex-shrink: 0;
  color: var(--how-green);
}

.how-highlight__copy {
  min-width: 0;
}

.how-highlight__title {
  margin: 0 0 0.3rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--how-text);
}

.how-highlight__text {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--how-muted);
}

/* ——— ПРОБНЫЙ ПЕРИОД ——— */
.section-trial {
  --trial-bg: var(--landing-surface);
  --trial-text: var(--landing-text);
  --trial-muted: var(--landing-muted);
  --trial-border: var(--landing-border);
  --trial-accent: var(--landing-accent);
  --trial-accent-soft: var(--landing-accent-soft);
  --trial-proof-bg: var(--landing-subtle-bg);
  padding-top: clamp(2rem, 5vw, 3.25rem);
  padding-bottom: clamp(2rem, 5vw, 3.25rem);
}

.section-trial .section-inner {
  text-align: left;
}

.trial-card {
  position: relative;
  border-radius: calc(var(--radius-lg) + 10px);
  border: 1px solid var(--trial-border);
  background: var(--trial-bg);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 12px 40px var(--landing-shadow);
  overflow: hidden;
}

.trial-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  background: var(--trial-accent);
  z-index: 1;
}

.trial-card__main {
  display: grid;
  gap: clamp(1.5rem, 3vw, 2.25rem);
  padding: clamp(1.75rem, 4vw, 2.5rem);
  padding-left: clamp(2rem, 4vw, 2.75rem);
}

@media (min-width: 900px) {
  .trial-card__main {
    grid-template-columns: minmax(0, 1.15fr) minmax(160px, 200px) auto;
    align-items: center;
    gap: clamp(1.25rem, 3vw, 2rem);
  }
}

.trial-card__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.85rem;
  margin-bottom: 0.85rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--trial-accent);
  border-radius: var(--radius-pill);
  background: var(--trial-accent-soft);
}

.trial-card__title {
  font-family: var(--heading);
  font-size: clamp(1.65rem, 3.5vw, 2.35rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  margin: 0 0 0.55rem;
  color: var(--trial-text);
  line-height: 1.15;
}

.trial-card__lead {
  margin: 0;
  max-width: 34rem;
  font-size: 0.98rem;
  line-height: 1.6;
  color: var(--trial-muted);
}

.trial-card__features {
  list-style: none;
  padding: 0;
  margin: 1.35rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.trial-card__feature {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.trial-card__feature-ico {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  color: var(--trial-accent);
  background: var(--trial-accent-soft);
}

.trial-card__feature-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
}

.trial-card__feature-text strong {
  font-size: 0.92rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--trial-text);
}

.trial-card__feature-text span {
  font-size: 0.84rem;
  line-height: 1.45;
  color: var(--trial-muted);
}

.trial-card__visual {
  display: none;
  justify-content: center;
  align-items: center;
}

@media (min-width: 900px) {
  .trial-card__visual {
    display: flex;
  }
}

.trial-visual {
  position: relative;
  width: 180px;
  height: 180px;
}

.trial-visual__ring {
  position: absolute;
  left: 50%;
  top: 50%;
  translate: -50% -50%;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--trial-muted) 35%, transparent);
}

.trial-visual__ring--1 {
  width: 88%;
  height: 88%;
}

.trial-visual__ring--2 {
  width: 68%;
  height: 68%;
}

.trial-visual__ring--3 {
  width: 48%;
  height: 48%;
}

.trial-visual__shield {
  position: absolute;
  left: 50%;
  top: 50%;
  translate: -50% -50%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 1.1rem;
  color: var(--trial-accent);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--landing-accent) 18%, transparent),
    color-mix(in srgb, var(--landing-accent) 6%, transparent)
  );
  box-shadow: 0 8px 24px color-mix(in srgb, var(--landing-accent) 12%, transparent);
}

.trial-visual__tile {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 0.65rem;
  color: var(--trial-accent);
  background: var(--landing-surface);
  border: 1px solid var(--trial-border);
  box-shadow: 0 4px 12px var(--landing-shadow);
}

.trial-visual__tile--tl {
  left: 8%;
  top: 12%;
}

.trial-visual__tile--tr {
  right: 8%;
  top: 12%;
}

.trial-visual__tile--bl {
  left: 8%;
  bottom: 12%;
}

.trial-visual__tile--br {
  right: 8%;
  bottom: 12%;
}

.trial-card__cta {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.5rem;
}

@media (min-width: 900px) {
  .trial-card__cta {
    align-items: flex-end;
    text-align: right;
    min-width: min(100%, 15rem);
  }
}

.trial-card__cta-btn {
  width: 100%;
  gap: 0.55rem;
  box-sizing: border-box;
}

@media (min-width: 900px) {
  .trial-card__cta-btn {
    width: auto;
    min-width: 14.5rem;
  }
}

.trial-card__hint {
  display: inline-flex;
  align-items: flex-start;
  gap: 0.4rem;
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--trial-muted);
  max-width: 16rem;
}

.trial-card__hint svg {
  flex-shrink: 0;
  margin-top: 0.1rem;
  color: var(--trial-accent);
}

@media (min-width: 900px) {
  .trial-card__hint {
    margin-left: auto;
    justify-content: flex-end;
  }
}

.trial-card__proof {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem 1.5rem;
  padding: 1rem clamp(1.5rem, 4vw, 2.25rem);
  padding-left: clamp(1.75rem, 4vw, 2.5rem);
  background: var(--trial-proof-bg);
  border-top: 1px solid var(--trial-border);
}

.trial-card__proof-users {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-width: min(100%, 22rem);
}

.trial-card__proof-badge {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.65rem;
  color: var(--trial-accent);
  background: var(--landing-surface);
  border: 1px solid var(--trial-border);
  box-shadow: 0 2px 8px var(--landing-shadow-soft);
}

.trial-card__proof-copy {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  text-align: left;
}

.trial-card__proof-copy strong {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--trial-text);
  line-height: 1.35;
}

.trial-card__proof-copy span {
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--trial-muted);
}

.trial-card__proof-rating {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 0.35rem 0.55rem;
  margin-left: auto;
  text-align: right;
}

.trial-card__proof-score {
  font-size: 0.95rem;
  font-weight: 800;
  color: var(--trial-text);
}

.trial-card__proof-stars {
  display: inline-flex;
  align-items: center;
  gap: 0.12rem;
  color: var(--trial-accent);
}

.trial-card__proof-reviews {
  flex-basis: 100%;
  font-size: 0.78rem;
  color: var(--trial-muted);
  text-align: right;
}

@media (max-width: 640px) {
  .trial-card__proof {
    flex-direction: column;
    align-items: flex-start;
  }

  .trial-card__proof-rating {
    margin-left: 0;
    align-self: stretch;
    width: 100%;
  }
}

/* ——— ТАРИФЫ ——— */
.section-pricing {
  --pricing-bg: var(--landing-bg-alt);
  --pricing-text: var(--landing-text);
  --pricing-muted: var(--landing-muted);
  --pricing-border: var(--landing-border);
  --pricing-accent: var(--landing-accent);
  --pricing-accent-soft: var(--landing-accent-soft);
  --pricing-card-bg: var(--landing-card);
  background: var(--pricing-bg);
}

.section-pricing .section-inner {
  text-align: center;
}

.pricing-head {
  margin-bottom: clamp(1.75rem, 4vw, 2.5rem);
}

.pricing-head__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 0 0.85rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--pricing-muted);
}

.pricing-head__eyebrow-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--pricing-accent);
  box-shadow: 0 0 0 3px var(--pricing-accent-soft);
}

.pricing-head__title {
  font-family: var(--heading);
  font-size: clamp(1.75rem, 4vw, 2.65rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.12;
  color: var(--pricing-text);
  margin: 0 0 0.85rem;
}

.pricing-head__accent {
  color: var(--pricing-accent);
}

.pricing-head__lead {
  margin: 0 auto 1.35rem;
  max-width: 38rem;
  font-size: 1rem;
  line-height: 1.65;
  color: var(--pricing-muted);
}

.pricing-trust-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.65rem 1.35rem;
  margin: 0 auto;
  padding: 0.85rem 1.25rem;
  max-width: 52rem;
  border-radius: calc(var(--radius-lg) + 4px);
  border: 1px solid var(--pricing-border);
  background: var(--pricing-card-bg);
  box-shadow: 0 2px 10px var(--landing-shadow-soft);
}

.pricing-trust-bar__item {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.84rem;
  font-weight: 600;
  line-height: 1.35;
  color: color-mix(in srgb, var(--pricing-muted) 35%, var(--pricing-text));
  text-align: left;
}

.pricing-trust-bar__icon {
  flex-shrink: 0;
  color: var(--pricing-accent);
}

.pricing-status {
  margin: 0 auto 1.5rem;
  max-width: 40rem;
  font-size: 1rem;
  line-height: 1.6;
  color: var(--pricing-muted);
}

.pricing-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.25rem;
  text-align: left;
  margin-bottom: clamp(1.5rem, 4vw, 2rem);
}

@media (min-width: 900px) {
  .pricing-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    align-items: stretch;
  }
}

.pricing-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: clamp(1.5rem, 3vw, 1.85rem);
  padding-top: 1.75rem;
  border-radius: calc(var(--radius-lg) + 8px);
  background: var(--pricing-card-bg);
  border: 1px solid var(--pricing-border);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 10px 28px var(--landing-shadow);
  overflow: visible;
  transition:
    transform 0.22s ease,
    box-shadow 0.22s ease,
    border-color 0.22s ease;
}

.pricing-card:hover {
  transform: translateY(-4px);
  box-shadow:
    0 2px 4px var(--landing-shadow),
    0 16px 36px var(--landing-shadow);
}

.pricing-card--popular {
  border-color: color-mix(in srgb, var(--pricing-accent) 35%, var(--pricing-border));
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--pricing-accent) 18%, transparent),
    0 16px 40px color-mix(in srgb, var(--landing-accent) 12%, transparent);
}

@media (min-width: 900px) {
  .pricing-card--popular {
    transform: translateY(-6px);
  }

  .pricing-card--popular:hover {
    transform: translateY(-9px);
  }
}

.pricing-card__ribbon {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translate(-50%, -52%);
  z-index: 2;
  padding: 0.38rem 0.95rem;
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--landing-on-accent);
  background: var(--pricing-accent);
  border-radius: var(--radius-pill);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--landing-accent) 28%, transparent);
  white-space: nowrap;
}

.pricing-card__period-badge {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  margin-bottom: 0.85rem;
  padding: 0.28rem 0.65rem;
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--pricing-muted);
  border-radius: var(--radius-pill);
  background: var(--landing-subtle-bg);
}

.pricing-card__header {
  margin-bottom: 1rem;
}

.pricing-card__name {
  font-family: var(--heading);
  margin: 0 0 0.35rem;
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--pricing-text);
}

.pricing-card__tagline {
  margin: 0;
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--pricing-muted);
}

.pricing-card__metrics {
  margin-bottom: 1rem;
}

.pricing-card__price-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.2rem 0.35rem;
  margin-bottom: 0.45rem;
}

.pricing-card__monthly-num {
  font-family: var(--heading);
  font-size: clamp(1.85rem, 3.5vw, 2.35rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  color: var(--pricing-accent);
  line-height: 1;
}

.pricing-card__monthly-unit {
  font-size: 0.95rem;
  font-weight: 700;
  color: color-mix(in srgb, var(--pricing-muted) 45%, var(--pricing-text));
}

.pricing-card__payment-hint {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--pricing-muted);
}

.pricing-card__billing-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.55rem;
}

.pricing-card__total-price {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--pricing-text);
}

.pricing-card__compare {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--pricing-muted);
  text-decoration: line-through;
}

.pricing-card__discount {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.45rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: var(--pricing-accent);
  border-radius: var(--radius-pill);
  background: var(--pricing-accent-soft);
}

.pricing-card__save {
  margin: 0.45rem 0 0;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.4;
  color: var(--pricing-accent);
}

.pricing-card__divider {
  margin: 0 0 1rem;
  border: 0;
  border-top: 1px solid var(--pricing-border);
}

.pricing-card__features {
  list-style: none;
  padding: 0;
  margin: 0 0 1.25rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.pricing-card__features li {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  font-size: 0.84rem;
  line-height: 1.45;
  color: color-mix(in srgb, var(--pricing-text) 88%, var(--pricing-muted));
}

.pricing-card__check {
  flex-shrink: 0;
  margin-top: 0.08rem;
  color: var(--pricing-accent);
}

.pricing-card__cta {
  margin-top: auto;
}

.pricing-card__btn {
  width: 100%;
  box-sizing: border-box;
}

.pricing-card--popular .pricing-card__btn.primary {
  box-shadow: 0 6px 18px color-mix(in srgb, var(--landing-accent) 28%, transparent);
}

.section-pricing .cta--outline {
  color: var(--pricing-accent);
  background: var(--landing-surface);
  border: 1.5px solid var(--pricing-accent);
  box-shadow: none;
}

.section-pricing .cta--outline:hover {
  color: var(--landing-on-accent);
  background: var(--pricing-accent);
  border-color: var(--pricing-accent);
}

.pricing-benefits {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.85rem;
  margin: 0 auto;
  padding: 1rem 1.15rem;
  max-width: 56rem;
  border-radius: calc(var(--radius-lg) + 4px);
  border: 1px solid var(--pricing-border);
  background: var(--pricing-card-bg);
  box-shadow: 0 2px 10px var(--landing-shadow-soft);
}

@media (min-width: 640px) {
  .pricing-benefits {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem 1.25rem;
  }
}

@media (min-width: 1024px) {
  .pricing-benefits {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.pricing-benefits__item {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  text-align: left;
}

.pricing-benefits__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.65rem;
  color: var(--pricing-accent);
  background: var(--pricing-accent-soft);
}

.pricing-benefits__copy {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 0;
}

.pricing-benefits__copy strong {
  font-size: 0.84rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--pricing-text);
}

.pricing-benefits__copy span {
  font-size: 0.76rem;
  line-height: 1.4;
  color: var(--pricing-muted);
}

.pricing-footnote {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.35rem 0.45rem;
  margin: clamp(1.75rem, 4vw, 2.35rem) auto 0;
  max-width: 42rem;
  text-align: center;
  font-size: 0.86rem;
  line-height: 1.55;
  color: var(--pricing-muted);
}

.pricing-footnote__icon {
  flex-shrink: 0;
  color: var(--pricing-accent);
}

.pricing-footnote__link {
  color: var(--pricing-accent);
  font-weight: 700;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}

.pricing-footnote__link:hover {
  color: var(--landing-accent-hover);
}

/* ——— FAQ ——— */
.section-faq {
  --faq-bg: var(--landing-section-muted-bg);
  --faq-text: var(--landing-text);
  --faq-muted: var(--landing-muted);
  --faq-border: var(--landing-border);
  --faq-accent: var(--landing-accent);
  --faq-accent-soft: var(--landing-accent-soft);
  --faq-card-bg: var(--landing-card);
  background: var(--faq-bg);
}

.section-faq .section-inner {
  text-align: center;
}

.faq-head {
  margin-bottom: clamp(1.5rem, 4vw, 2.25rem);
}

.faq-head__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0 0 0.85rem;
  padding: 0.35rem 0.85rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--faq-accent);
  border-radius: var(--radius-pill);
  background: var(--faq-accent-soft);
}

.faq-head__title {
  font-family: var(--heading);
  font-size: clamp(1.75rem, 4vw, 2.65rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.12;
  color: var(--faq-text);
  margin: 0 0 0.85rem;
}

.faq-head__lead {
  margin: 0 auto 1.35rem;
  max-width: 40rem;
  font-size: 1rem;
  line-height: 1.65;
  color: var(--faq-muted);
}

.faq-trust-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.85rem;
  margin: 0 auto;
  max-width: 56rem;
  padding: 1rem 1.15rem;
  border-radius: calc(var(--radius-lg) + 4px);
  border: 1px solid var(--faq-border);
  background: var(--faq-card-bg);
  box-shadow: 0 2px 10px var(--landing-shadow-soft);
}

@media (min-width: 640px) {
  .faq-trust-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1rem 1.25rem;
  }
}

@media (min-width: 1024px) {
  .faq-trust-row {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.faq-trust-row__item {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  text-align: left;
}

.faq-trust-row__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.65rem;
  color: var(--faq-accent);
  background: var(--faq-accent-soft);
}

.faq-trust-row__copy {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 0;
}

.faq-trust-row__copy strong {
  font-size: 0.84rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--faq-text);
}

.faq-trust-row__copy span {
  font-size: 0.76rem;
  line-height: 1.4;
  color: var(--faq-muted);
}

.faq-shell {
  max-width: 52rem;
  margin: 0 auto clamp(1.25rem, 3vw, 1.75rem);
  padding: clamp(0.35rem, 1.5vw, 0.65rem);
  border-radius: calc(var(--radius-lg) + 8px);
  border: 1px solid var(--faq-border);
  background: var(--faq-card-bg);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 12px 32px var(--landing-shadow);
}

.faq-accordion {
  text-align: left;
}

.faq-item {
  border-bottom: 1px solid var(--faq-border);
}

.faq-item:last-child {
  border-bottom: none;
}

.faq-item__heading {
  margin: 0;
  font-size: inherit;
  font-weight: inherit;
}

.faq-question {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 1.05rem 1rem;
  background: none;
  border: none;
  font-family: var(--sans);
  cursor: pointer;
  text-align: left;
  border-radius: var(--radius);
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.faq-question:hover {
  background: var(--faq-accent-soft);
}

.faq-item.is-open .faq-question {
  color: var(--faq-accent);
}

.faq-question__mark {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  color: var(--faq-accent);
  background: var(--faq-accent-soft);
}

.faq-question__text {
  flex: 1;
  min-width: 0;
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--faq-text);
}

.faq-item.is-open .faq-question__text {
  color: var(--faq-accent);
}

.faq-icon {
  flex-shrink: 0;
  color: var(--faq-muted);
  transition:
    transform 0.25s ease,
    color 0.25s ease;
  display: flex;
  align-items: center;
}

.faq-item.is-open .faq-icon {
  transform: rotate(180deg);
  color: var(--faq-accent);
}

.faq-answer-wrapper {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.32s ease-out;
}

.faq-item.is-open .faq-answer-wrapper {
  grid-template-rows: 1fr;
}

.faq-answer {
  overflow: hidden;
  color: var(--faq-muted);
  font-size: 0.94rem;
  line-height: 1.65;
  padding: 0 1rem 0 3.85rem;
}

.faq-item.is-open .faq-answer {
  padding-bottom: 1.15rem;
}

@media (max-width: 560px) {
  .faq-answer {
    padding-left: 1rem;
  }
}

.faq-support {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem 1.25rem;
  max-width: 52rem;
  margin: 0 auto;
  padding: 1rem 1.15rem;
  border-radius: calc(var(--radius-lg) + 4px);
  border: 1px solid var(--faq-border);
  background: var(--faq-card-bg);
  box-shadow: 0 2px 10px var(--landing-shadow-soft);
  text-align: left;
}

.faq-support__copy {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-width: min(100%, 18rem);
}

.faq-support__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.65rem;
  color: var(--faq-accent);
  background: var(--faq-accent-soft);
}

.faq-support__text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.faq-support__text strong {
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--faq-text);
  line-height: 1.35;
}

.faq-support__text span {
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--faq-muted);
}

.faq-support__btn {
  gap: 0.55rem;
  margin-left: auto;
  box-sizing: border-box;
}

@media (max-width: 640px) {
  .faq-support__btn {
    width: 100%;
    margin-left: 0;
  }
}

/* ——— ФИНАЛЬНЫЙ CTA ——— */
.section-final {
  --final-bg: var(--landing-section-muted-bg);
  --final-text: var(--landing-text);
  --final-muted: var(--landing-muted);
  --final-border: var(--landing-border);
  --final-accent: var(--landing-accent);
  --final-accent-soft: var(--landing-accent-soft);
  --final-card-bg: var(--landing-card);
  padding-bottom: clamp(4rem, 8vw, 6rem);
  background: var(--final-bg);
}

.section-final .section-inner {
  text-align: left;
}

.final-cta-card {
  display: grid;
  gap: clamp(1.5rem, 3vw, 2rem);
  padding: clamp(1.65rem, 4vw, 2.25rem);
  border-radius: calc(var(--radius-lg) + 10px);
  border: 1px solid var(--final-border);
  background: var(--final-card-bg);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 14px 40px var(--landing-shadow);
  overflow: hidden;
}

@media (min-width: 900px) {
  .final-cta-card {
    grid-template-columns: minmax(0, 1.1fr) minmax(260px, 0.9fr);
    align-items: center;
    gap: clamp(1.25rem, 3vw, 2rem);
  }
}

.final-cta-card__pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.85rem;
  padding: 0.35rem 0.85rem;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--final-accent);
  border-radius: var(--radius-pill);
  background: var(--final-accent-soft);
}

.final-cta-card__title {
  font-family: var(--heading);
  font-size: clamp(1.45rem, 3vw, 2.1rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.18;
  margin: 0 0 0.65rem;
  color: var(--final-text);
}

.final-cta-card__accent {
  color: var(--final-accent);
}

.final-cta-card__lead {
  margin: 0 0 1.25rem;
  font-size: 0.96rem;
  line-height: 1.62;
  color: var(--final-muted);
  max-width: 36rem;
}

.final-cta-card__features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.85rem;
}

@media (min-width: 560px) {
  .final-cta-card__features {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.75rem;
  }
}

.final-cta-card__feature {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  min-width: 0;
}

.final-cta-card__feature-ico {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.15rem;
  height: 2.15rem;
  border-radius: 0.65rem;
  color: var(--final-accent);
  background: var(--landing-subtle-bg);
  border: 1px solid var(--final-border);
}

.final-cta-card__feature-text {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 0;
}

.final-cta-card__feature-text strong {
  font-size: 0.8rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--final-text);
}

.final-cta-card__feature-text span {
  font-size: 0.72rem;
  line-height: 1.4;
  color: var(--final-muted);
}

.final-cta-card__aside {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
}

.final-visual {
  position: relative;
  width: min(100%, 320px);
  height: 200px;
  margin-bottom: 1rem;
}

@media (min-width: 900px) {
  .final-visual {
    width: 100%;
    height: 240px;
    margin-bottom: 0;
  }

  .final-cta-card__btn {
    position: absolute;
    right: clamp(0.5rem, 2vw, 1.25rem);
    bottom: clamp(0.5rem, 2vw, 1.25rem);
    z-index: 2;
    min-width: 13.5rem;
  }
}

.final-visual__map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  opacity: 0.35;
  pointer-events: none;
}

.final-visual__ring {
  position: absolute;
  left: 50%;
  top: 50%;
  translate: -50% -50%;
  border-radius: 50%;
  border: 1px dashed color-mix(in srgb, var(--final-muted) 35%, transparent);
}

.final-visual__ring--1 {
  width: 72%;
  height: 72%;
}

.final-visual__ring--2 {
  width: 48%;
  height: 48%;
}

.final-visual__shield {
  position: absolute;
  left: 50%;
  top: 50%;
  translate: -50% -50%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4.25rem;
  height: 4.25rem;
  border-radius: 1rem;
  color: var(--final-accent);
  background: linear-gradient(
    145deg,
    color-mix(in srgb, var(--landing-accent) 18%, transparent),
    color-mix(in srgb, var(--landing-accent) 6%, transparent)
  );
  box-shadow: 0 8px 24px color-mix(in srgb, var(--landing-accent) 12%, transparent);
}

.final-visual__pin {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--final-accent);
  filter: drop-shadow(0 2px 6px color-mix(in srgb, var(--landing-accent) 20%, transparent));
}

.final-visual__pin--tl {
  left: 14%;
  top: 18%;
}

.final-visual__pin--tr {
  right: 12%;
  top: 22%;
}

.final-visual__pin--bl {
  left: 18%;
  bottom: 16%;
}

.final-visual__pin--br {
  right: 16%;
  bottom: 20%;
}

.final-cta-card__btn {
  gap: 0.55rem;
  width: 100%;
  max-width: 18rem;
  box-sizing: border-box;
  box-shadow: 0 8px 22px color-mix(in srgb, var(--landing-accent) 28%, transparent);
}

@media (max-width: 899px) {
  .final-cta-card__aside {
    padding-top: 0.5rem;
  }
}

/* ——— FOOTER ——— */
.footer {
  --footer-bg: var(--landing-bg-alt);
  --footer-text: var(--landing-text);
  --footer-muted: var(--landing-muted);
  --footer-border: var(--landing-border);
  --footer-accent: var(--landing-accent);
  --footer-accent-soft: var(--landing-accent-soft);
  --footer-card-bg: var(--landing-card);
  padding: clamp(2rem, 5vw, 3rem) 1.25rem clamp(1.5rem, 3vw, 2rem);
  background: var(--footer-bg);
}

.footer-shell {
  max-width: min(var(--landing-content-max, 84rem), 100%);
  margin: 0 auto;
  padding: clamp(1.35rem, 3vw, 1.85rem);
  border-radius: calc(var(--radius-lg) + 10px);
  border: 1px solid var(--footer-border);
  background: var(--footer-card-bg);
  box-shadow:
    0 1px 2px var(--landing-shadow-soft),
    0 12px 36px var(--landing-shadow);
}

.footer-top {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.75rem 1.25rem;
}

@media (min-width: 768px) {
  .footer-top {
    grid-template-columns: minmax(0, 1.35fr) repeat(3, minmax(0, 1fr));
    gap: 1.5rem 1.75rem;
  }
}

.footer-brand {
  max-width: 22rem;
}

.footer-brand__logo {
  display: block;
  width: min(100%, 11.5rem);
  height: auto;
  margin-bottom: 0.85rem;
}

.footer-brand__desc {
  margin: 0 0 1rem;
  color: var(--footer-muted);
  font-size: 0.88rem;
  line-height: 1.58;
}

.footer-social {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.footer-social__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.35rem;
  height: 2.35rem;
  border-radius: 0.65rem;
  color: var(--footer-accent);
  background: var(--landing-subtle-bg);
  border: 1px solid var(--footer-border);
  text-decoration: none;
  transition:
    background 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;
}

.footer-social__btn:hover {
  color: var(--landing-on-accent);
  background: var(--footer-accent);
  border-color: var(--footer-accent);
}

.footer-col__title {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 0 0.85rem;
  font-size: 0.92rem;
  font-weight: 800;
  color: var(--footer-text);
}

.footer-col__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--footer-accent);
  box-shadow: 0 0 0 3px var(--footer-accent-soft);
}

.footer-col__list,
.footer-col__contacts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.footer-col__list a {
  color: var(--footer-muted);
  text-decoration: none;
  font-size: 0.84rem;
  font-weight: 500;
  line-height: 1.45;
  transition: color 0.2s ease;
}

.footer-col__list a:hover {
  color: var(--footer-accent);
}

.footer-col__contacts li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.84rem;
  line-height: 1.45;
  color: var(--footer-muted);
}

.footer-col__contact-ico {
  flex-shrink: 0;
  color: var(--footer-accent);
}

.footer-col__contact-link {
  color: var(--footer-accent);
  font-weight: 700;
  text-decoration: none;
}

.footer-col__contact-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.footer-highlights {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.85rem;
  margin-top: clamp(1.35rem, 3vw, 1.75rem);
  padding: 1rem 1.1rem;
  border-radius: calc(var(--radius-lg) + 2px);
  border: 1px solid var(--footer-border);
  background: var(--landing-section-muted-bg);
}

@media (min-width: 640px) {
  .footer-highlights {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.85rem 1rem;
  }
}

@media (min-width: 1024px) {
  .footer-highlights {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.footer-highlights__item {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding-right: 0.35rem;
}

@media (min-width: 1024px) {
  .footer-highlights__item:not(:last-child) {
    border-right: 1px solid var(--footer-border);
  }
}

.footer-highlights__icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 0.65rem;
  color: var(--footer-accent);
  background: var(--footer-accent-soft);
}

.footer-highlights__copy {
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  min-width: 0;
}

.footer-highlights__copy strong {
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--footer-text);
}

.footer-highlights__copy span {
  font-size: 0.74rem;
  line-height: 1.4;
  color: var(--footer-muted);
}

.footer-bottom {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.85rem 1rem;
  margin-top: clamp(1.25rem, 3vw, 1.65rem);
  padding-top: 1.15rem;
  border-top: 1px solid var(--footer-border);
  align-items: center;
}

@media (min-width: 900px) {
  .footer-bottom {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) auto;
  }
}

.footer-bottom__note {
  display: inline-flex;
  align-items: flex-start;
  gap: 0.4rem;
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.45;
  color: var(--footer-muted);
  text-align: left;
}

.footer-bottom__note--center {
  justify-self: center;
}

@media (max-width: 899px) {
  .footer-bottom__note--center {
    justify-self: start;
  }
}

.footer-bottom__ico {
  flex-shrink: 0;
  margin-top: 0.08rem;
  color: var(--footer-accent);
}

.footer-payments {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.45rem 0.65rem;
  padding: 0.45rem 0.7rem;
  border-radius: var(--radius-pill);
  border: 1px solid var(--footer-border);
  background: var(--landing-surface);
}

@media (max-width: 899px) {
  .footer-payments {
    justify-content: flex-start;
  }
}

.footer-payments__logo {
  display: block;
  width: auto;
  height: 1.15rem;
  object-fit: contain;
  opacity: 0.88;
}
</style>
