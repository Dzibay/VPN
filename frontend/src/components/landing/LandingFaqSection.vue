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

</template>
