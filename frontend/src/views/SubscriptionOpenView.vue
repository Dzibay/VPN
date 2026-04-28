<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
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

let openTimer = null
const didLeave = ref(false)

function clearOpenTimer() {
  if (openTimer) {
    clearTimeout(openTimer)
    openTimer = null
  }
}

function scheduleOpenFallback() {
  clearOpenTimer()
  openTimer = setTimeout(() => {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
    if (didLeave.value) return
    didLeave.value = true
    goToApps()
  }, 4000)
}

async function load() {
  loading.value = true
  didLeave.value = false
  clearOpenTimer()

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
    clearOpenTimer()
    load()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  clearOpenTimer()
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
          <div
            class="sub-open-spinner"
            role="status"
            aria-label="Загрузка"
          />
          <p class="sub-open-text">
            {{ loading ? 'Проверяем ссылку…' : 'Открываем приложение…' }}
          </p>
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
</style>
