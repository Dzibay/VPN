<script setup>
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import CookieConsentBanner from './components/CookieConsentBanner.vue'

const route = useRoute()
const showChrome = computed(() => !route.meta?.minimalChrome)
</script>

<template>
  <div class="app">
    <AppHeader v-if="showChrome" />
    <main class="main">
      <RouterView />
    </main>
    <CookieConsentBanner v-if="showChrome" />
  </div>
</template>

<style scoped>
.app {
  min-height: 100dvh;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* Иначе широкий контент (грид, длинные строки) раздувает main и даёт горизонтальный скролл на телефоне */
  min-width: 0;
  padding: 0;
  width: 100%;
}
</style>
