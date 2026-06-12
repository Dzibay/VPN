<script setup>
import { useLandingPageContext } from '../../composables/useLandingPage.js'
import { RouterLink } from 'vue-router'

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

</template>
