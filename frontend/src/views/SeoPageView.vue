<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { provideLandingPage } from '../composables/useLandingPage.js'
import { getSeoPageByPath } from '../content/seo/index.js'
import { getSeoPageContent } from '../content/seo/getSeoPageContent.js'
import SeoHeroSection from '../components/landing/SeoHeroSection.vue'
import LandingPageMain from '../components/landing/LandingPageMain.vue'
import SeoArticleSection from '../components/landing/SeoArticleSection.vue'
import LandingFooter from '../components/landing/LandingFooter.vue'

const route = useRoute()
provideLandingPage()

const pageMeta = computed(() =>
  getSeoPageByPath(
    typeof route.meta.seoPath === 'string' ? route.meta.seoPath : route.path,
  ),
)

const content = computed(() =>
  getSeoPageContent(
    typeof route.meta.seoPath === 'string' ? route.meta.seoPath : route.path,
  ),
)

const pageTitle = computed(
  () => content.value?.meta?.title ?? pageMeta.value?.title ?? 'Подорожник VPN',
)

function applyDocumentMeta() {
  if (typeof document === 'undefined') return
  document.title = pageTitle.value
  const desc = content.value?.meta?.description
  if (!desc) return
  let el = document.querySelector('meta[name="description"]')
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', 'description')
    document.head.appendChild(el)
  }
  el.setAttribute('content', desc)
}

onMounted(applyDocumentMeta)
watch(pageTitle, applyDocumentMeta)

onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.title = 'Подорожник VPN — умный split tunneling и VLESS | не нужно выключать'
})
</script>

<template>
  <div
    v-if="content?.hero"
    class="home"
  >
    <main id="main-content">
      <SeoHeroSection :hero="content.hero" />
      <LandingPageMain>
        <SeoArticleSection
          v-if="content.article"
          :article="content.article"
        />
      </LandingPageMain>
    </main>
    <LandingFooter />
  </div>
  <div
    v-else
    class="home"
  >
    <main
      id="main-content"
      class="section"
    >
      <div class="section-inner">
        <p>Контент страницы «{{ pageMeta?.title }}» скоро появится.</p>
      </div>
    </main>
  </div>
</template>

<style src="../styles/landing-page.css"></style>
