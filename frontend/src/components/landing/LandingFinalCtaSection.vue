<script setup>
import { useLandingPageContext } from '../../composables/useLandingPage.js'
import { RouterLink } from 'vue-router'

const {
  HOME_IMAGES,
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
              {{ landingCopy.finalTitle }}
            </h2>
            <p class="final-cta-card__lead">
              {{ landingCopy.finalLead }}
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

</template>
