<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import { fetchJson } from '../api/client.js'
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
        'Не удалось проверить ссылку подписки. Попробуйте открыть снова или установите клиент.',
    }
  }
  if (page.value?.state === 'invalid_token') {
    return {
      kind: 'danger',
      text:
        page.value.message
        || 'Ссылка недействительна. Получите новую в боте или в личном кабинете.',
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
    return 'Открыть с подпиской'
  }
  return p.open_button_label
})

/** На мобильном после диплинка — быстрый переход в магазин, если вкладка осталась на переднем плане. */
const OPEN_MOBILE_STORE_FALLBACK_MS = 450

let loadGeneration = 0
let openTimer = null
let deeplinkIframe = null

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

function scheduleMobileStoreFallback() {
  if (!isMobileAppStoreDevice()) return
  clearOpenTimer()
  openTimer = setTimeout(() => {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
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

/** Телефон — верхнее окно + таймер в магазин; ПК — iframe, страница не уезжает. */
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
  removeDeeplinkIframe()
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
            Не удалось загрузить
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
          <p
            v-if="page?.lead && page.state === 'ok'"
            class="app-dl-lead app-dl-lead--tight"
          >
            {{ page.lead }}
          </p>
          <p
            v-else
            class="app-dl-lead"
          >
            Скачайте приложение для вашей системы или перейдите на официальный сайт.
          </p>

          <div
            v-if="showStoreRow"
            class="app-dl-actions"
          >
            <div
              class="app-dl-actions-row"
              :class="{ 'app-dl-actions-row--single': storeRowSingle }"
            >
              <a
                v-if="storeRef?.download"
                class="btn-primary app-dl-btn"
                :href="storeRef.download"
              >Скачать</a>
              <a
                v-if="storeRef?.site"
                class="btn-secondary app-dl-btn"
                :href="storeRef.site"
              >Перейти на сайт</a>
            </div>
          </div>
          <p
            v-else
            class="app-dl-muted"
          >
            Для этой платформы нет прямой ссылки в каталоге — откройте сайт разработчика вручную.
          </p>

          <div
            v-if="page?.deeplink && page.state === 'ok'"
            class="app-dl-open-block"
          >
            <p class="app-dl-hint">
              Уже установили клиент — импортируйте подписку:
            </p>
            <button
              type="button"
              class="btn-primary app-dl-open-full"
              @click="retryOpenInClient"
            >
              {{ openInClientLabel }}
            </button>
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
  padding: 1.5rem 1rem 2.5rem;
  box-sizing: border-box;
  gap: 0.75rem;
}

.app-dl-card {
  width: 100%;
  max-width: 26rem;
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
  margin: 0 0 0.65rem;
  font-family: var(--heading);
  font-size: 1.35rem;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.25;
}

.app-dl-lead {
  margin: 0 0 1.1rem;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.5;
}

.app-dl-lead--tight {
  margin-bottom: 0.85rem;
}

.app-dl-open-block {
  margin-top: 1.25rem;
  padding-top: 1.15rem;
  border-top: 1px solid var(--card-border);
}

.app-dl-open-full {
  display: flex;
  width: 100%;
  box-sizing: border-box;
  justify-content: center;
  text-align: center;
  font: inherit;
  cursor: pointer;
  border: none;
}

.app-dl-muted {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
}

.app-dl-actions {
  margin-bottom: 0;
}

.app-dl-actions-row {
  display: flex;
  flex-direction: row;
  gap: 0.6rem;
  width: 100%;
  flex-wrap: nowrap;
}

.app-dl-actions-row :deep(.btn-primary),
.app-dl-actions-row :deep(.btn-secondary) {
  flex: 1;
  min-width: 0;
  text-align: center;
  text-decoration: none;
}

.app-dl-actions-row--single :deep(.btn-primary),
.app-dl-actions-row--single :deep(.btn-secondary) {
  max-width: 100%;
}

.app-dl-btn {
  display: inline-flex;
  justify-content: center;
  text-decoration: none;
  box-sizing: border-box;
}

.app-dl-hint {
  margin: 0 0 0.65rem;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}
</style>
