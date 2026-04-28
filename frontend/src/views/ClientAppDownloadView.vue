<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { fetchJson, subscriptionOpenPath } from '../api/client.js'
import {
  forcedStoreRefs,
  pickStoreRefsAuto,
} from '../util/subscriptionOpenStores.js'

const route = useRoute()

const loading = ref(true)
/** @type {import('vue').Ref<string | null>} */
const error = ref(null)
/** @type {import('vue').Ref<null | { client_code: string, display_name: string, store_links: Record<string, unknown> }>} */
const appInfo = ref(null)

const client = computed(() => String(route.params.client ?? ''))

const platformFromQuery = computed(() => {
  const p = route.query.platform
  return typeof p === 'string' ? p : null
})

const tokenFromQuery = computed(() => {
  const t = route.query.token
  return typeof t === 'string' && t ? t : null
})

const subError = computed(() => {
  const e = route.query.sub_error
  return typeof e === 'string' ? e : null
})

const errorBanner = computed(() => {
  switch (subError.value) {
    case 'invalid_token':
      return 'Ссылка недействительна. Получите новую в боте или в личном кабинете.'
    case 'inactive':
      return 'Подписка не активна. Продлите её и откройте ссылку снова.'
    case 'load_failed':
      return 'Не удалось проверить ссылку подписки. Попробуйте открыть снова или установите клиент.'
    default:
      return null
  }
})

/** @type {import('vue').Ref<{ site?: string | null, download?: string | null } | null>} */
const storeRef = ref(null)

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

async function load() {
  loading.value = true
  error.value = null
  appInfo.value = null
  storeRef.value = null

  if (!client.value) {
    loading.value = false
    error.value = 'Не указан клиент.'
    return
  }

  try {
    const data = await fetchJson(
      `/api/public/client-apps/${encodeURIComponent(client.value)}`,
    )
    appInfo.value = data
    document.title = `${data.display_name} — Подорожник VPN`
    applyStoreLinks(data.store_links, platformFromQuery.value)
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(
  () => [route.params.client, route.query.platform],
  () => {
    load()
  },
)

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

const openWithSubscriptionHref = computed(() => {
  const t = tokenFromQuery.value
  if (!t) return null
  return subscriptionOpenPath(t, client.value, platformFromQuery.value)
})
</script>

<template>
  <div class="app-dl">
    <div class="app-dl-wrap">
      <RouterLink
        class="app-dl-back"
        to="/cabinet"
      ><span
        class="app-dl-back-arrow"
        aria-hidden="true"
      >←</span> Личный кабинет</RouterLink>

      <div class="app-dl-card">
        <template v-if="loading">
          <p class="app-dl-muted">
            Загрузка…
          </p>
        </template>
        <template v-else-if="error">
          <h1 class="app-dl-h1">
            Клиент не найден
          </h1>
          <p class="app-dl-body">
            {{ error }}
          </p>
        </template>
        <template v-else-if="appInfo">
          <div
            v-if="errorBanner"
            class="app-dl-banner"
            role="status"
          >
            {{ errorBanner }}
          </div>
          <h1 class="app-dl-h1">
            {{ appInfo.display_name }}
          </h1>
          <p class="app-dl-lead">
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
            v-if="openWithSubscriptionHref"
            class="app-dl-open-block"
          >
            <p class="app-dl-hint">
              Уже установили клиент — импортируйте подписку:
            </p>
            <a
              class="btn-primary app-dl-open-full"
              :href="openWithSubscriptionHref"
            >Открыть с подпиской</a>
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

.app-dl-back {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
  max-width: 26rem;
  box-sizing: border-box;
  padding: 0;
  margin: 0;
  border: none;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: color 0.2s ease;
}

.app-dl-back:hover {
  color: var(--accent);
}

.app-dl-back-arrow {
  font-size: 1em;
  line-height: 1;
}

.app-dl-banner {
  margin: 0 0 1rem;
  padding: 0.65rem 0.75rem;
  border-radius: var(--radius);
  background: var(--danger-soft);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: var(--danger);
  font-size: 0.9rem;
  line-height: 1.45;
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
  text-decoration: none;
  padding: 0.65rem 1.1rem;
}

.app-dl-body {
  margin: 0 0 1rem;
  color: var(--text);
  line-height: 1.55;
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
