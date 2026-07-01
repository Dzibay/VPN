<script setup>
import { computed } from 'vue'
import {
  Globe,
  Lock,
  Star,
  Zap,
} from 'lucide-vue-next'
import AppActionButton from '../AppActionButton.vue'
import { useLandingPageContext } from '../../composables/useLandingPage.js'

const ICONS = { Globe, Lock, Zap }

const props = defineProps({
  /** @type {import('vue').PropType<{
   *   badgeIcon?: string,
   *   badgeText: string,
   *   titleLine1: string,
   *   titleHighlight: string,
   *   titleLine2: string,
   *   lead: string,
   *   bgImage: string,
   *   features: Array<{ icon: string, title: string, text: string }>,
   * }>} */
  hero: {
    type: Object,
    required: true,
  },
})

const {
  HOME_IMAGES,
  ArrowRight,
  isLoggedIn,
  loggedInHomeCtaPath,
} = useLandingPageContext()

const featureItems = computed(() =>
  (props.hero.features ?? []).map((item) => ({
    ...item,
    icon: ICONS[item.icon] ?? Globe,
  })),
)
</script>

<template>
  <section
    id="hero"
    class="hero hero--landing hero--seo"
    aria-labelledby="hero-title"
  >
    <div class="hero__inner hero__inner--seo">
      <div
        class="hero__bg hero__bg--seo"
        aria-hidden="true"
      >
        <img
          class="hero__bg-seo"
          :src="hero.bgImage"
          alt=""
          width="1536"
          height="1024"
          decoding="async"
          fetchpriority="high"
          @error="($event.target).style.display = 'none'"
        />
      </div>

      <div class="hero__container hero__container--seo">
        <div class="hero__content">
          <div class="hero__badge hero__badge--seo">
          <img
            v-if="hero.badgeIcon"
            class="hero__badge-icon"
            :src="hero.badgeIcon"
            alt=""
            width="20"
            height="20"
            decoding="async"
          />
          {{ hero.badgeText }}
        </div>

        <h1
          id="hero-title"
          class="hero__title hero__title--seo"
          :style="hero.accentColor ? { '--seo-accent-color': hero.accentColor } : undefined"
        >
          {{ hero.titleLine1 }}
          <span class="hero__title-brand">{{ hero.titleHighlight }}</span>
          <br />
          <span class="hero__title-underline">{{ hero.titleLine2 }}</span>
        </h1>

        <p class="hero__lead">
          {{ hero.lead }}
        </p>

        <ul
          class="hero__features"
          role="list"
        >
          <li
            v-for="(item, i) in featureItems"
            :key="i"
            class="hero__feature"
          >
            <span
              class="hero__feature-ico"
              aria-hidden="true"
            >
              <component
                :is="item.icon"
                :size="22"
                :stroke-width="2"
              />
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
                <ArrowRight
                  :size="20"
                  :stroke-width="2"
                  aria-hidden="true"
                />
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
                <ArrowRight
                  :size="20"
                  :stroke-width="2"
                  aria-hidden="true"
                />
              </template>
            </AppActionButton>
            <a
              class="btn-secondary hero__cta-alt"
              href="#pricing"
            >
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
            <div
              class="hero__social-fallback"
              aria-hidden="true"
            >
              <span /><span /><span /><span />
            </div>
          </div>
          <div class="hero__social-copy">
            <p class="hero__social-count">
              10 000+ пользователей доверяют нам
            </p>
            <p class="hero__social-rating">
              <span
                class="hero__stars"
                aria-hidden="true"
              >
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
      </div>
    </div>
  </section>
</template>
