<script setup>
import { computed, onMounted, ref } from 'vue'
import { Headphones, ShieldBan } from 'lucide-vue-next'
import SitePageLayout from '../components/SitePageLayout.vue'
import { fetchJson } from '../api/client.js'
import { SUPPORT_TELEGRAM } from '../content/legal.js'

const BLOCKED_IMAGE_SRC = '/images/blocked/blocked.png'

/** @type {import('vue').Ref<{ support_telegram_url?: string | null } | null>} */
const siteLinks = ref(null)
const imageOk = ref(true)

function telegramUrlFromHandle(handle) {
  const user = String(handle || '').trim().replace(/^@/, '')
  return user ? `https://t.me/${user}` : null
}

const supportUrl = computed(() => {
  const fromApi = siteLinks.value?.support_telegram_url
  if (typeof fromApi === 'string' && fromApi.trim()) return fromApi.trim()
  return telegramUrlFromHandle(SUPPORT_TELEGRAM)
})

const supportLabel = computed(() => {
  const url = supportUrl.value
  if (!url) return SUPPORT_TELEGRAM
  const m = url.match(/t\.me\/([^/?#]+)/i)
  return m?.[1] ? `@${m[1]}` : SUPPORT_TELEGRAM
})

onMounted(async () => {
  try {
    siteLinks.value = await fetchJson('/api/public/site-links')
  } catch {
    siteLinks.value = null
  }
})
</script>

<template>
  <SitePageLayout as="main" class="blocked-page">
    <article class="blocked-card glass">
      <div class="blocked-visual" aria-hidden="true">
        <img
          v-if="imageOk"
          class="blocked-image"
          :src="BLOCKED_IMAGE_SRC"
          alt=""
          @error="imageOk = false"
        />
        <div v-else class="blocked-image-fallback">
          <ShieldBan :size="56" stroke-width="1.35" />
        </div>
      </div>

      <h1 class="blocked-title">Доступ ограничен</h1>

      <p class="blocked-lead">
        Сейчас вы не можете пользоваться сервисом.
        Если нужна помощь — напишите в поддержку в Telegram:
        <a
          v-if="supportUrl"
          class="blocked-support-link"
          :href="supportUrl"
          target="_blank"
          rel="noopener noreferrer"
        >{{ supportLabel }}</a><template v-else>{{ supportLabel }}</template>.
      </p>

      <div v-if="supportUrl" class="blocked-actions">
        <a
          class="btn-primary blocked-support-btn"
          :href="supportUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          <Headphones :size="18" aria-hidden="true" />
          Написать в поддержку
        </a>
      </div>
    </article>
  </SitePageLayout>
</template>

<style scoped>
.blocked-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem 3rem;
}

.blocked-page :deep(.site-page-layout__inner) {
  max-width: min(28rem, 100%);
}

.blocked-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1rem;
  padding: 1.75rem 1.35rem 1.5rem;
  border-radius: 18px;
}

.blocked-visual {
  width: 100%;
  display: flex;
  justify-content: center;
}

.blocked-image {
  display: block;
  width: min(100%, 18rem);
  height: auto;
  max-height: 14rem;
  object-fit: contain;
  border-radius: 12px;
}

.blocked-image-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 7.5rem;
  height: 7.5rem;
  border-radius: 999px;
  background: rgba(248, 113, 113, 0.1);
  color: var(--danger, #dc2626);
}

.blocked-title {
  margin: 0;
  font-size: clamp(1.35rem, 4vw, 1.65rem);
  line-height: 1.2;
  color: var(--text-h);
}

.blocked-lead {
  margin: 0;
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--muted);
}

.blocked-actions {
  width: 100%;
  margin-top: 0.35rem;
}

.blocked-support-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  width: 100%;
  text-decoration: none;
}

.blocked-support-link {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.blocked-support-link:hover {
  text-decoration: underline;
}
</style>
