<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  detectStorePlatform,
  fetchJson,
  sitePublicUrl,
  subscriptionClashPublicUrl,
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

const CABINET_TAB_IDS = ['subscription', 'profile', 'referral']

function normalizeCabinetTab(raw) {
  const t =
    typeof raw === 'string' ? raw.trim() : Array.isArray(raw) ? String(raw[0] ?? '').trim() : ''
  return CABINET_TAB_IDS.includes(t) ? t : 'subscription'
}

const activeCabinetTab = ref(normalizeCabinetTab(route.query.tab))

watch(
  () => route.query.tab,
  (q) => {
    activeCabinetTab.value = normalizeCabinetTab(q)
  },
)

function setCabinetTab(id) {
  const next = normalizeCabinetTab(id)
  activeCabinetTab.value = next
  const q = { ...route.query }
  if (next === 'subscription') {
    delete q.tab
  } else {
    q.tab = next
  }
  router.replace({ path: route.path, query: q })
}

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const me = ref(null)

const referralsStaffVisible = computed(
  () => me.value?.role === 'admin' || me.value?.role === 'manager',
)

const referralClientUser = computed(() => me.value?.role === 'user')

function telegramPropTrim(props, key) {
  if (!props || typeof props !== 'object') return ''
  const v = props[key]
  return typeof v === 'string' && v.trim() !== '' ? v.trim() : ''
}

/** Есть ли в БД привязка / данные Telegram для блока профиля */
const profileTelegramLinked = computed(() => {
  const m = me.value
  if (!m) return false
  if (m.telegram_id != null) return true
  const p = m.telegram_properties
  return Boolean(
    telegramPropTrim(p, 'username') ||
      telegramPropTrim(p, 'first_name') ||
      telegramPropTrim(p, 'last_name'),
  )
})

const profileTelegramUsername = computed(() => {
  const raw = telegramPropTrim(me.value?.telegram_properties, 'username')
  if (!raw) return ''
  return raw.startsWith('@') ? raw : `@${raw}`
})

/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const myReferralLink = ref(null)
const myReferralLoading = ref(false)
const myReferralError = ref(null)
const referralCopySite = ref(false)
const referralCopyTg = ref(false)
/** @type {ReturnType<typeof setTimeout> | null} */
let referralCopySiteTimer = null
/** @type {ReturnType<typeof setTimeout> | null} */
let referralCopyTgTimer = null

const effectiveReferralSiteUrl = computed(() => {
  const L = myReferralLink.value
  if (!L || typeof L !== 'object') return ''
  const direct = L.site_entry_url
  if (typeof direct === 'string' && direct.trim()) return direct.trim()
  const t = L.token
  if (typeof t !== 'string' || !t.trim()) return ''
  const base = sitePublicUrl().replace(/\/$/, '')
  if (!base) return ''
  return `${base}/?ref=${encodeURIComponent(t.trim())}`
})

const effectiveReferralTelegramUrl = computed(() => {
  const L = myReferralLink.value
  if (!L || typeof L !== 'object') return ''
  const direct = L.telegram_deep_link
  if (typeof direct === 'string' && direct.trim()) return direct.trim()
  return ''
})

async function loadMyReferral() {
  if (me.value?.role !== 'user') {
    myReferralLink.value = null
    myReferralError.value = null
    return
  }
  myReferralLoading.value = true
  myReferralError.value = null
  try {
    const data = await fetchJson('/api/referral/me')
    myReferralLink.value = data?.link ?? null
  } catch (e) {
    myReferralError.value = e.message || String(e)
    myReferralLink.value = null
  } finally {
    myReferralLoading.value = false
  }
}

async function copyReferralSite() {
  const url = effectiveReferralSiteUrl.value
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    referralCopySite.value = true
    if (referralCopySiteTimer) clearTimeout(referralCopySiteTimer)
    referralCopySiteTimer = setTimeout(() => {
      referralCopySite.value = false
      referralCopySiteTimer = null
    }, 2000)
  } catch {
    /* ignore */
  }
}

async function copyReferralTelegram() {
  const url = effectiveReferralTelegramUrl.value
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    referralCopyTg.value = true
    if (referralCopyTgTimer) clearTimeout(referralCopyTgTimer)
    referralCopyTgTimer = setTimeout(() => {
      referralCopyTg.value = false
      referralCopyTgTimer = null
    }, 2000)
  } catch {
    /* ignore */
  }
}

watch(
  () => me.value?.role,
  (role) => {
    if (role !== 'user') {
      myReferralLink.value = null
      myReferralError.value = null
      myReferralLoading.value = false
    }
  },
)

watch(
  () => [activeCabinetTab.value, referralClientUser.value],
  ([tab, isClient]) => {
    if (tab === 'referral' && isClient) void loadMyReferral()
  },
)

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

const telegramSyncBusy = ref(false)
const telegramSyncError = ref(null)

async function openTelegramSyncLink() {
  telegramSyncBusy.value = true
  telegramSyncError.value = null
  try {
    const data = await fetchJson('/api/auth/me/telegram-sync-start', {
      method: 'POST',
      body: '{}',
    })
    const url = data?.telegram_deep_link
    if (typeof url === 'string' && url.trim()) {
      window.open(url.trim(), '_blank', 'noopener,noreferrer')
    } else {
      telegramSyncError.value = 'Сервер не вернул ссылку на бота'
    }
  } catch (e) {
    telegramSyncError.value = e.message || String(e)
  } finally {
    telegramSyncBusy.value = false
  }
}

function formatDate(iso) {
  if (iso == null || iso === '') return '—'
  const s = String(iso)
  const d = s.length >= 10 ? s.slice(0, 10) : s
  return d
}

/** Календарная дата (UTC) по `registered_at` из API — в формате YYYY-MM-DD, как «Действует до». */
function formatRegisteredAt(raw) {
  if (raw == null || raw === '') return '—'
  const t = Date.parse(String(raw))
  if (Number.isNaN(t)) return '—'
  const d = new Date(t)
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
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

const subscriptionClashUrl = computed(() => {
  const t = me.value?.subscription_token
  return t ? subscriptionClashPublicUrl(String(t)) : ''
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
      <h1>Личный кабинет</h1>
      <p class="sub">
        Подписка, профиль и реферальная программа.
      </p>
    </header>

    <div v-if="loading" class="card card-pad muted">Загрузка…</div>
    <div v-else-if="error" class="card card-pad err">{{ error }}</div>
    <template v-else-if="me">
      <nav
        class="cabinet-tabs"
        role="tablist"
        aria-label="Разделы личного кабинета"
      >
        <button
          id="cabinet-tab-subscription"
          type="button"
          role="tab"
          class="cabinet-tab"
          :class="{ 'cabinet-tab--active': activeCabinetTab === 'subscription' }"
          :aria-selected="activeCabinetTab === 'subscription'"
          aria-controls="cabinet-panel-subscription"
          @click="setCabinetTab('subscription')"
        >
          Подписка
        </button>
        <button
          id="cabinet-tab-profile"
          type="button"
          role="tab"
          class="cabinet-tab"
          :class="{ 'cabinet-tab--active': activeCabinetTab === 'profile' }"
          :aria-selected="activeCabinetTab === 'profile'"
          aria-controls="cabinet-panel-profile"
          @click="setCabinetTab('profile')"
        >
          Профиль
        </button>
        <button
          id="cabinet-tab-referral"
          type="button"
          role="tab"
          class="cabinet-tab"
          :class="{ 'cabinet-tab--active': activeCabinetTab === 'referral' }"
          :aria-selected="activeCabinetTab === 'referral'"
          aria-controls="cabinet-panel-referral"
          @click="setCabinetTab('referral')"
        >
          Реферальная система
        </button>
      </nav>

      <div
        v-show="activeCabinetTab === 'subscription'"
        id="cabinet-panel-subscription"
        class="cabinet-panel"
        role="tabpanel"
        aria-labelledby="cabinet-tab-subscription"
      >
        <div class="stack">
          <div class="card card-pad">
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
              Для FlClashX, Clash Meta и других клиентов на Clash 
              используйте специальную кнопку подключения ниже
            </p>
          </div>

          <div
            v-if="me.subscription_open_clients?.length"
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
              <RouterLink
                v-for="c in filteredOpenClients"
                :key="c.client_code"
                class="client-btn"
                :to="openClientTo(c.client_code)"
              >{{ c.display_name }}</RouterLink>
            </div>
          </div>
        </div>
      </div>

      <div
        v-show="activeCabinetTab === 'profile'"
        id="cabinet-panel-profile"
        class="cabinet-panel"
        role="tabpanel"
        aria-labelledby="cabinet-tab-profile"
      >
        <div class="stack">
          <div v-if="me.role === 'admin'" class="card card-pad">
            <h2 class="block-title">Администратор</h2>
            <p class="hint">
              Управление серверами и пользователями — в разделе ниже в шапке или
              <RouterLink class="sub-link" to="/admin/users">перейти к данным</RouterLink>.
            </p>
          </div>
          <div class="card card-pad">
            <h2 class="block-title">Профиль</h2>
            <dl class="dl">
              <div v-if="me.email" class="row">
                <dt>Email</dt>
                <dd>{{ me.email }}</dd>
              </div>
              <div class="row row--telegram">
                <dt>Telegram</dt>
                <dd>
                  <template v-if="profileTelegramLinked">
                    <div v-if="profileTelegramUsername">
                      {{ profileTelegramUsername }}
                    </div>
                    <p v-else class="hint profile-tg-no-username-hint">
                      Никнейм в Telegram (@username) не указан.
                    </p>
                  </template>
                  <template v-else>
                    <p class="hint profile-tg-unlinked-hint">
                      У вас не привязан телеграмм. 
                      Если Вы уже использовали нашего бота 
                      или хотите использовать его для управления аккаунтом - 
                      нажмите кнопку ниже и активируйте бота.
                    </p>
                    <p v-if="telegramSyncError" class="err profile-tg-sync-err">
                      {{ telegramSyncError }}
                    </p>
                    <button
                      type="button"
                      class="copy-sub-btn profile-tg-open-btn"
                      :disabled="telegramSyncBusy"
                      @click="openTelegramSyncLink"
                    >
                      {{
                        telegramSyncBusy
                          ? 'Готовим ссылку…'
                          : 'Привязать телеграм бота'
                      }}
                    </button>
                  </template>
                </dd>
              </div>
              <div class="row">
                <dt>Дата регистрации</dt>
                <dd>{{ formatRegisteredAt(me.registered_at) }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <div
        v-show="activeCabinetTab === 'referral'"
        id="cabinet-panel-referral"
        class="cabinet-panel"
        role="tabpanel"
        aria-labelledby="cabinet-tab-referral"
      >
        <div class="stack">
          <div class="card card-pad referral-card">
            <h2 class="block-title">Реферальная система</h2>
            <p v-if="referralClientUser" class="hint">
              Ваша персональная реферальная ссылка — ниже; по ней учитываются приглашённые. Ссылка при
              необходимости создаётся автоматически при первом открытии этой вкладки.
            </p>
            <p v-else-if="referralsStaffVisible" class="hint">
              Сотрудникам: выпуск и учёт всех реферальных токенов — в админ-панели.
            </p>
            <p v-else class="hint">
              Персональные ссылки для клиентов доступны в личном кабинете для учётной записи пользователя.
            </p>

            <div
              v-if="referralClientUser"
              class="referral-my-block"
              aria-label="Ваша реферальная ссылка"
            >
              <div v-if="myReferralLoading" class="hint referral-my-status">
                Загрузка…
              </div>
              <div v-else-if="myReferralError" class="referral-my-err">
                {{ myReferralError }}
              </div>
              <template v-else-if="myReferralLink">
                <dl class="dl referral-stats-dl">
                  <div class="row">
                    <dt>Токен</dt>
                    <dd class="mono">{{ myReferralLink.token }}</dd>
                  </div>
                  <div class="row">
                    <dt>Клики</dt>
                    <dd class="mono">{{ myReferralLink.clicks_count ?? 0 }}</dd>
                  </div>
                  <div class="row">
                    <dt>Регистрации</dt>
                    <dd class="mono">{{ myReferralLink.registrations_count ?? 0 }}</dd>
                  </div>
                  <div class="row">
                    <dt>Оплаты</dt>
                    <dd class="mono">{{ myReferralLink.payments_count ?? 0 }}</dd>
                  </div>
                </dl>
                <div class="referral-copy-stack">
                  <button
                    type="button"
                    class="btn-secondary referral-copy-wide"
                    :disabled="!effectiveReferralSiteUrl"
                    @click="copyReferralSite"
                  >
                    {{
                      referralCopySite
                        ? 'Скопировано'
                        : 'Скопировать ссылку на сайт'
                    }}
                  </button>
                  <p
                    v-if="!effectiveReferralSiteUrl"
                    class="hint referral-copy-warn"
                  >
                    Не удалось собрать ссылку: задайте в .env API переменную
                    <code class="inline-code">SITE_ADRESS</code> (публичный URL сайта).
                  </p>
                  <button
                    type="button"
                    class="btn-secondary referral-copy-wide"
                    :disabled="!effectiveReferralTelegramUrl"
                    @click="copyReferralTelegram"
                  >
                    {{
                      referralCopyTg
                        ? 'Скопировано'
                        : 'Скопировать ссылку на бота (Telegram)'
                    }}
                  </button>
                  <p
                    v-if="!effectiveReferralTelegramUrl"
                    class="hint referral-copy-warn"
                  >
                    Ссылка на бота не настроена на сервере — скопируйте токен и передайте
                    приглашённому вручную или используйте ссылку на сайт.
                  </p>
                </div>
              </template>
              <p v-else class="hint referral-my-status">
                Не удалось получить реферальную ссылку. Обновите страницу или попробуйте позже.
              </p>
            </div>

            <div v-if="referralsStaffVisible" class="referral-staff-actions">
              <RouterLink
                class="client-btn referral-staff-btn"
                :to="{ path: '/admin/referrals' }"
              >
                Управление реферальными токенами
              </RouterLink>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 520px;
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
}

.cabinet-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.35rem;
  margin-bottom: 1rem;
}

.cabinet-tab {
  appearance: none;
  margin: 0;
  padding: 0.4rem 0.5rem;
  border-radius: var(--radius-pill);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.25;
  cursor: pointer;
  text-align: center;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  border: 1px solid var(--card-border);
  background: var(--surface);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.cabinet-tab:hover {
  color: var(--accent);
  border-color: var(--accent-border);
}

.cabinet-tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.cabinet-tab--active {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

.cabinet-tab--active:hover {
  color: var(--on-accent);
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}

.referral-card .inline-code {
  font-family: var(--mono);
  font-size: 0.88em;
  padding: 0.08rem 0.3rem;
  border-radius: 4px;
  background: var(--code-bg);
  border: 1px solid var(--card-border);
  color: var(--text-h);
}

.referral-staff-actions {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--nav-border);
}

.referral-staff-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  box-sizing: border-box;
  text-decoration: none;
}

.referral-my-block {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--nav-border);
}

.referral-my-status {
  margin-bottom: 0;
}

.referral-my-err {
  margin: 0;
  font-size: 0.92rem;
  color: var(--danger);
  line-height: 1.45;
}

.referral-stats-dl {
  margin-bottom: 0.25rem;
}

.referral-copy-stack {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.85rem;
}

.referral-copy-wide {
  width: 100%;
  box-sizing: border-box;
  justify-content: center;
}

.referral-copy-warn {
  margin: 0;
  font-size: 0.82rem;
}

@media (max-width: 420px) {
  .cabinet-tab {
    font-size: 0.72rem;
    padding: 0.38rem 0.35rem;
  }
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
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

.profile-tg-unlinked-hint {
  margin-bottom: 0.65rem;
}

.profile-tg-sync-err {
  margin: 0 0 0.5rem;
  font-size: 0.88rem;
}

.profile-tg-open-btn {
  margin-top: 0.35rem;
  text-decoration: none;
}

.row--telegram dd {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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
