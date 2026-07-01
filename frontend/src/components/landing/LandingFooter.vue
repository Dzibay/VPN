<script setup>
import { useLandingPageContext } from '../../composables/useLandingPage.js'

const {
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
  footerSeoLinks,
  finalCtaFeatures,
  finalVisualPins,
  isLoggedIn,
  loggedInHomeCtaPath,
} = useLandingPageContext()

</script>

<template>
    <!-- FOOTER -->
    <footer
      class="footer"
      role="contentinfo"
    >
      <div class="footer-shell">
        <div class="footer-top">
          <div class="footer-brand">
            <picture v-if="!isHalyalBrand" class="footer-brand__logo">
              <source
                :srcset="HOME_IMAGES.logoWordmarkDark"
                media="(prefers-color-scheme: dark)"
              />
              <img
                :src="HOME_IMAGES.logoWordmark"
                width="220"
                height="48"
                :alt="brandName"
                decoding="async"
              />
            </picture>
            <div v-else class="footer-brand__logo footer-brand__logo--text">
              {{ brandName }}
            </div>
            <p class="footer-brand__desc">
              {{ landingCopy.footerDesc }}
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
            v-if="!isHalyalBrand"
            class="footer-col"
            aria-label="Сервисы"
          >
            <h3 class="footer-col__title">
              <span class="footer-col__dot" aria-hidden="true" />
              Сервисы
            </h3>
            <ul class="footer-col__list">
              <li
                v-for="link in footerSeoLinks"
                :key="link.to"
              >
                <RouterLink :to="link.to">{{ link.label }}</RouterLink>
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
            {{ landingCopy.footerCopyright }}
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
</template>
