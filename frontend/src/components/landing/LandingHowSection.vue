<script setup>
import { useLandingPageContext } from '../../composables/useLandingPage.js'

const {
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
} = useLandingPageContext()

</script>

<template>
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

</template>
