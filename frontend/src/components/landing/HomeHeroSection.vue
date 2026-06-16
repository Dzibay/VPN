<script setup>
import { useLandingPageContext } from '../../composables/useLandingPage.js'
import AppActionButton from '../AppActionButton.vue'

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
            YouTube, ChatGPT и зарубежные<br />
            сервисы — через VPN
          </h1>

          <p class="hero__lead">
            Российские сервисы работают без постоянного переключения, а
            зарубежные — через защищённый канал.
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

</template>
