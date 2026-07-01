<script setup>
import LandingWhySection from './LandingWhySection.vue'
import LandingHowSection from './LandingHowSection.vue'
import LandingTrialSection from './LandingTrialSection.vue'
import LandingPricingSection from './LandingPricingSection.vue'
import LandingFaqSection from './LandingFaqSection.vue'
import LandingFinalCtaSection from './LandingFinalCtaSection.vue'
</script>

<template>
  <LandingWhySection />
  <LandingHowSection />
  <LandingTrialSection />
  <LandingPricingSection />
  <LandingFaqSection />
  <LandingFinalCtaSection />
  <slot />
</template>
