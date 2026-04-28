<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
/** После вызова deeplink ждём: либо сигнал открытия (visibility), либо таймаут → страница установки. */
const postDeeplinkWait = ref(false)
/** Только если вкладка ушла в фон после deeplink — считаем, что приложение откликнулось; иначе не показываем «успех». */
const openedOk = ref(false)
const token = computed(() => String(route.params.token ?? ''))
const client = computed(() => String(route.params.client ?? ''))

const platformFromQuery = computed(() => {
  const p = route.query.platform
  return typeof p === 'string' ? p : null
})

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

function appsQuery(extra = {}) {
  const q = { ...extra }
  if (token.value) q.token = token.value
  if (platformFromQuery.value) q.platform = platformFromQuery.value
  return q
}

function goToApps(subError) {
  router.replace({
    name: 'client-app-download',
    params: { client: client.value },
    query: appsQuery(subError ? { sub_error: subError } : {}),
  })
}

/** Если после deeplink вкладка так и осталась на переднем плане — переход на установку (нет обработчика URI / клиент не открылся). */
const OPEN_FALLBACK_MS = 2200
/** Окно для принятия visibility/pagehide как «приложение открылось». */
const OPEN_SUCCESS_WINDOW_MS = 3500

let deeplinkIssuedAt = 0
let openTimer = null

let detachOpenSignals = null
function teardownOpenSignals() {
  if (detachOpenSignals) {
    detachOpenSignals()
    detachOpenSignals = null
  }
}

function registerOpenSuccessSignals() {
  teardownOpenSignals()
  deeplinkIssuedAt = Date.now()

  function tryMarkOpened() {
    if (openedOk.value) return
    const elapsed = Date.now() - deeplinkIssuedAt
    if (elapsed > OPEN_SUCCESS_WINDOW_MS) return
    openedOk.value = true
    postDeeplinkWait.value = false
    clearOpenTimer()
    teardownOpenSignals()
    loading.value = false
  }

  const onVisibility = () => {
    if (document.visibilityState === 'hidden') tryMarkOpened()
  }
  const onPageHide = () => tryMarkOpened()

  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('pagehide', onPageHide)
  detachOpenSignals = () => {
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('pagehide', onPageHide)
  }
}

function clearOpenTimer() {
  if (openTimer) {
    clearTimeout(openTimer)
    openTimer = null
  }
}

function scheduleOpenFallback() {
  clearOpenTimer()
  openTimer = setTimeout(() => {
    if (openedOk.value) return
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
    postDeeplinkWait.value = false
    teardownOpenSignals()
    goToApps()
  }, OPEN_FALLBACK_MS)
}

async function load() {
  loading.value = true
  postDeeplinkWait.value = false
  openedOk.value = false
  clearOpenTimer()
  teardownOpenSignals()

  if (!token.value || !client.value) {
    loading.value = false
    goToApps('load_failed')
    return
  }

  try {
    const data = await fetchJson(buildDataPath())

    if (data.state === 'invalid_token' || data.state === 'inactive') {
      goToApps(data.state)
      return
    }

    if (data.state === 'ok' && data.deeplink) {
      if (typeof data.title === 'string') document.title = data.title
      loading.value = false
      postDeeplinkWait.value = true
      registerOpenSuccessSignals()
      try {
        window.location.replace(String(data.deeplink))
      } catch {
        /* ignore */
      }
      scheduleOpenFallback()
      return
    }

    goToApps('load_failed')
  } catch (e) {
    if (e.status === 404) {
      router.replace({ path: '/cabinet', query: { unknown_client: '1' } })
      return
    }
    goToApps('load_failed')
  } finally {
    loading.value = false
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
  teardownOpenSignals()
})
</script>

<template>
  <div class="sub-open">
    <div class="sub-open-wrap">
      <div class="sub-open-card">
        <div class="sub-open-brand">
          <img
            src="/icons/podorozhnik-logo.png"
            alt=""
            @error="(e) => { const el = e.target; if (el instanceof HTMLElement) el.style.display = 'none' }"
          >
          <span>Подорожник VPN</span>
        </div>
        <div
          class="sub-open-loader"
          aria-live="polite"
        >
          <template v-if="openedOk">
            <div
              class="sub-open-success-icon"
              aria-hidden="true"
            >
              ✓
            </div>
            <p class="sub-open-text sub-open-text-success">
              Готово
            </p>
            <p class="sub-open-sub">
              Подписка открыта в приложении. Можно вернуться в браузер — VPN-соединение настраивается в клиенте.
            </p>
          </template>
          <template v-else-if="postDeeplinkWait">
            <div
              class="sub-open-spinner"
              role="status"
              aria-label="Открываем приложение"
            />
            <p class="sub-open-text">
              Открываем приложение…
            </p>
          </template>
          <template v-else>
            <div
              v-if="loading"
              class="sub-open-spinner"
              role="status"
              aria-label="Загрузка"
            />
            <p class="sub-open-text">
              {{ loading ? 'Проверяем ссылку…' : 'Открываем приложение…' }}
            </p>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sub-open {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  font: inherit;
  color: var(--text);
  background: var(--bg-gradient);
}

.sub-open-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem 2.5rem;
  box-sizing: border-box;
}

.sub-open-card {
  width: 100%;
  max-width: 22rem;
  padding: 1.35rem 1.25rem 1.5rem;
  border-radius: var(--radius-lg);
  background: var(--surface-glass);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-md);
  box-sizing: border-box;
  text-align: center;
}

.sub-open-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: 0.02em;
}

.sub-open-brand img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.sub-open-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.sub-open-spinner {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 50%;
  border: 3px solid var(--accent-soft);
  border-top-color: var(--accent);
  animation: sub-open-spin 0.75s linear infinite;
}

@keyframes sub-open-spin {
  to {
    transform: rotate(360deg);
  }
}

.sub-open-text {
  margin: 0;
  font-size: 0.92rem;
  color: var(--muted);
  line-height: 1.45;
}

.sub-open-text-success {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-h);
}

.sub-open-success-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--on-accent, #000);
  background: var(--accent);
  line-height: 1;
}

.sub-open-sub {
  margin: 0;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 18rem;
}
</style>
