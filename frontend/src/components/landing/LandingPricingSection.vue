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

</template>
