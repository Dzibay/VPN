<script setup>
import { provideLandingPage } from '../composables/useLandingPage.js'
import HomeHeroSection from '../components/landing/HomeHeroSection.vue'
import LandingPageMain from '../components/landing/LandingPageMain.vue'
import LandingFooter from '../components/landing/LandingFooter.vue'

provideLandingPage()
</script>

<template>
  <div class="home">
    <main id="main-content">
      <HomeHeroSection />
      <LandingPageMain />
    </main>
    <LandingFooter />
  </div>
</template>

<style src="../styles/landing-page.css"></style>
