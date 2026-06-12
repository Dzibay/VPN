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

</template>
