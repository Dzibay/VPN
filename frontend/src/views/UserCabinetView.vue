<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  detectStorePlatform,
  fetchJson,
  subscriptionOpenPath,
  subscriptionPublicUrl,
} from '../api/client.js'
import AppTooltip from '../components/AppTooltip.vue'
import { formatTrafficBytes } from '../utils/formatTraffic.js'

/** Подсказки к строкам исх./вх. в блоке трафика */
const TRAFFIC_HINT_UP =
  'Данные, которые ваше устройство отправило через VPN (upload).'
const TRAFFIC_HINT_DOWN =
  'Данные, которые ваше устройство получило через VPN (download).'

const PLATFORM_OPTIONS = [
  { value: 'windows', label: 'Windows' },
  { value: 'android', label: 'Android' },
  { value: 'ios', label: 'iOS' },
  { value: 'macos', label: 'macOS' },
  { value: 'linux', label: 'Linux' },
]

const router = useRouter()
const route = useRoute()

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const me = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    me.value = await fetchJson('/api/auth/me')
  } catch (e) {
    if (e.status === 401) {
      router.replace({ name: 'login', query: { redirect: '/cabinet' } })
      return
    }
    error.value = e.message || String(e)
    me.value = null
  } finally {
    loading.value = false
  }
}

function formatDate(iso) {
  if (iso == null || iso === '') return '—'
  const s = String(iso)
  const d = s.length >= 10 ? s.slice(0, 10) : s
  return d
}

/** После редиректа с бэка (?unknown_client=1) показываем подсказку и чистим URL. */
const unknownClientHint = ref(false)

const subscriptionCopied = ref(false)
/** @type {ReturnType<typeof setTimeout> | null} */
let subscriptionCopiedTimer = null

/** Платформа для `?platform=` на /sub/…/open/… (кнопки магазина). */
const storePlatform = ref(
  typeof window !== 'undefined' ? detectStorePlatform() : 'windows',
)

function setStorePlatform(p) {
  storePlatform.value = p
}

/** Локальный путь /sub/…/open/… — открываем в этом же окне через RouterLink. */
function openClientTo(clientCode) {
  const t = me.value?.subscription_token
  if (!t) return '/cabinet'
  return subscriptionOpenPath(String(t), clientCode, storePlatform.value)
}

/** Клиенты с учётом выбранной платформы (store_platforms пустой — показываем всегда). */
const filteredOpenClients = computed(() => {
  const list = me.value?.subscription_open_clients
  if (!Array.isArray(list) || !list.length) return []
  const plat = storePlatform.value
  return list.filter((c) => {
    const p = c.store_platforms
    if (!Array.isArray(p) || p.length === 0) return true
    return p.includes(plat)
  })
})

const subscriptionUrl = computed(() => {
  const t = me.value?.subscription_token
  return t ? subscriptionPublicUrl(String(t)) : ''
})

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

onMounted(() => {
  const q = route.query.unknown_client
  if (q === '1' || q === 'true') {
    unknownClientHint.value = true
    router.replace({ path: '/cabinet' })
  }
  load()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1>Личный кабинет</h1>
      <p class="sub">Профиль и параметры подписки.</p>
    </header>

    <div v-if="loading" class="card card-pad muted">Загрузка…</div>
    <div v-else-if="error" class="card card-pad err">{{ error }}</div>
    <div v-else-if="me" class="stack">
      <div v-if="me.role === 'admin'" class="card card-pad">
        <h2 class="block-title">Администратор</h2>
        <p class="hint">
          Управление серверами и пользователями — в разделе ниже в шапке или
          <RouterLink class="sub-link" to="/admin">перейти к данным</RouterLink>.
        </p>
        <dl class="dl">
          <div class="row">
            <dt>Email</dt>
            <dd>{{ me.email }}</dd>
          </div>
        </dl>
      </div>

      <div v-else class="card card-pad">
        <h2 class="block-title">Профиль</h2>
        <dl class="dl">
          <div v-if="me.email" class="row">
            <dt>Email</dt>
            <dd>{{ me.email }}</dd>
          </div>
          <div
            v-if="me.telegram_id != null || me.telegram_properties?.username"
            class="row"
          >
            <dt>Telegram</dt>
            <dd>
              <template v-if="me.telegram_id != null">
                {{ me.telegram_id
                }}<span
                  v-if="me.telegram_properties?.username"
                  class="muted"
                > @{{ me.telegram_properties.username }}</span>
              </template>
              <template
                v-else-if="me.telegram_properties?.username"
              >
                <span class="muted"
                  >@{{ me.telegram_properties.username }}</span
                >
              </template>
            </dd>
          </div>
          <div
            v-if="!me.email && me.telegram_id == null && !me.telegram_properties?.username"
            class="row"
          >
            <dt>Контакт</dt>
            <dd>—</dd>
          </div>
        </dl>
      </div>

      <div v-if="me.role === 'user'" class="card card-pad">
        <h2 class="block-title">Подписка</h2>
        <dl class="dl">
          <div class="row">
            <dt>Статус</dt>
            <dd>
              <span
                class="pill"
                :class="
                  me.subscription_active ? 'pill--ok' : 'pill--off'
                "
              >
                {{
                  me.subscription_active ? 'Активна' : 'Неактивна / истекла'
                }}
              </span>
            </dd>
          </div>
          <div class="row">
            <dt>Действует до</dt>
            <dd>{{ formatDate(me.subscription_until) }}</dd>
          </div>
          <div class="row">
            <dt>Потреблённый трафик</dt>
            <dd class="mono traffic-value">
              <span class="traffic-total">{{
                formatTrafficBytes(me.traffic_total_bytes ?? 0)
              }}</span>
              <span class="traffic-paren" aria-hidden="true">(</span>
              <AppTooltip :text="TRAFFIC_HINT_UP">
                <span class="traffic-detail">исх.&nbsp;{{
                  formatTrafficBytes(me.traffic_up_bytes ?? 0)
                }}</span>
              </AppTooltip>
              <span class="traffic-paren" aria-hidden="true">,&nbsp;</span>
              <AppTooltip :text="TRAFFIC_HINT_DOWN">
                <span class="traffic-detail">вх.&nbsp;{{
                  formatTrafficBytes(me.traffic_down_bytes ?? 0)
                }}</span>
              </AppTooltip>
              <span class="traffic-paren" aria-hidden="true">)</span>
            </dd>
          </div>
        </dl>
        <button
          type="button"
          class="copy-sub-btn"
          :disabled="!subscriptionUrl"
          @click="copySubscriptionUrl"
        >
          {{ subscriptionCopied ? 'Скопировано' : 'Скопировать ссылку подписки' }}
        </button>
        <p class="hint hint-below-copy">
          Используйте в VPN-клиенте как subscription URL (если поддерживается).
        </p>
      </div>

      <div
        v-if="me.role === 'user' && me.subscription_open_clients?.length"
        class="card card-pad card-apps"
      >
        <div
          v-if="unknownClientHint"
          class="banner-warn"
          role="status"
        >
          Такого клиента в ссылке нет — выберите приложение ниже.
        </div>
        <h2 class="block-title">Подключить в приложении</h2>
        <div class="platform-block">
          <div
            class="platform-chips"
            role="radiogroup"
            aria-label="Платформа для ссылок приложения (сайт и скачивание)"
          >
            <button
              v-for="p in PLATFORM_OPTIONS"
              :key="p.value"
              type="button"
              class="platform-chip"
              :class="{ 'platform-chip--active': storePlatform === p.value }"
              role="radio"
              :aria-checked="storePlatform === p.value"
              @click="setStorePlatform(p.value)"
            >
              {{ p.label }}
            </button>
          </div>
        </div>
        <p
          v-if="!filteredOpenClients.length"
          class="hint clients-empty"
        >
          Для этой платформы нет клиентов с готовой ссылкой установки — выберите другую ОС выше.
        </p>
        <div
          v-else
          class="client-btns"
        >
          <template
            v-for="c in filteredOpenClients"
            :key="c.client_code"
          >
            <RouterLink
              v-if="me.subscription_active"
              class="client-btn"
              :to="openClientTo(c.client_code)"
            >{{ c.display_name }}</RouterLink>
            <span
              v-else
              class="client-btn client-btn--off"
              title="Продлите подписку"
            >{{ c.display_name }}</span>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 520px;
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

.back {
  display: inline-block;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  margin-bottom: 1rem;
  transition: color 0.2s ease;
}

.back:hover {
  color: var(--accent);
}

h1 {
  font-size: 1.6rem;
  margin: 0 0 0.4rem;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

.muted {
  color: var(--muted);
}

.err {
  color: var(--danger);
}

.block-title {
  font-size: 1.05rem;
  margin: 0 0 1rem;
  color: var(--text-h);
}

.dl {
  margin: 0;
}

.row {
  display: grid;
  grid-template-columns: 8.5rem 1fr;
  gap: 0.5rem 1rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--nav-border);
  font-size: 0.92rem;
}

.row:last-child {
  border-bottom: none;
}

dt {
  margin: 0;
  color: var(--muted);
  font-weight: 600;
}

dd {
  margin: 0;
  color: var(--text-h);
  word-break: break-word;
}

.mono {
  font-variant-numeric: tabular-nums;
}

.traffic-value {
  line-height: 1.45;
}

.traffic-total {
  color: var(--text-h);
  font-weight: 600;
  font-size: 1.05em;
}

.traffic-paren {
  color: color-mix(in srgb, var(--muted) 55%, transparent);
  font-weight: 400;
  font-size: 0.78em;
  vertical-align: baseline;
}

.traffic-detail {
  color: color-mix(in srgb, var(--muted) 72%, var(--text) 28%);
  font-weight: 400;
  font-size: 0.78em;
  cursor: help;
}

.pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}

.pill--ok {
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.pill--off {
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid rgba(225, 29, 72, 0.35);
}

.hint {
  margin: 0 0 0.65rem;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}

.hint-below-copy {
  margin: 0.6rem 0 0;
}

.sub-link {
  font-size: 0.85rem;
  word-break: break-all;
  color: var(--accent);
  font-weight: 500;
}

.copy-sub-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  box-sizing: border-box;
  margin: 1rem 0 0;
  padding: 0.5rem 1rem;
  border-radius: 10px;
  font: inherit;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--on-accent);
  background: color-mix(in srgb, var(--accent) 78%, #050a08 22%);
  border: 1px solid color-mix(in srgb, var(--accent-border) 75%, #020403 25%);
  transition:
    filter 0.15s ease,
    background 0.15s ease,
    opacity 0.15s ease;
}

.copy-sub-btn:hover:not(:disabled) {
  filter: brightness(1.04);
  background: color-mix(in srgb, var(--accent-hover) 80%, #050a08 20%);
}

.copy-sub-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.copy-sub-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

@media (prefers-color-scheme: light) {
  .copy-sub-btn {
    background: var(--accent);
    border-color: var(--accent-border);
  }

  .copy-sub-btn:hover:not(:disabled) {
    background: var(--accent-hover);
  }
}

.banner-warn {
  margin: 0 0 1rem;
  padding: 0.65rem 0.85rem;
  border-radius: 10px;
  font-size: 0.88rem;
  line-height: 1.45;
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid rgba(225, 29, 72, 0.35);
}

.card-apps .platform-block {
  margin-top: 0.75rem;
  padding-top: 0;
  border-top: none;
}

.card-apps .client-btns,
.card-apps .clients-empty {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--nav-border);
}

.clients-hint {
  margin-top: 0.35rem;
}

.client-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.client-btn {
  display: inline-block;
  padding: 0.45rem 0.85rem;
  border-radius: 10px;
  font-size: 0.86rem;
  font-weight: 600;
  text-decoration: none;
  /* Как .cta.primary: тёмные токены — тёмный текст на акценте, без #fff (слишком ярко на OLED) */
  color: var(--on-accent);
  background: color-mix(in srgb, var(--accent) 78%, #050a08 22%);
  border: 1px solid color-mix(in srgb, var(--accent-border) 75%, #020403 25%);
  transition:
    filter 0.15s ease,
    background 0.15s ease;
}

.client-btn:hover {
  filter: brightness(1.04);
  background: color-mix(in srgb, var(--accent-hover) 80%, #050a08 20%);
}

.client-btn--off {
  cursor: not-allowed;
  background: var(--nav-border);
  color: var(--muted);
  border-color: var(--card-border);
}

.client-btn--off:hover {
  filter: none;
}

@media (prefers-color-scheme: light) {
  .client-btn {
    background: var(--accent);
    border-color: var(--accent-border);
  }

  .client-btn:hover {
    background: var(--accent-hover);
  }
}

.platform-block {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--nav-border);
}

.platform-label {
  display: block;
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

.platform-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.platform-chip {
  appearance: none;
  margin: 0;
  padding: 0.38rem 0.75rem;
  border-radius: var(--radius-pill);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--text);
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease;
}

.platform-chip:hover {
  border-color: var(--accent-border);
  color: var(--text-h);
}

.platform-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.platform-chip--active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}

.platform-detect-hint {
  margin: 0.55rem 0 0;
  font-size: 0.8rem;
}
</style>
