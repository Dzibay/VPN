<script setup>
/**
 * Картинки для первых двух секций — положите в frontend/public/images/home/:
 *   hero-bg-map.png      — точечная карта мира на фоне hero (опционально)
 *   hero-app-mockup.png  — макет приложения справа (обязательно для макета)
 *   trust-avatars.png    — 4 аватара для блока «10 000+ пользователей» (опционально)
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
  Globe,
  Headphones,
  Lock,
  Monitor,
  Shield,
  Star,
  Zap,
} from 'lucide-vue-next'
import { getAccessToken, getSessionRole } from '../auth/session.js'
import { defaultPathAfterLogin } from '../auth/permissions.js'
import { sitePublicUrl } from '../api/client.js'

/** @type {const} */
const HOME_IMAGES = {
  bgMap: '/images/home/hero-bg-map.png',
  appMockup: '/images/home/hero-app-mockup.png',
  trustAvatars: '/images/home/trust-avatars.png',
}

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

onMounted(refreshAuth)
router.afterEach(refreshAuth)

const services = {
  vpn: [
    'YouTube',
    'Instagram',
    'Google Gemini',
    'Netflix',
    'ChatGPT',
    'Claude AI',
  ],
  direct: [
    'Сбербанк',
    'Т-Банк',
    'Госуслуги',
    'Кинопоиск',
    'Яндекс Еда',
    'Wildberries',
  ],
}

/** Одни и те же возможности на любом сроке — меняется только цена. */
const planIncludes = [
  'Split tunneling: РФ напрямую, зарубежное через VPN',
  'Протокол VLESS и ключ подписки в личном кабинете',
  'До 5 устройств одновременно на один ключ',
]

/**
 * @typedef {{
 *   id: number;
 *   name: string;
 *   tagline: string;
 *   monthlyHighlight: string;
 *   totalPrice: string;
 *   periodShort: string;
 *   compareAtTotal: string | null;
 *   savingsLabel: string | null;
 *   popular: boolean;
 *   ctaGuest: string;
 * }} PlanRow
 */

/** @type {PlanRow[]} */
const plans = [
  {
    id: 1,
    name: '1 месяц',
    tagline: 'Попробовать без долгих обязательств.',
    monthlyHighlight: '100 ₽',
    totalPrice: '100 ₽',
    periodShort: 'за 30 дней',
    compareAtTotal: null,
    savingsLabel: null,
    popular: false,
    ctaGuest: 'Оформить месяц',
  },
  {
    id: 3,
    name: '6 месяцев',
    tagline: 'Лучшее соотношение срока и цены за месяц.',
    monthlyHighlight: '85 ₽',
    totalPrice: '510 ₽',
    periodShort: 'единый платёж',
    compareAtTotal: '600 ₽',
    savingsLabel: 'Экономия 90 ₽ к шести месяцам по 100 ₽',
    popular: true,
    ctaGuest: 'Подключить на полгода',
  },
  {
    id: 4,
    name: '12 месяцев',
    tagline: 'Минимальная цена месяца при оплате раз в год.',
    monthlyHighlight: '80 ₽',
    totalPrice: '960 ₽',
    periodShort: 'единый платёж',
    compareAtTotal: '1 200 ₽',
    savingsLabel: 'Экономия 240 ₽ к двенадцати месяцам по 100 ₽',
    popular: false,
    ctaGuest: 'Взять на год',
  },
]

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
    q: 'На каких устройствах работает?',
    a:
      'Мы поддерживаем Android, iOS, Windows и macOS. Вы можете использовать удобные клиенты вроде V2Ray или Happ с современным протоколом VLESS.',
  },
  {
    q: 'Сколько устройств можно подключить?',
    a:
      'По одной подписке вы можете подключить до 5 устройств одновременно без потери скорости.',
  },
]

const activeFaq = ref(null)

function toggleFaq(index) {
  activeFaq.value = activeFaq.value === index ? null : index
}

/** JSON-LD FAQ для поисковых систем (Google понимает SPA при рендере). */
let faqLdEl = null

onMounted(() => {
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
            Безопасный интернет без ограничений
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
              <RouterLink class="hero__btn hero__btn--primary" :to="loggedInHomeCtaPath">
                Перейти в кабинет
                <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
              </RouterLink>
            </template>
            <template v-else>
              <RouterLink class="hero__btn hero__btn--primary" to="/register">
                Начать пользоваться VPN
                <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
              </RouterLink>
              <a class="hero__btn hero__btn--secondary" href="#pricing">
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

    <!-- КАК РАБОТАЕТ -->
    <section
      id="how"
      class="section section-how"
      aria-labelledby="how-heading"
    >
      <div class="section-inner">
        <p class="section-eyebrow">Умная маршрутизация</p>
        <h2 id="how-heading" class="section-title">
          Две дороги из одного VPN
        </h2>
        <p class="section-lead">
          Подорожник делит трафик автоматически: международные сервисы идут через
          зашифрованный канал (VLESS), а привычные российские приложения —
          по вашему обычному IP, без лишних задержек
        </p>

        <div class="how-panels">
          <article class="how-panel how-panel--vpn">
            <header class="how-panel__head">
              <span class="how-panel__tag how-panel__tag--vpn">Туннель</span>
              <h3 class="how-panel__title">Через VPN</h3>
              <p class="how-panel__sub">
                Стриминг, соцсети, ИИ и всё, что за рубежом
              </p>
            </header>
            <ul class="chip-list" role="list">
              <li
                v-for="s in services.vpn"
                :key="s"
                class="chip chip--vpn"
              >
                {{ s }}
              </li>
            </ul>
          </article>

          <div class="how-connector" aria-hidden="true">
            <span class="how-connector__line" />
            <span class="how-connector__badge">split</span>
            <span class="how-connector__line" />
          </div>

          <article class="how-panel how-panel--direct">
            <header class="how-panel__head">
              <span class="how-panel__tag how-panel__tag--direct">
                Прямой IP
              </span>
              <h3 class="how-panel__title">Напрямую (РФ)</h3>
              <p class="how-panel__sub">
                Банки, госуслуги и локальные сервисы без обходов
              </p>
            </header>
            <ul class="chip-list" role="list">
              <li
                v-for="s in services.direct"
                :key="s"
                class="chip chip--direct"
              >
                {{ s }}
              </li>
            </ul>
          </article>
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

    <!-- ТАРИФЫ -->
    <section
      id="pricing"
      class="section section-pricing"
      aria-labelledby="pricing-trial-title"
      aria-describedby="pricing-plans-heading"
    >
      <div class="section-inner">
        <div class="pricing-trial">
          <div class="pricing-trial__grid">
            <div class="pricing-trial__copy">
              <span class="pricing-trial__pill">Пробный период</span>
              <h2 id="pricing-trial-title" class="pricing-trial__title">
                14 дней бесплатно
              </h2>
              <p class="pricing-trial__lead">
                Оцените split tunneling и подписку VLESS без карты и без ограничений по функциям.
              </p>
              <ul class="pricing-trial__checks" aria-label="Что входит в пробный период">
                <li>Без привязки банковской карты</li>
                <li>Те же правила маршрутизации, что после оплаты</li>
                <li>До 5 устройств на одну подписку</li>
              </ul>
            </div>
            <div class="pricing-trial__aside">
              <RouterLink
                v-if="isLoggedIn"
                class="cta primary large pricing-trial__cta"
                :to="loggedInHomeCtaPath"
              >
                Перейти в кабинет
              </RouterLink>
              <RouterLink
                v-else
                class="cta primary large pricing-trial__cta"
                to="/register"
              >
                Начать бесплатно
              </RouterLink>
              <p class="pricing-trial__hint">
                Регистрация занимает минуту — ключ подписки в личном кабинете.
              </p>
            </div>
          </div>
        </div>

        <div class="pricing-plans-head">
          <p class="section-eyebrow section-eyebrow--center">Подписка</p>
          <h3
            id="pricing-plans-heading"
            class="pricing-plans-heading"
          >
            Один сервис — три способа платить
          </h3>
          <p class="pricing-plans-lead">
            На любом тарифе одинаковые возможности: умная маршрутизация, VLESS и до 5
            устройств. Отличается только срок и сумма за месяц.
          </p>
          <div
            class="pricing-trust-strip"
            aria-label="Ключевые условия"
          >
            <span class="pricing-trust-strip__item">
              <svg class="pricing-trust-strip__icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Полный функционал на всех планах
            </span>
            <span class="pricing-trust-strip__dot" aria-hidden="true" />
            <span class="pricing-trust-strip__item">
              <svg class="pricing-trust-strip__icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Цены на сайте — без навязанных доплат
            </span>
            <span class="pricing-trust-strip__dot" aria-hidden="true" />
            <span class="pricing-trust-strip__item">
              <svg class="pricing-trust-strip__icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
              Один ключ — смартфон и компьютер
            </span>
          </div>
        </div>

        <div
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
            <div v-if="plan.popular" class="pricing-card__ribbon">
              Чаще выбирают
            </div>
            <div class="pricing-card__header">
              <h4 class="pricing-card__name">{{ plan.name }}</h4>
              <p class="pricing-card__tagline">{{ plan.tagline }}</p>
            </div>

            <div class="pricing-card__metrics">
              <div class="pricing-card__monthly-big">
                <span class="pricing-card__monthly-num">{{ plan.monthlyHighlight }}</span>
                <span class="pricing-card__monthly-unit">в месяц</span>
                <span class="pricing-card__monthly-hint">при оплате за период целиком</span>
              </div>

              <div class="pricing-card__total-row">
                <template v-if="plan.compareAtTotal">
                  <span class="pricing-card__compare">{{ plan.compareAtTotal }}</span>
                </template>
                <span class="pricing-card__total-price">{{ plan.totalPrice }}</span>
                <span class="pricing-card__period-badge">{{ plan.periodShort }}</span>
              </div>

              <p
                v-if="plan.savingsLabel"
                class="pricing-card__save"
              >
                {{ plan.savingsLabel }}
              </p>
            </div>

            <ul class="pricing-card__features" aria-label="Что входит">
              <li
                v-for="(line, idx) in planIncludes"
                :key="idx"
              >
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

        <p class="pricing-footnote">
          После <RouterLink class="pricing-footnote__link" to="/register">регистрации</RouterLink>
          вы получите пробный доступ на 14 дней — затем можно выбрать любой из тарифов в личном кабинете.
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
        <p class="section-eyebrow">Поддержка</p>
        <h2 id="faq-heading" class="section-title">
          Частые вопросы
        </h2>
        <p class="section-lead section-lead--narrow">
          Коротко о том, как устроен умный VPN и чего ждать после регистрации.
        </p>

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
                  {{ faq.q }}
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
      </div>
    </section>

    <!-- ФИНАЛЬНЫЙ CTA -->
    <section
      class="section section-final"
      aria-labelledby="final-cta-heading"
    >
      <div class="section-inner section-inner--cta">
        <div class="final-cta-card">
          <div class="final-cta-card__accent" aria-hidden="true" />
          <div class="final-cta-card__main">
            <p class="section-eyebrow final-cta-card__eyebrow">
              Следующий шаг
            </p>
            <h2
              id="final-cta-heading"
              class="final-cta-card__title"
            >
              Забудьте про постоянное включение и выключение VPN
            </h2>
            <p class="final-cta-card__lead">
              Один раз настроили маршруты — дальше интернет ведёт себя предсказуемо:
              сервисы за рубежом через туннель, российские приложения без лишних обходов.
            </p>
          </div>
          <div class="final-cta-card__action">
            <RouterLink
              v-if="isLoggedIn"
              class="cta primary large final-cta-card__btn"
              :to="loggedInHomeCtaPath"
            >
              Открыть кабинет
            </RouterLink>
            <RouterLink
              v-else
              class="cta primary large final-cta-card__btn"
              to="/register"
            >
              Создать аккаунт
            </RouterLink>
            <RouterLink
              v-if="!isLoggedIn"
              class="cta secondary final-cta-card__btn-secondary"
              to="/login"
            >
              Уже есть аккаунт — войти
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
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="footer-logo">Подорожник VPN</span>
          <p class="footer-desc">
            Умный VPN на VLESS с split tunneling: зарубежное — через туннель,
            российское — напрямую.
          </p>
        </div>
        <nav
          class="footer-links"
          aria-label="Разделы главной страницы"
        >
          <a href="#how">Как работает</a>
          <a href="#benefits">Почему мы</a>
          <a href="#pricing">Тарифы</a>
        </nav>
      </div>
      <div class="footer-bottom">
        <span>© 2026 Подорожник VPN. Все права защищены.</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.home {
  flex: 1;
  color: var(--text);
  display: flex;
  flex-direction: column;
}

.home :is(section[id]) {
  scroll-margin-top: 4.5rem;
}

.section {
  padding: clamp(3.25rem, 7vw, 5.5rem) 1.25rem;
}

.section-inner {
  max-width: 72rem;
  margin: 0 auto;
  text-align: center;
}

.section-title {
  font-family: var(--heading);
  font-size: clamp(1.85rem, 4.2vw, 2.65rem);
  margin: 0 0 1rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.15;
  color: var(--text-h);
}

.section-lead {
  font-size: 1.08rem;
  line-height: 1.65;
  color: var(--muted);
  margin: 0 auto 2.5rem;
  max-width: 42rem;
}

.section-lead--narrow {
  max-width: 36rem;
}

.section-eyebrow {
  margin: 0 0 0.65rem;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--accent);
}

.section-eyebrow--center {
  text-align: center;
}

.text-accent {
  color: var(--accent);
  background: linear-gradient(120deg, var(--accent), #8b5cf6);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.text-green {
  color: #10b981;
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
  --home-bg: #ffffff;
  --home-text: #111827;
  --home-muted: #6b7280;
  --home-border: #e5e7eb;
  --home-accent: #1d9a5c;
  --home-accent-hover: #18804d;
  --home-accent-soft: rgba(29, 154, 92, 0.1);
  --home-on-accent: #ffffff;

  position: relative;
  padding: clamp(2rem, 5vw, 3.5rem) clamp(1rem, 4vw, 2rem) clamp(3rem, 6vw, 4.5rem);
  background: var(--home-bg);
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
  right: -8%;
  top: 50%;
  transform: translateY(-50%);
  width: min(72%, 52rem);
  height: auto;
  max-height: 100%;
  object-fit: contain;
  object-position: right center;
  opacity: 0.55;
}

@media (max-width: 1023px) {
  .hero__bg-map {
    left: 50%;
    right: auto;
    top: 58%;
    transform: translate(-50%, -50%);
    width: min(128%, 40rem);
    max-height: none;
    object-position: center center;
    opacity: 0.42;
  }
}

@media (max-width: 1023px) {
  .hero--landing {
    padding-bottom: clamp(2.5rem, 8vw, 3.5rem);
  }

  .hero__bg-map {
    left: 50%;
    right: auto;
    top: 58%;
    transform: translate(-50%, -50%);
    width: min(175%, 28rem);
    max-width: none;
    max-height: none;
    object-fit: contain;
    object-position: center center;
    opacity: 0.42;
  }
}

.hero__container {
  position: relative;
  z-index: 1;
  max-width: 72rem;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr;
  gap: 2.5rem;
  align-items: center;
}

@media (min-width: 1024px) {
  .hero__container {
    grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
    gap: 1.5rem 2rem;
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
  border: 1px solid rgba(29, 154, 92, 0.2);
}

.hero__badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--home-accent);
  box-shadow: 0 0 0 0 rgba(29, 154, 92, 0.45);
  animation: hero-badge-pulse 2s infinite;
}

@keyframes hero-badge-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(29, 154, 92, 0.45);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(29, 154, 92, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(29, 154, 92, 0);
  }
}

.hero__title {
  margin: 0 0 1rem;
  font-family: var(--heading);
  font-size: clamp(2rem, 4.2vw, 3.35rem);
  font-weight: 800;
  line-height: 1.12;
  letter-spacing: -0.035em;
  color: var(--home-text);
}

.hero__lead {
  margin: 0 0 1.35rem;
  max-width: 34rem;
  font-size: clamp(0.95rem, 1.8vw, 1.05rem);
  line-height: 1.6;
  color: var(--home-muted);
}

.hero__features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0 0 1.5rem;
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
  gap: 0.55rem;
  padding: 0.75rem 0.65rem;
  border: 1px solid var(--home-border);
  border-radius: 12px;
  background: #fff;
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

.hero__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.85rem 1.35rem;
  border-radius: 12px;
  font-size: 0.95rem;
  font-weight: 700;
  text-decoration: none;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    background 0.2s ease,
    border-color 0.2s ease;
}

.hero__btn--primary {
  color: var(--home-on-accent);
  background: linear-gradient(135deg, #58d68d 0%, #45b39d 100%);
  box-shadow: 0 4px 14px rgba(29, 154, 92, 0.28);
  border: none;
}

.hero__btn--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(29, 154, 92, 0.32);
  filter: brightness(1.04);
}

.hero__btn--secondary {
  color: var(--home-text);
  background: #fff;
  border: 1px solid var(--home-border);
}

.hero__btn--secondary:hover {
  border-color: rgba(29, 154, 92, 0.35);
  color: var(--home-accent);
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
  border: 2px solid #fff;
  margin-left: -0.55rem;
  background: linear-gradient(135deg, #d1d5db, #9ca3af);
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
  color: #f59e0b;
}

.hero__visual {
  display: none;
  justify-content: center;
  align-items: flex-start;
  min-width: 0;
}

@media (min-width: 1024px) {
  .hero__visual {
    display: flex;
  }
}

.hero__mockup {
  width: min(100%, 26rem);
  height: auto;
  object-fit: contain;
  filter: drop-shadow(0 18px 40px rgba(15, 23, 42, 0.12));
}

@media (min-width: 1024px) {
  .hero__mockup {
    width: min(100%, 32rem);
    margin-right: -1rem;
  }
}

/* ——— ПОЧЕМУ ВЫБИРАЮТ ——— */
.section-why {
  --home-bg: #ffffff;
  --home-text: #111827;
  --home-muted: #6b7280;
  --home-border: #e5e7eb;
  --home-accent: #1d9a5c;
  --home-accent-soft: rgba(29, 154, 92, 0.1);

  padding: clamp(2.5rem, 5vw, 3.75rem) clamp(1rem, 4vw, 2rem);
  background: var(--home-bg);
  border-top: 1px solid var(--home-border);
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
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.why-card:hover {
  border-color: rgba(29, 154, 92, 0.28);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
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
.section-how {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--bg) 100%, transparent) 0%,
    color-mix(in srgb, var(--surface) 35%, var(--bg)) 50%,
    color-mix(in srgb, var(--bg) 100%, transparent) 100%
  );
  border-block: 1px solid color-mix(in srgb, var(--card-border) 65%, transparent);
}

.how-panels {
  display: grid;
  gap: 1.5rem;
  align-items: stretch;
  margin-top: 0.5rem;
}

@media (min-width: 900px) {
  .how-panels {
    grid-template-columns: 1fr auto 1fr;
    gap: 1.25rem;
    align-items: center;
  }
}

.how-panel {
  position: relative;
  text-align: left;
  padding: clamp(1.35rem, 3vw, 1.85rem);
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--card-bg) 88%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(14px);
  overflow: hidden;
}

.how-panel::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 3px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.how-panel--vpn::before {
  background: linear-gradient(
    90deg,
    var(--accent),
    color-mix(in srgb, var(--accent) 40%, #8b5cf6)
  );
}

.how-panel--direct::before {
  background: linear-gradient(
    90deg,
    #10b981,
    color-mix(in srgb, #58d68d 70%, #45b39d)
  );
}

.how-panel__head {
  margin-bottom: 1.25rem;
}

.how-panel__tag {
  display: inline-block;
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 0.28rem 0.65rem;
  border-radius: var(--radius-pill);
  margin-bottom: 0.65rem;
}

.how-panel__tag--vpn {
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.how-panel__tag--direct {
  background: color-mix(in srgb, #10b981 16%, transparent);
  color: #34d399;
  border: 1px solid color-mix(in srgb, #10b981 45%, transparent);
}

.how-panel__title {
  font-family: var(--heading);
  margin: 0 0 0.35rem;
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--text-h);
  letter-spacing: -0.02em;
}

.how-panel__sub {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.5;
  color: var(--muted);
}

.chip-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.45rem 0.75rem;
  border-radius: var(--radius-pill);
  font-size: 0.82rem;
  font-weight: 600;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface) 90%, transparent);
  color: var(--text-h);
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    transform 0.2s ease;
}

.chip:hover {
  transform: translateY(-1px);
}

.chip--vpn {
  border-color: color-mix(in srgb, var(--accent-border) 55%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
}

.chip--direct {
  border-color: color-mix(in srgb, #10b981 35%, var(--card-border));
  background: color-mix(in srgb, #10b981 7%, var(--surface));
}

.how-connector {
  display: none;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0 0.25rem;
}

@media (min-width: 900px) {
  .how-connector {
    display: flex;
  }
}

.how-connector__line {
  width: 2px;
  height: 2rem;
  border-radius: 2px;
  background: linear-gradient(
    180deg,
    transparent,
    var(--card-border),
    transparent
  );
}

.how-connector__badge {
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 0.35rem 0.55rem;
  border-radius: var(--radius-pill);
  border: 1px dashed color-mix(in srgb, var(--muted) 45%, var(--card-border));
  background: color-mix(in srgb, var(--surface) 88%, transparent);
}

/* ——— ТАРИФЫ ——— */
.section-pricing {
  background: linear-gradient(
    180deg,
    transparent,
    color-mix(in srgb, var(--accent) 4%, transparent) 40%,
    transparent
  );
}

.pricing-trial {
  position: relative;
  margin-bottom: clamp(2.5rem, 5vw, 3.75rem);
  border-radius: calc(var(--radius-lg) + 8px);
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface-glass) 94%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(18px);
  overflow: hidden;
  text-align: left;
}

.pricing-trial::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(
    180deg,
    var(--accent),
    color-mix(in srgb, var(--accent-muted) 85%, #8b5cf6)
  );
}

.pricing-trial__grid {
  display: grid;
  gap: clamp(1.35rem, 4vw, 2rem);
  padding: clamp(1.45rem, 4vw, 2.2rem);
  padding-left: clamp(1.6rem, 4vw, 2.35rem);
}

@media (min-width: 768px) {
  .pricing-trial__grid {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: clamp(1.75rem, 4vw, 2.75rem);
  }
}

.pricing-trial__pill {
  display: inline-flex;
  align-items: center;
  padding: 0.3rem 0.8rem;
  margin-bottom: 0.75rem;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.11em;
  text-transform: uppercase;
  color: var(--accent);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--accent) 9%, transparent);
}

.pricing-trial__title {
  font-family: var(--heading);
  font-size: clamp(1.45rem, 3.2vw, 2rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  margin: 0 0 0.55rem;
  color: var(--text-h);
  line-height: 1.18;
}

.pricing-trial__lead {
  margin: 0;
  max-width: 36rem;
  font-size: 0.98rem;
  line-height: 1.6;
  color: var(--muted);
}

.pricing-trial__checks {
  list-style: none;
  padding: 0;
  margin: 1.05rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.pricing-trial__checks li {
  position: relative;
  padding-left: 1.4rem;
  font-size: 0.9rem;
  line-height: 1.45;
  color: color-mix(in srgb, var(--text) 88%, var(--muted));
}

.pricing-trial__checks li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.52em;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}

.pricing-trial__aside {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.35rem;
}

@media (min-width: 768px) {
  .pricing-trial__aside {
    align-items: flex-end;
    text-align: right;
    min-width: min(100%, 240px);
  }
}

.pricing-trial__cta {
  width: 100%;
  box-sizing: border-box;
}

@media (min-width: 768px) {
  .pricing-trial__cta {
    width: auto;
    min-width: 13.5rem;
  }
}

.pricing-trial__hint {
  margin: 0.65rem 0 0;
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--muted);
  max-width: 18rem;
}

@media (min-width: 768px) {
  .pricing-trial__hint {
    margin-left: auto;
  }
}

.pricing-plans-head {
  margin-bottom: clamp(1.5rem, 4vw, 2.25rem);
}

.pricing-trust-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.4rem 0.85rem;
  margin-top: 1.2rem;
  padding: 0.62rem 1.05rem;
  border-radius: var(--radius-pill);
  border: 1px solid color-mix(in srgb, var(--card-border) 92%, transparent);
  background: color-mix(in srgb, var(--surface-glass) 90%, transparent);
  font-size: 0.81rem;
  font-weight: 600;
  line-height: 1.35;
  color: color-mix(in srgb, var(--muted) 40%, var(--text-h));
  max-width: 46rem;
  margin-inline: auto;
}

.pricing-trust-strip__item {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  text-align: left;
}

.pricing-trust-strip__icon {
  flex-shrink: 0;
  color: var(--accent);
  opacity: 0.92;
}

.pricing-trust-strip__dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--muted);
  opacity: 0.4;
}

@media (max-width: 560px) {
  .pricing-trust-strip__dot {
    display: none;
  }
}

.pricing-plans-heading {
  font-family: var(--heading);
  font-size: clamp(1.55rem, 3.2vw, 2.15rem);
  font-weight: 800;
  color: var(--text-h);
  margin: 0 0 0.7rem;
  letter-spacing: -0.03em;
  line-height: 1.15;
}

.pricing-plans-lead {
  margin: 0 auto;
  max-width: 40rem;
  font-size: 1.02rem;
  line-height: 1.62;
  color: var(--muted);
}

.pricing-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.35rem;
  text-align: left;
}

@media (min-width: 768px) {
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
  padding: clamp(1.55rem, 3vw, 1.85rem) clamp(1.35rem, 3vw, 1.55rem)
    clamp(1.35rem, 3vw, 1.55rem);
  padding-top: 1.95rem;
  border-radius: calc(var(--radius-lg) + 6px);
  background: color-mix(in srgb, var(--surface-glass) 94%, transparent);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
  backdrop-filter: blur(14px);
  overflow: visible;
  transition:
    transform 0.22s ease,
    box-shadow 0.22s ease,
    border-color 0.22s ease;
}

.pricing-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-md);
  border-color: color-mix(in srgb, var(--accent-border) 42%, var(--card-border));
}

.pricing-card--popular {
  border-color: color-mix(in srgb, var(--accent-border) 75%, var(--card-border));
  background:
    linear-gradient(
      165deg,
      color-mix(in srgb, var(--accent) 14%, var(--surface-glass)) 0%,
      color-mix(in srgb, var(--surface-glass) 94%, transparent) 42%,
      color-mix(in srgb, var(--surface-glass) 96%, transparent) 100%
    );
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--accent) 28%, transparent),
    0 18px 40px color-mix(in srgb, var(--accent) 12%, transparent),
    var(--shadow-md);
}

@media (min-width: 768px) {
  .pricing-card--popular {
    transform: translateY(-8px);
  }

  .pricing-card--popular:hover {
    transform: translateY(-11px);
  }
}

.pricing-card__ribbon {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translate(-50%, -52%);
  z-index: 2;
  padding: 0.38rem 0.95rem;
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--on-accent);
  background: linear-gradient(
    125deg,
    var(--accent),
    color-mix(in srgb, var(--accent-muted) 92%, var(--accent))
  );
  border-radius: var(--radius-pill);
  box-shadow:
    0 6px 18px color-mix(in srgb, var(--accent) 38%, transparent),
    0 1px 0 color-mix(in srgb, #fff 12%, transparent);
  white-space: nowrap;
}

.pricing-card__header {
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 85%, transparent);
}

.pricing-card__name {
  font-family: var(--heading);
  margin: 0 0 0.4rem;
  font-size: 1.12rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text-h);
}

.pricing-card__tagline {
  margin: 0;
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--muted);
}

.pricing-card__metrics {
  margin-bottom: 1rem;
}

.pricing-card__monthly-big {
  margin-bottom: 0.75rem;
}

.pricing-card__monthly-num {
  font-family: var(--heading);
  font-size: clamp(2rem, 4vw, 2.45rem);
  font-weight: 800;
  letter-spacing: -0.04em;
  color: var(--accent);
  line-height: 1;
}

.pricing-card__monthly-unit {
  margin-left: 0.35rem;
  font-size: 0.92rem;
  font-weight: 700;
  color: color-mix(in srgb, var(--muted) 55%, var(--text-h));
}

.pricing-card__monthly-hint {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.74rem;
  font-weight: 600;
  color: var(--muted);
  line-height: 1.35;
}

.pricing-card__total-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.65rem;
}

.pricing-card__compare {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--muted);
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--muted) 65%, transparent);
}

.pricing-card__total-price {
  font-family: var(--mono);
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-h);
  letter-spacing: -0.02em;
}

.pricing-card__period-badge {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.22rem 0.5rem;
  border-radius: var(--radius-pill);
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  color: color-mix(in srgb, var(--muted) 55%, var(--text-h));
}

.pricing-card__save {
  margin: 0.55rem 0 0;
  font-size: 0.8rem;
  font-weight: 700;
  line-height: 1.4;
  color: color-mix(in srgb, var(--accent) 92%, var(--text-h));
}

.pricing-card__features {
  list-style: none;
  padding: 0;
  margin: 0 0 1.15rem;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.pricing-card__features li {
  position: relative;
  padding-left: 1.35rem;
  font-size: 0.84rem;
  line-height: 1.45;
  color: color-mix(in srgb, var(--text) 82%, var(--muted));
}

.pricing-card__features li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.48em;
  width: 6px;
  height: 6px;
  border-radius: 2px;
  background: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 20%, transparent);
}

.pricing-card__cta {
  margin-top: auto;
}

.pricing-card__btn {
  width: 100%;
  box-sizing: border-box;
}

.pricing-card--popular .pricing-card__btn.primary {
  box-shadow: 0 6px 18px color-mix(in srgb, var(--accent) 32%, transparent);
}

.pricing-footnote {
  margin: clamp(1.85rem, 4vw, 2.5rem) auto 0;
  max-width: 38rem;
  text-align: center;
  font-size: 0.87rem;
  line-height: 1.58;
  color: var(--muted);
}

.pricing-footnote__link {
  color: var(--accent);
  font-weight: 700;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}

.pricing-footnote__link:hover {
  color: var(--accent-hover);
}

/* ——— FAQ ——— */
.section-faq {
  background: var(--card-bg);
  border-block: 1px solid var(--card-border);
}

.faq-shell {
  max-width: 44rem;
  margin: 0 auto;
  padding: clamp(0.35rem, 1.5vw, 0.65rem);
  border-radius: calc(var(--radius-lg) + 6px);
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface-glass) 92%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(14px);
}

.faq-accordion {
  text-align: left;
}

.faq-item {
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 85%, transparent);
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
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1.15rem 1rem;
  background: none;
  border: none;
  font-family: var(--sans);
  font-size: 1.02rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--text-h);
  cursor: pointer;
  text-align: left;
  border-radius: var(--radius);
  transition:
    background 0.2s ease,
    color 0.2s ease;
}

.faq-question:hover {
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.faq-item.is-open .faq-question {
  color: var(--accent);
}

.faq-icon {
  flex-shrink: 0;
  color: var(--muted);
  transition:
    transform 0.25s ease,
    color 0.25s ease;
  display: flex;
  align-items: center;
}

.faq-item.is-open .faq-icon {
  transform: rotate(180deg);
  color: var(--accent);
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
  color: var(--muted);
  font-size: 0.96rem;
  line-height: 1.65;
  padding: 0 1rem;
}

.faq-item.is-open .faq-answer {
  padding-bottom: 1.15rem;
}

@media (prefers-reduced-motion: reduce) {
  .why-card,
  .hero__btn,
  .pricing-card,
  .chip,
  .cta {
    transition: none;
  }

  .why-card:hover,
  .hero__btn--primary:hover,
  .pricing-card:hover,
  .pricing-card--popular,
  .pricing-card--popular:hover,
  .cta.primary:hover,
  .cta--outline:hover {
    transform: none;
  }

  .faq-answer-wrapper {
    transition: none;
  }

  .faq-item.is-open .faq-answer-wrapper {
    grid-template-rows: 1fr;
  }

  .faq-item:not(.is-open) .faq-answer-wrapper {
    grid-template-rows: 0fr;
  }
}

/* ——— ФИНАЛЬНЫЙ CTA ——— */
.section-final {
  padding-bottom: clamp(4rem, 8vw, 6rem);
}

.section-inner--cta {
  max-width: 72rem;
  margin: 0 auto;
  padding-inline: 0;
}

.final-cta-card {
  position: relative;
  display: grid;
  gap: clamp(1.25rem, 3vw, 1.65rem);
  padding: clamp(1.45rem, 4vw, 2rem);
  border-radius: calc(var(--radius-lg) + 8px);
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface-glass) 95%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(16px);
  overflow: hidden;
  text-align: left;
}

@media (min-width: 768px) {
  .final-cta-card {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: clamp(1.75rem, 4vw, 2.5rem);
  }
}

.final-cta-card__accent {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 3px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--accent-muted) 55%, var(--accent)),
    var(--accent),
    color-mix(in srgb, #8b5cf6 45%, var(--accent))
  );
  opacity: 0.95;
}

.final-cta-card__main {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.final-cta-card__eyebrow {
  margin: 0 0 0.45rem;
  text-align: left;
}

.final-cta-card__title {
  font-family: var(--heading);
  font-size: clamp(1.38rem, 2.8vw, 1.85rem);
  font-weight: 800;
  letter-spacing: -0.028em;
  line-height: 1.22;
  margin: 0 0 0.55rem;
  color: var(--text-h);
}

.final-cta-card__lead {
  margin: 0;
  font-size: 0.96rem;
  line-height: 1.62;
  color: var(--muted);
  max-width: 40rem;
}

.final-cta-card__action {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  align-items: stretch;
}

@media (min-width: 768px) {
  .final-cta-card__action {
    align-items: flex-end;
  }
}

.final-cta-card__btn {
  box-sizing: border-box;
}

.final-cta-card__btn-secondary {
  box-sizing: border-box;
  font-size: 0.88rem;
  font-weight: 600;
  padding: 0.55rem 1rem;
}

@media (min-width: 768px) {
  .final-cta-card__btn,
  .final-cta-card__btn-secondary {
    width: auto;
    min-width: 12.5rem;
    justify-content: center;
  }
}

@media (max-width: 767px) {
  .final-cta-card__btn,
  .final-cta-card__btn-secondary {
    width: 100%;
  }
}

/* ——— FOOTER ——— */
.footer {
  background: color-mix(in srgb, var(--card-bg) 100%, transparent);
  border-top: 1px solid var(--card-border);
  padding: clamp(2.5rem, 5vw, 3.25rem) 1.25rem 1.5rem;
}

.footer-inner {
  max-width: 72rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 2rem;
  align-items: center;
  text-align: center;
}

@media (min-width: 768px) {
  .footer-inner {
    flex-direction: row;
    justify-content: space-between;
    align-items: flex-start;
    text-align: left;
  }
}

.footer-brand {
  max-width: 22rem;
}

.footer-logo {
  font-family: var(--heading);
  font-size: 1.22rem;
  font-weight: 800;
  color: var(--text-h);
  display: block;
  margin-bottom: 0.5rem;
}

.footer-desc {
  color: var(--muted);
  font-size: 0.92rem;
  line-height: 1.55;
  margin: 0;
}

.footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem 1.35rem;
  justify-content: center;
}

@media (min-width: 768px) {
  .footer-links {
    justify-content: flex-end;
  }
}

.footer-links a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.93rem;
  font-weight: 600;
  transition: color 0.2s ease;
}

.footer-links a:hover {
  color: var(--accent);
}

.footer-bottom {
  max-width: 72rem;
  margin: 2rem auto 0;
  padding-top: 1.5rem;
  border-top: 1px solid var(--card-border);
  text-align: center;
  font-size: 0.84rem;
  color: var(--muted);
}

@media (prefers-color-scheme: light) {
  .how-panel__tag--direct {
    color: var(--accent-muted);
  }

  .chip--direct {
    border-color: color-mix(in srgb, var(--accent-muted) 35%, var(--card-border));
    background: color-mix(in srgb, var(--accent-soft) 55%, var(--surface));
  }
}
</style>
