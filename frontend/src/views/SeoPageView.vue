<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { provideLandingPage } from '../composables/useLandingPage.js'
import { getSeoPageByPath } from '../content/seo/index.js'
import { getSeoPageContent } from '../content/seo/getSeoPageContent.js'
import {
  applyDefaultDocumentMeta,
  applyDocumentMeta,
  buildPageMeta,
  resolvePublicSiteUrl,
} from '../seo/documentMeta.js'
import SeoHeroSection from '../components/landing/SeoHeroSection.vue'
import LandingPageMain from '../components/landing/LandingPageMain.vue'
import SeoArticleSection from '../components/landing/SeoArticleSection.vue'
import LandingFooter from '../components/landing/LandingFooter.vue'

const route = useRoute()
provideLandingPage()

const seoPath = computed(() =>
  typeof route.meta.seoPath === 'string' ? route.meta.seoPath : route.path,
)

const pageMeta = computed(() => getSeoPageByPath(seoPath.value))

const content = computed(() => getSeoPageContent(seoPath.value))

const documentMeta = computed(() =>
  buildPageMeta(resolvePublicSiteUrl(), seoPath.value, content.value),
)

function syncDocumentMeta() {
  applyDocumentMeta(documentMeta.value)
}

onMounted(syncDocumentMeta)
watch(documentMeta, syncDocumentMeta, { deep: true })

onBeforeUnmount(() => {
  applyDefaultDocumentMeta(resolvePublicSiteUrl())
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
