<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppActionButton from '../components/AppActionButton.vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import { fetchJson, subscriptionPublicUrl } from '../api/client.js'
import {
  forcedStoreRefs,
  getMobileStoreRedirectUrl,
  isMobileAppStoreDevice,
  pickStoreRefsAuto,
} from '../util/subscriptionOpenStores.js'

const route = useRoute()
const router = useRouter()

const token = computed(() => String(route.params.token ?? ''))
const client = computed(() => String(route.params.client ?? ''))

/** Ответ GET …/data (после успешного запроса). */
const page = ref(null)
/** Параллельно: публичное описание клиента — имя и магазины до ответа /data. */
const publicInfo = ref(null)
const localSubError = ref(null)

const openPageStoreLinks = ref(null)

/** @type {import('vue').Ref<{ site?: string | null, download?: string | null } | null>} */
const storeRef = ref(null)

const platformFromQuery = computed(() => {
  const p = route.query.platform
  return typeof p === 'string' ? p : null
})

function applyStoreLinks(links, forcedPlatform) {
  if (!links || typeof links !== 'object') {
    storeRef.value = null
    return
  }
  const fp =
    forcedPlatform &&
    typeof forcedPlatform === 'string' &&
    ['windows', 'android', 'ios', 'macos', 'linux'].includes(forcedPlatform)
      ? forcedPlatform
      : null
  storeRef.value = fp
    ? forcedStoreRefs(links, fp)
    : pickStoreRefsAuto(links)
}

function buildDataPath() {
  const t = encodeURIComponent(token.value)
  const c = encodeURIComponent(client.value)
  let path = `/sub/${t}/open/${c}/data`
  const q = platformFromQuery.value
  if (
    q &&
    ['windows', 'android', 'ios', 'macos', 'linux'].includes(q.toLowerCase())
  ) {
    path += `?platform=${encodeURIComponent(q)}`
  }
  return path
}

const displayTitle = computed(() => {
  const p = page.value
  const pub = publicInfo.value
  return (
    (p && typeof p.display_name === 'string' && p.display_name)
    || (pub && typeof pub.display_name === 'string' && pub.display_name)
    || (p && typeof p.headline === 'string' && p.headline)
    || client.value
  )
})

const routeBanner = computed(() => {
  if (localSubError.value === 'load_failed') {
    return {
      kind: 'danger',
      text:
        'Не удалось проверить ссылку настройки. Попробуйте обновить страницу или установить приложение вручную.',
    }
  }
  if (page.value?.state === 'invalid_token') {
    return {
      kind: 'danger',
      text:
        page.value.message
        || 'Ссылка устарела или недействительна. Получите новую ссылку в Telegram-боте.',
    }
  }
  return null
})

const showStoreRow = computed(() => {
  const R = storeRef.value
  return !!(R && (R.site || R.download))
})

const storeRowSingle = computed(() => {
  const R = storeRef.value
  if (!R) return true
  const n = (R.download ? 1 : 0) + (R.site ? 1 : 0)
  return n <= 1
})

const openInClientLabel = computed(() => {
  const p = page.value
  if (!p || typeof p.open_button_label !== 'string' || !p.open_button_label) {
    return 'Подключить автоматически'
  }
  return p.open_button_label
})

const subscriptionUrl = computed(() => {
  const fromPage = page.value?.subscription_url
  if (typeof fromPage === 'string' && fromPage) return fromPage
  return token.value ? subscriptionPublicUrl(token.value) : ''
})

const subscriptionCopied = ref(false)
let subscriptionCopiedTimer = null

async function copySubscriptionUrl() {
  const url = subscriptionUrl.value
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    subscriptionCopied.value = true
    if (subscriptionCopiedTimer) clearTimeout(subscriptionCopiedTimer)
    subscriptionCopiedTimer = setTimeout(() => {
      subscriptionCopied.value = false
      subscriptionCopiedTimer = null
    }, 2000)
  } catch {
    /* ignore */
  }
}

const OPEN_MOBILE_STORE_FALLBACK_MS = 1000

let loadGeneration = 0
let openTimer = null
let deeplinkIframe = null
let cancelMobileFallbackWatchers = null

function removeDeeplinkIframe() {
  if (deeplinkIframe?.parentNode) {
    deeplinkIframe.parentNode.removeChild(deeplinkIframe)
  }
  deeplinkIframe = null
}

function clearOpenTimer() {
  if (openTimer) {
    clearTimeout(openTimer)
    openTimer = null
  }
}

function clearMobileFallbackWatchers() {
  if (cancelMobileFallbackWatchers) {
    cancelMobileFallbackWatchers()
    cancelMobileFallbackWatchers = null
  }
}

function armMobileFallbackWatchers() {
  clearMobileFallbackWatchers()
  const onBecameBackground = () => {
    if (typeof document === 'undefined') return
    if (document.visibilityState === 'visible') return
    clearOpenTimer()
    clearMobileFallbackWatchers()
  }
  document.addEventListener('visibilitychange', onBecameBackground)
  window.addEventListener('pagehide', onBecameBackground)
  cancelMobileFallbackWatchers = () => {
    document.removeEventListener('visibilitychange', onBecameBackground)
    window.removeEventListener('pagehide', onBecameBackground)
  }
}

function scheduleMobileStoreFallback() {
  if (!isMobileAppStoreDevice()) return
  clearOpenTimer()
  clearMobileFallbackWatchers()
  armMobileFallbackWatchers()
  openTimer = setTimeout(() => {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') {
      clearMobileFallbackWatchers()
      return
    }
    clearMobileFallbackWatchers()
    removeDeeplinkIframe()
    const storeUrl = getMobileStoreRedirectUrl(
      openPageStoreLinks.value,
      platformFromQuery.value,
    )
    if (storeUrl) {
      try {
        window.location.replace(storeUrl)
      } catch {
        /* ignore */
      }
    }
  }, OPEN_MOBILE_STORE_FALLBACK_MS)
}

function invokeDeeplink(url) {
  removeDeeplinkIframe()
  const u = String(url)
  if (isMobileAppStoreDevice()) {
    try {
      window.location.replace(u)
    } catch {
      /* ignore */
    }
    scheduleMobileStoreFallback()
    return
  }
  deeplinkIframe = document.createElement('iframe')
  deeplinkIframe.setAttribute(
    'style',
    'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;border:none;left:-9999px;top:0',
  )
  deeplinkIframe.setAttribute('aria-hidden', 'true')
  document.body.appendChild(deeplinkIframe)
  try {
    deeplinkIframe.src = u
  } catch {
    try {
      deeplinkIframe.contentWindow.location.href = u
    } catch {
      /* ignore */
    }
  }
}

function retryOpenInClient() {
  const d = page.value?.deeplink
  if (!d || typeof d !== 'string') return
  openPageStoreLinks.value = page.value?.store_links ?? null
  removeDeeplinkIframe()
  if (isMobileAppStoreDevice()) {
    try {
      window.location.replace(String(d))
    } catch {
      /* ignore */
    }
    scheduleMobileStoreFallback()
    return
  }
  invokeDeeplink(String(d))
}

function mergeStoreLinks() {
  const p = page.value
  const pub = publicInfo.value
  const links = p?.store_links ?? pub?.store_links ?? null
  applyStoreLinks(links, platformFromQuery.value)
}

async function load() {
  const gen = ++loadGeneration
  page.value = null
  publicInfo.value = null
  localSubError.value = null
  storeRef.value = null
  openPageStoreLinks.value = null
  clearOpenTimer()
  clearMobileFallbackWatchers()
  removeDeeplinkIframe()

  if (!token.value || !client.value) {
    localSubError.value = 'load_failed'
    return
  }

  const pubUrl = `/api/public/client-apps/${encodeURIComponent(client.value)}`
  const pubPromise = fetchJson(pubUrl)
    .then((info) => {
      if (gen !== loadGeneration) return
      publicInfo.value = info
      mergeStoreLinks()
    })
    .catch(() => {})

  try {
    const data = await fetchJson(buildDataPath())
    if (gen !== loadGeneration) return
    await pubPromise.catch(() => {})
    if (gen !== loadGeneration) return
    page.value = data
    mergeStoreLinks()

    if (typeof data.title === 'string') document.title = data.title

    if (data.state === 'invalid_token') {
      return
    }

    if (data.state === 'ok' && data.deeplink) {
      openPageStoreLinks.value = data.store_links ?? null
      await nextTick()
      if (gen !== loadGeneration) return
      invokeDeeplink(String(data.deeplink))
    }
  } catch (e) {
    await pubPromise.catch(() => {})
    if (gen !== loadGeneration) return
    if (e?.status === 404) {
      router.replace({ path: '/cabinet', query: { unknown_client: '1' } })
      return
    }
    localSubError.value = 'load_failed'
    const pub = publicInfo.value
    if (pub) {
      page.value = {
        state: 'error',
        display_name: pub.display_name,
        store_links: pub.store_links,
        title: `${pub.display_name} — Подорожник VPN`,
        deeplink: null,
        lead: null,
      }
      mergeStoreLinks()
      document.title = `${pub.display_name} — Подорожник VPN`
    } else {
      page.value = null
    }
  }
}

watch(
  () => [route.params.token, route.params.client, route.query.platform],
  () => {
    load()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clearOpenTimer()
  clearMobileFallbackWatchers()
  removeDeeplinkIframe()
  if (subscriptionCopiedTimer) {
    clearTimeout(subscriptionCopiedTimer)
    subscriptionCopiedTimer = null
  }
})
</script>

<template>
  <div
    v-if="token && client"
    class="app-dl"
  >
    <div class="app-dl-wrap">
      <CabinetBackLink to="/cabinet" />

      <div class="app-dl-card">
        <template v-if="localSubError && !page">
          <h1 class="app-dl-h1">
            Не удалось загрузить данные
          </h1>
          <p
            v-if="routeBanner"
            class="app-dl-banner app-dl-banner--danger"
            role="status"
          >
            {{ routeBanner.text }}
          </p>
        </template>
        
        <template v-else>
          <div
            v-if="routeBanner"
            class="app-dl-banner"
            :class="
              routeBanner.kind === 'info'
                ? 'app-dl-banner--info'
                : 'app-dl-banner--danger'
            "
            role="status"
          >
            {{ routeBanner.text }}
          </div>
          
          <h1 class="app-dl-h1">
            {{ displayTitle }}
          </h1>
          
          <p class="app-dl-lead">
            Мы пытаемся запустить приложение для автоматической настройки. Если ничего не произошло, выполните два простых шага:
          </p>

          <div class="app-dl-steps">
            <div class="app-dl-step">
              <div class="app-dl-step-number">1</div>
              <div class="app-dl-step-content">
                <p class="app-dl-step-text">
                  Скачайте и установите приложение на ваше устройство:
                </p>
                
                <div
                  v-if="showStoreRow"
                  class="app-dl-actions"
                >
                  <div
                    class="app-dl-actions-row"
                    :class="{ 'app-dl-actions-row--single': storeRowSingle }"
                  >
                    <AppActionButton
                      v-if="storeRef?.download"
                      variant="primary"
                      block
                      :href="storeRef.download"
                    >
                      Скачать программу
                    </AppActionButton>
                    <AppActionButton
                      v-if="storeRef?.site"
                      variant="secondary"
                      block
                      :href="storeRef.site"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Официальный сайт
                    </AppActionButton>
                  </div>
                </div>
                <p
                  v-else
                  class="app-dl-muted"
                >
                  Для вашей платформы нет прямой ссылки. Пожалуйста, откройте сайт разработчика вручную.
                </p>
              </div>
            </div>

            <div
              v-if="page?.deeplink && page.state === 'ok'"
              class="app-dl-step"
            >
              <div class="app-dl-step-number">2</div>
              <div class="app-dl-step-content">
                <p class="app-dl-step-text">
                  Откройте установленное приложение, вернитесь на этот экран и нажмите кнопку ниже для мгновенной настройки сети:
                </p>
                <AppActionButton
                  variant="primary"
                  block
                  class="app-dl-open-full"
                  @click="retryOpenInClient"
                >
                  {{ openInClientLabel }}
                </AppActionButton>
              </div>
            </div>
          </div>

          <div
            v-if="page?.state === 'ok' && subscriptionUrl"
            class="app-dl-fallback"
          >
            <h2 class="app-dl-fallback-title">
              Приложение не открылось?
            </h2>
            <p class="app-dl-fallback-text">
              Скопируйте ссылку подписки и вставьте её в {{ displayTitle }} вручную:
              в приложении откройте раздел добавления подписки по ссылке и вставьте скопированный адрес.
            </p>
            <AppActionButton
              variant="secondary"
              block
              @click="copySubscriptionUrl"
            >
              {{ subscriptionCopied ? 'Скопировано' : 'Скопировать ссылку подписки' }}
            </AppActionButton>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-dl {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  font: inherit;
  color: var(--text);
  background: var(--bg-gradient);
}

.app-dl-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: min(var(--page-content-max, 25rem), 100%);
  min-width: 0;
  margin-inline: auto;
  padding: 1.5rem max(1rem, env(safe-area-inset-left, 0px)) 2.5rem
    max(1rem, env(safe-area-inset-right, 0px));
  box-sizing: border-box;
  gap: 0.75rem;
}

.app-dl-card {
  width: 100%;
  max-width: 100%;
  padding: 1.35rem 1.25rem 1.5rem;
  border-radius: var(--radius-lg);
  background: var(--surface-glass);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-md);
  box-sizing: border-box;
}

.app-dl-banner {
  margin: 0 0 1rem;
  padding: 0.65rem 0.75rem;
  border-radius: var(--radius);
  font-size: 0.9rem;
  line-height: 1.45;
}

.app-dl-banner--danger {
  background: var(--danger-soft);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: var(--danger);
}

.app-dl-banner--info {
  background: var(--accent-soft, rgba(59, 130, 246, 0.12));
  border: 1px solid rgba(59, 130, 246, 0.28);
  color: var(--muted);
}

.app-dl-h1 {
  margin: 0 0 0.75rem;
  font-family: var(--heading);
  font-size: 1.35rem;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.25;
}

.app-dl-lead {
  margin: 0 0 1.25rem;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.5;
}

/* Стилизация пошаговой инструкции */
.app-dl-steps {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-bottom: 0.5rem;
}

.app-dl-step {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
}

.app-dl-step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 50%;
  background: var(--accent-soft, rgba(59, 130, 246, 0.1));
  color: var(--text-h);
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
  border: 1px solid var(--card-border);
}

.app-dl-step-content {
  flex: 1;
  min-width: 0;
}

.app-dl-step-text {
  margin: 0 0 0.65rem;
  font-size: 0.92rem;
  line-height: 1.45;
  color: var(--text);
}

.app-dl-open-full {
  margin-top: 0.25rem;
}

.app-dl-muted {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}

.app-dl-actions-row {
  display: flex;
  flex-direction: row;
  gap: 0.6rem;
  width: 100%;
  flex-wrap: nowrap;
}

.app-dl-actions-row :deep(.app-action-btn) {
  flex: 1;
  min-width: 0;
}

.app-dl-actions-row--single :deep(.app-action-btn) {
  max-width: 100%;
}

.app-dl-fallback {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border);
}

.app-dl-fallback-title {
  margin: 0 0 0.5rem;
  font-family: var(--heading);
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.3;
}

.app-dl-fallback-text {
  margin: 0 0 0.85rem;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}

</style>