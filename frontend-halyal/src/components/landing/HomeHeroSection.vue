<script setup>
import { ArrowRight, CheckCircle2, Globe, HeartHandshake, Lock, Zap } from 'lucide-vue-next'
import { useLandingPageContext } from '../../composables/useLandingPage.js'
import AppActionButton from '../AppActionButton.vue'

const {
  HOME_IMAGES,
  landingCopy,
  heroMiniFeatures,
  heroTags,
  isLoggedIn,
  loggedInHomeCtaPath,
} = useLandingPageContext()

const featureIcons = [Lock, Globe, Zap]
</script>

<template>
  <section id="hero" class="hero hero--halyal" aria-labelledby="hero-title">
    <div class="hero__bg" aria-hidden="true">
      <img
        class="hero__bg-photo"
        :src="HOME_IMAGES.heroBg"
        alt=""
        width="1920"
        height="1080"
        decoding="async"
        fetchpriority="high"
      />
      <div class="hero__bg-gradient" />
    </div>

    <div class="hero__container">
      <div class="hero__content">
        <ul class="hero__tags" role="list">
          <li v-for="tag in heroTags" :key="tag" class="hero__tag">
            <CheckCircle2 :size="14" :stroke-width="2.5" aria-hidden="true" />
            {{ tag }}
          </li>
        </ul>

        <h1 id="hero-title" class="hero__title">
          VPN для
          <span class="hero__title-accent">спокойного</span>
          доступа к
          <span class="hero__title-accent">нужным</span>
          сервисам
        </h1>

        <p class="hero__lead">
          {{ landingCopy.heroLead }}
        </p>

        <ul class="hero__features" role="list">
          <li
            v-for="(item, i) in heroMiniFeatures"
            :key="i"
            class="hero__feature-card"
          >
            <span class="hero__feature-ico" aria-hidden="true">
              <component :is="featureIcons[i]" :size="20" :stroke-width="2" />
            </span>
            <span class="hero__feature-text">
              <strong>{{ item.title }}</strong>
              <span>{{ item.text }}</span>
            </span>
          </li>
        </ul>

        <div class="hero__cta">
          <AppActionButton
            variant="primary"
            large
            elevate-on-hover
            class="hero__cta-btn"
            :to="isLoggedIn ? loggedInHomeCtaPath : '/register'"
          >
            Перейти в кабинет
            <template #icon>
              <ArrowRight :size="20" :stroke-width="2" aria-hidden="true" />
            </template>
          </AppActionButton>
        </div>

        <p class="hero__charity">
          <HeartHandshake :size="18" :stroke-width="2" aria-hidden="true" />
          <span>{{ landingCopy.heroCharityNote }}</span>
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero--halyal {
  position: relative;
  min-height: clamp(32rem, 88vh, 52rem);
  display: flex;
  align-items: center;
  padding: clamp(2rem, 5vw, 4rem) clamp(1rem, 4vw, 2.5rem);
  overflow: hidden;
  color: var(--landing-text);
}

.hero__bg {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 0;
}

.hero__bg-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center right;
}

.hero__bg-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(247, 243, 238, 0.97) 0%,
    rgba(247, 243, 238, 0.92) 42%,
    rgba(247, 243, 238, 0.55) 62%,
    rgba(247, 243, 238, 0.15) 100%
  );
}

.hero__container {
  position: relative;
  z-index: 1;
  width: min(84rem, 100%);
  margin: 0 auto;
}

.hero__content {
  max-width: 38rem;
}

.hero__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0 0 1.25rem;
  padding: 0;
  list-style: none;
}

.hero__tag {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--halyal-green);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(27, 67, 50, 0.12);
  box-shadow: 0 1px 4px rgba(27, 67, 50, 0.06);
}

.hero__title {
  margin: 0 0 1rem;
  font-family: var(--heading);
  font-size: clamp(1.85rem, 4.2vw, 2.75rem);
  font-weight: 800;
  line-height: 1.15;
  letter-spacing: -0.03em;
  color: var(--landing-text);
}

.hero__title-accent {
  color: var(--halyal-gold);
}

.hero__lead {
  margin: 0 0 1.5rem;
  font-size: clamp(0.95rem, 1.8vw, 1.05rem);
  line-height: 1.65;
  color: var(--landing-muted);
  max-width: 34rem;
}

.hero__features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0 0 1.75rem;
  padding: 0;
  list-style: none;
}

.hero__feature-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.85rem 0.75rem;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(27, 67, 50, 0.1);
  box-shadow: 0 2px 8px rgba(27, 67, 50, 0.06);
  backdrop-filter: blur(6px);
}

.hero__feature-ico {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 10px;
  color: var(--halyal-green);
  background: var(--halyal-gold-soft);
}

.hero__feature-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--landing-muted);
}

.hero__feature-text strong {
  font-size: 0.78rem;
  color: var(--landing-text);
}

.hero__cta {
  margin-bottom: 1.25rem;
}

.hero__cta-btn {
  --accent: var(--halyal-green);
  --accent-hover: var(--halyal-green-hover);
  --on-accent: #ffffff;
}

.hero__charity {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0;
  max-width: 28rem;
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--landing-muted);
}

.hero__charity svg {
  flex-shrink: 0;
  margin-top: 0.1rem;
  color: var(--halyal-gold);
}

@media (max-width: 768px) {
  .hero--halyal {
    min-height: auto;
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
  }

  .hero__bg-photo {
    object-position: 70% center;
  }

  .hero__bg-gradient {
    background: linear-gradient(
      180deg,
      rgba(247, 243, 238, 0.96) 0%,
      rgba(247, 243, 238, 0.88) 55%,
      rgba(247, 243, 238, 0.72) 100%
    );
  }

  .hero__features {
    grid-template-columns: 1fr;
  }
}
</style>
