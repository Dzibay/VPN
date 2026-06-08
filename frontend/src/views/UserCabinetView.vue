<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AppActionButton from '../components/AppActionButton.vue'
import AppPager from '../components/AppPager.vue'
import SitePageLayout from '../components/SitePageLayout.vue'
import {
  detectStorePlatform,
  fetchJson,
  sitePublicUrl,
  subscriptionOpenPath,
  subscriptionPublicUrl,
} from '../api/client.js'
import AppTooltip from '../components/AppTooltip.vue'
import { formatTrafficBytes } from '../utils/formatTraffic.js'
import {
  formatMskApiDateTime,
  formatMskSubscriptionDaysRemaining,
} from '../utils/mskDate.js'
import { useOffsetPagination } from '../composables/useOffsetPagination.js'
import {
  refreshClientSupportUnread,
  startClientSupportUnreadPolling,
  stopClientSupportUnreadPolling,
  useClientSupportUnread,
} from '../composables/useClientSupportUnread.js'
import { formatRub } from '../composables/useYookassaPricing.js'
import { isMobileDevice, openTelegramDeepLink } from '../utils/subscription/openDeepLink.js'
import {
  formatSubscriptionConnectionOs,
  formatSubscriptionConnectionUserAgent,
} from '../utils/subscription/subscriptionConnectionFormat.js'
import {
  hideClientLogoOnError,
  openClientLogoUrl,
} from '../utils/subscription/subscriptionOpenClientLogo.js'
import { BookOpen, Check, ChevronRight, CreditCard, Gift, Calendar, Headphones, Link2, Loader2, Lock, MousePointerClick, Send, UserPlus, Wallet } from 'lucide-vue-next'

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

const payNeedTelegramQuery = () => {
  const v = route.query.pay_need_telegram
  return v === '1' || v === 'true' || v === true
}

watch(
  () => [route.query.pay_need_telegram, route.query.tab],
  () => {
    if (!payNeedTelegramQuery()) return
    if (normalizeCabinetTab(route.query.tab) !== 'profile') {
      activeCabinetTab.value = 'profile'
      void router.replace({
        path: route.path,
        query: { ...route.query, tab: 'profile' },
      })
    }
  },
  { immediate: true },
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
  if (next !== 'profile') {
    delete q.pay_need_telegram
  }
  router.replace({ path: route.path, query: q })
}

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const me = ref(null)

const subscriptionConnectionDeletingId = ref(null)
const subscriptionConnectionDeleteError = ref(null)

const referralsStaffVisible = computed(
  () => me.value?.role === 'admin' || me.value?.role === 'manager',
)

const referralClientUser = computed(() => me.value?.role === 'user')

const { unreadCount: clientSupportUnread } = useClientSupportUnread()

const clientSupportUnreadLabel = computed(() => {
  const n = clientSupportUnread.value
  if (n < 1) return ''
  if (n === 1) return '1 новый ответ'
  if (n > 99) return '99+ новых ответов'
  return `${n} новых ответа`
})

/** @type {import('vue').Ref<Array<{ id: number, amount: string | number, months: number, provider: string, payment_kind: string, created_at: string }>>} */
const paymentHistoryItems = ref([])
const paymentHistoryTotal = ref(0)
const paymentHistoryLoading = ref(false)
const paymentHistoryError = ref(null)

const {
  offset: paymentHistoryOffset,
  limit: paymentHistoryLimit,
  canPrev: paymentHistoryCanPrev,
  canNext: paymentHistoryCanNext,
  rangeLabel: paymentHistoryRangeLabel,
  prev: paymentHistoryPrev,
  next: paymentHistoryNext,
  reset: resetPaymentHistoryPagination,
} = useOffsetPagination({
  limit: 10,
  total: () => paymentHistoryTotal.value,
  count: () => paymentHistoryItems.value.length,
  onChange: () => {
    if (activeCabinetTab.value === 'profile' && referralClientUser.value) {
      void loadPaymentHistory()
    }
  },
})

function paymentKindLabel(k) {
  const s = String(k ?? '')
  if (s === 'subscription') return 'Подписка'
  if (s === 'one_time') return 'Разовая'
  return s || '—'
}

function paymentProviderLabel(provider) {
  const s = String(provider ?? '').trim().toLowerCase()
  if (s === 'yookassa') return 'Сайт'
  if (s === 'tribute') return 'Telegram'
  if (s === 'manual') return 'Ручное начисление'
  return s || '—'
}

function formatPaymentHistoryDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'short' })
}

function formatPaymentAmount(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return String(v ?? '—')
  return formatRub(n)
}

function formatPaymentMonths(n) {
  const m = Number(n)
  if (!Number.isFinite(m) || m < 1) return '—'
  const mod10 = m % 10
  const mod100 = m % 100
  let word = 'месяцев'
  if (mod10 === 1 && mod100 !== 11) word = 'месяц'
  else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) word = 'месяца'
  return `${m} ${word}`
}

async function loadPaymentHistory() {
  if (me.value?.role !== 'user') {
    paymentHistoryItems.value = []
    paymentHistoryTotal.value = 0
    paymentHistoryError.value = null
    return
  }
  paymentHistoryLoading.value = true
  paymentHistoryError.value = null
  try {
    const params = new URLSearchParams({
      limit: String(paymentHistoryLimit.value),
      offset: String(paymentHistoryOffset.value),
    })
    const data = await fetchJson(`/api/me/payments?${params.toString()}`)
    paymentHistoryItems.value = Array.isArray(data?.items) ? data.items : []
    paymentHistoryTotal.value = Number(data?.total) || 0
  } catch (e) {
    paymentHistoryError.value = e.message || String(e)
    paymentHistoryItems.value = []
    paymentHistoryTotal.value = 0
  } finally {
    paymentHistoryLoading.value = false
  }
}

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
const myReferralBonusPending = ref(0)
const myReferralBonusReceived = ref(0)
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
    myReferralBonusPending.value = 0
    myReferralBonusReceived.value = 0
    myReferralError.value = null
    return
  }
  myReferralLoading.value = true
  myReferralError.value = null
  try {
    const data = await fetchJson('/api/referral/me')
    myReferralLink.value = data?.link ?? null
    myReferralBonusPending.value = Number(data?.bonus_days_pending_activation ?? 0)
    myReferralBonusReceived.value = Number(data?.bonus_days_received ?? 0)
  } catch (e) {
    myReferralError.value = e.message || String(e)
    myReferralLink.value = null
    myReferralBonusPending.value = 0
    myReferralBonusReceived.value = 0
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
      myReferralBonusPending.value = 0
      myReferralBonusReceived.value = 0
      myReferralError.value = null
      myReferralLoading.value = false
    }
  },
)

watch(
  () => [activeCabinetTab.value, referralClientUser.value],
  ([tab, isClient]) => {
    if (tab === 'referral' && isClient) void loadMyReferral()
    if (tab === 'profile' && isClient) {
      resetPaymentHistoryPagination()
      void loadPaymentHistory()
    }
  },
)

async function load() {
  loading.value = true
  error.value = null
  subscriptionConnectionDeleteError.value = null
  try {
    me.value = await fetchJson('/api/me')
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
/** На телефоне: запасная ссылка под кнопкой (нативный тап, если авто-переход не сработал) */
const telegramSyncFallbackLink = ref(null)

async function openTelegramSyncLink() {
  const mobile = isMobileDevice()
  telegramSyncBusy.value = true
  telegramSyncError.value = null
  telegramSyncFallbackLink.value = null
  try {
    const data = await fetchJson('/api/me/telegram-sync-start', {
      method: 'POST',
      body: '{}',
    })
    const url = data?.telegram_deep_link
    if (typeof url !== 'string' || !url.trim()) {
      telegramSyncError.value = 'Сервер не вернул ссылку на бота'
      return
    }
    const link = url.trim()
    if (mobile) telegramSyncFallbackLink.value = link
    openTelegramDeepLink(link, { mobile })
  } catch (e) {
    telegramSyncError.value = e.message || String(e)
  } finally {
    telegramSyncBusy.value = false
  }
}

watch(profileTelegramLinked, (linked) => {
  if (linked) telegramSyncFallbackLink.value = null
})

const pwdCurrent = ref('')
const pwdNew = ref('')
const pwdNew2 = ref('')
const pwdBusy = ref(false)
const pwdError = ref(null)
const pwdOk = ref(false)
/** @type {ReturnType<typeof setTimeout> | null} */
let pwdOkTimer = null

async function submitPasswordChange() {
  pwdError.value = null
  pwdOk.value = false
  if (pwdOkTimer) {
    clearTimeout(pwdOkTimer)
    pwdOkTimer = null
  }
  if (pwdNew.value.length < 8) {
    pwdError.value = 'Новый пароль — не короче 8 символов'
    return
  }
  if (pwdNew.value !== pwdNew2.value) {
    pwdError.value = 'Новый пароль и подтверждение не совпадают'
    return
  }
  pwdBusy.value = true
  try {
    await fetchJson('/api/me/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: pwdCurrent.value,
        new_password: pwdNew.value,
      }),
    })
    pwdCurrent.value = ''
    pwdNew.value = ''
    pwdNew2.value = ''
    pwdOk.value = true
    pwdOkTimer = setTimeout(() => {
      pwdOk.value = false
      pwdOkTimer = null
    }, 4000)
    await load()
  } catch (e) {
    pwdError.value = e.message || String(e)
  } finally {
    pwdBusy.value = false
  }
}

function formatDate(iso) {
  if (iso == null || iso === '') return '—'
  const s = String(iso)
  const d = s.length >= 10 ? s.slice(0, 10) : s
  return d
}

const subscriptionRemainingLabel = computed(() =>
  formatMskSubscriptionDaysRemaining(me.value?.subscription_until),
)

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

/** Сколько уникальных приложений уже запрашивали подписку по ссылке (subscription_devices). */
const subscriptionConnectionsDisplay = computed(() => {
  const m = me.value
  if (!m) return '—'
  const n = Number(m.subscription_connections_count ?? 0)
  const raw = m.subscription_connections_limit
  const lim =
    raw == null || raw === ''
      ? null
      : typeof raw === 'number'
        ? raw
        : Number(raw)
  if (lim != null && !Number.isNaN(lim) && lim > 0) return `${n} из ${lim}`
  return `${n}`
})

const subscriptionConnectionsList = computed(() => {
  const list = me.value?.subscription_connections
  return Array.isArray(list) ? list : []
})

async function deleteSubscriptionConnection(deviceId) {
  const id = Number(deviceId)
  if (!Number.isFinite(id) || id < 1) return
  if (subscriptionConnectionDeletingId.value !== null) return
  subscriptionConnectionDeleteError.value = null
  subscriptionConnectionDeletingId.value = id
  try {
    await fetchJson(`/api/me/subscription-devices/${id}`, {
      method: 'DELETE',
    })
    await load()
  } catch (e) {
    subscriptionConnectionDeleteError.value =
      e.message || String(e)
  } finally {
    subscriptionConnectionDeletingId.value = null
  }
}

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

function goCabinetPay() {
  void router.push({ name: 'cabinet-pay' })
}

watch(
  () => me.value?.role,
  (role) => {
    if (role === 'user') {
      startClientSupportUnreadPolling()
      void refreshClientSupportUnread()
    } else {
      stopClientSupportUnreadPolling()
    }
  },
)

onMounted(() => {
  const q = route.query.unknown_client
  if (q === '1' || q === 'true') {
    unknownClientHint.value = true
    router.replace({ path: '/cabinet' })
  }
  load()
})

onBeforeUnmount(() => {
  stopClientSupportUnreadPolling()
  // Чистим таймеры «скопировано/сохранено», чтобы коллбэк не сработал после ухода со страницы.
  clearTimeout(referralCopySiteTimer)
  clearTimeout(referralCopyTgTimer)
  clearTimeout(pwdOkTimer)
  clearTimeout(subscriptionCopiedTimer)
})
</script>

<template>
  <SitePageLayout>
    <template #header>
      <header class="head">
        <h1>Личный кабинет</h1>
      </header>
    </template>

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
                <dd>
                  {{ formatDate(me.subscription_until) }}
                  <span
                    v-if="subscriptionRemainingLabel"
                    class="subscription-remaining"
                  >
                    · {{ subscriptionRemainingLabel }}
                  </span>
                </dd>
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
              <div class="row row-connections">
                <dt>Подключения</dt>
                <dd class="connections-block">
                  <div class="mono connections-count">
                    {{ subscriptionConnectionsDisplay }}
                  </div>
                  <details
                    v-if="subscriptionConnectionsList.length"
                    class="connections-expand"
                  >
                    <summary class="connections-expand__summary">
                      Устройства
                    </summary>
                    <ul
                      class="connections-expand__list"
                      role="list"
                    >
                      <li
                        v-for="conn in subscriptionConnectionsList"
                        :key="conn.id"
                        class="connections-expand__item"
                      >
                        <div class="connections-expand__line mono">
                          <span class="connections-expand__os">{{
                            formatSubscriptionConnectionOs(conn.os)
                          }}</span>
                          <span
                            class="connections-expand__dot"
                            aria-hidden="true"
                          > · </span>
                          <span class="connections-expand__ua">{{
                            formatSubscriptionConnectionUserAgent(conn.user_agent)
                          }}</span>
                        </div>
                        <button
                          type="button"
                          class="connections-expand__remove"
                          :disabled="subscriptionConnectionDeletingId !== null"
                          :aria-busy="
                            subscriptionConnectionDeletingId === Number(conn.id)
                          "
                          :aria-label="
                            `Удалить подключение: ${formatSubscriptionConnectionOs(conn.os)}, ${formatSubscriptionConnectionUserAgent(conn.user_agent)}`
                          "
                          @click.stop="deleteSubscriptionConnection(conn.id)"
                        >
                          {{
                            subscriptionConnectionDeletingId === Number(conn.id)
                              ? 'Удаление…'
                              : 'Удалить'
                          }}
                        </button>
                      </li>
                    </ul>
                    <p
                      v-if="subscriptionConnectionDeleteError"
                      class="connections-expand__del-err"
                      role="alert"
                    >
                      {{ subscriptionConnectionDeleteError }}
                    </p>
                  </details>
                </dd>
              </div>
            </dl>
            <div class="cabinet-sub-action-stack">
              <AppActionButton
                variant="accent"
                block
                stacked
                :disabled="!subscriptionUrl"
                @click="copySubscriptionUrl"
              >
                <template #icon>
                  <Check
                    v-if="subscriptionCopied"
                    :size="18"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                  <Link2
                    v-else
                    :size="18"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                </template>
                {{ subscriptionCopied ? 'Скопировано' : 'Скопировать ссылку подписки' }}
              </AppActionButton>
              <AppActionButton
                variant="pay"
                block
                stacked
                @click="goCabinetPay"
              >
                <template #icon>
                  <CreditCard
                    :size="18"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                </template>
                Оплата и продление
              </AppActionButton>
            </div>
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
                  <span
                    class="platform-chip__icon"
                    aria-hidden="true"
                  >
                    <!-- Windows -->
                    <svg
                      v-if="p.value === 'windows'"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    ><path d="M3 5.5h9V12H3V5.5zm10.5 0H21V12h-7.5V5.5zM3 13.5h9v6.5H3V13.5zm10.5 0H21v6.5h-7.5V13.5z" /></svg>
                    <!-- Android -->
                    <svg
                      v-else-if="p.value === 'android'"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    ><path d="M17.6 9.48l1.84-3.18c.16-.31.04-.69-.26-.85a.657.657 0 0 0-.83.22l-1.88 3.24a11.437 11.437 0 0 0-8.45 0L5.1 5.67a.648.648 0 0 0-.83-.22c-.3.16-.42.54-.26.85l1.84 3.18C3.25 10.82 2 13.37 2 16.19h20c0-2.82-1.25-5.37-3.4-7.71zM7 14.75c0 .55.45 1 1 1s1-.45 1-1-.45-1-1-1-1 .45-1 1zm8 0c0 .55.45 1 1 1s1-.45 1-1-.45-1-1-1-1 .45-1 1z" /></svg>
                    <!-- iOS -->
                    <svg
                      v-else-if="p.value === 'ios'"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    ><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" /></svg>
                    <!-- macOS -->
                    <svg
                      v-else-if="p.value === 'macos'"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.75"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><rect
                      x="3"
                      y="4"
                      width="18"
                      height="12"
                      rx="2"
                    /><path d="M2 18h20" /></svg>
                    <!-- Linux -->
                    <svg
                      v-else-if="p.value === 'linux'"
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path d="m4 17 5-5-5-5M13 19h7" /></svg>
                  </span>
                  <span class="platform-chip__label">{{ p.label }}</span>
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
                class="client-app-tile"
                :to="openClientTo(c.client_code)"
              >
                <div class="client-app-tile__logo">
                  <img
                    :src="openClientLogoUrl(c.client_code)"
                    :alt="`Логотип ${c.display_name}`"
                    class="client-app-tile__logo-img"
                    loading="lazy"
                    decoding="async"
                    @error="hideClientLogoOnError"
                  />
                </div>
                <span class="client-app-tile__name">{{ c.display_name }}</span>
              </RouterLink>
            </div>
          </div>

          <div class="card card-pad instructions-widget">
            <h2 class="block-title">Помощь</h2>
            <p class="hint instructions-widget__hint">
              Пошаговые инструкции и чат с поддержкой.
            </p>
            <p
              v-if="referralClientUser && clientSupportUnread > 0"
              class="support-unread-callout"
              role="status"
            >
              У вас {{ clientSupportUnreadLabel }} от поддержки — откройте чат ниже.
            </p>
            <div class="cabinet-help-action-stack">
              <AppActionButton
                variant="secondary"
                block
                stacked
                :to="{ name: 'cabinet-instructions' }"
              >
                <template #icon>
                  <BookOpen
                    :size="18"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                </template>
                Открыть инструкции
              </AppActionButton>
              <div
                class="cabinet-support-btn-wrap"
                :class="{ 'cabinet-support-btn-wrap--unread': clientSupportUnread > 0 }"
              >
                <AppActionButton
                  :variant="clientSupportUnread > 0 ? 'accent' : 'secondary'"
                  block
                  stacked
                  :to="{ name: 'cabinet-support' }"
                >
                  <template #icon>
                    <Headphones
                      :size="18"
                      :stroke-width="2"
                      aria-hidden="true"
                    />
                  </template>
                  {{
                    clientSupportUnread > 0
                      ? `Поддержка · ${clientSupportUnreadLabel}`
                      : 'Написать в поддержку'
                  }}
                </AppActionButton>
              </div>
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
              <RouterLink class="sub-link" to="/admin/users/analytics">перейти к данным</RouterLink>.
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
                    <AppActionButton
                      variant="telegram"
                      block
                      class="profile-tg-open-btn"
                      :disabled="telegramSyncBusy"
                      @click="openTelegramSyncLink"
                    >
                      <template #icon>
                        <Loader2
                          v-if="telegramSyncBusy"
                          class="profile-tg-open-btn__icon--spin"
                          :size="20"
                          :stroke-width="2"
                          aria-hidden="true"
                        />
                        <Send
                          v-else
                          :size="20"
                          :stroke-width="2"
                          aria-hidden="true"
                        />
                      </template>
                      {{
                        telegramSyncBusy
                          ? 'Готовим ссылку…'
                          : 'Привязать телеграм бота'
                      }}
                    </AppActionButton>
                    <p
                      v-if="telegramSyncFallbackLink && isMobileDevice()"
                      class="hint profile-tg-fallback-hint"
                    >
                      Если Telegram не открылся —
                      <a
                        :href="telegramSyncFallbackLink"
                        class="profile-tg-fallback-hint__link"
                        rel="noopener noreferrer"
                        >откройте ссылку вручную</a
                      >.
                    </p>
                  </template>
                </dd>
              </div>
              <div class="row">
                <dt>Дата регистрации</dt>
                <dd>{{ formatRegisteredAt(me.registered_at) }}</dd>
              </div>
            </dl>
            <details
              v-if="me.has_site_password"
              class="profile-pwd"
            >
              <summary class="profile-pwd__summary">
                Смена пароля
              </summary>
              <form
                class="profile-pwd__form"
                @submit.prevent="submitPasswordChange"
              >
                <label class="profile-pwd__field">
                  <span class="profile-pwd__label">Текущий пароль</span>
                  <input
                    v-model="pwdCurrent"
                    class="profile-pwd__input"
                    type="password"
                    name="current-password"
                    autocomplete="current-password"
                    required
                  />
                </label>
                <label class="profile-pwd__field">
                  <span class="profile-pwd__label">Новый пароль</span>
                  <input
                    v-model="pwdNew"
                    class="profile-pwd__input"
                    type="password"
                    name="new-password"
                    autocomplete="new-password"
                    required
                    minlength="8"
                  />
                </label>
                <label class="profile-pwd__field">
                  <span class="profile-pwd__label">Повтор нового пароля</span>
                  <input
                    v-model="pwdNew2"
                    class="profile-pwd__input"
                    type="password"
                    name="new-password-confirm"
                    autocomplete="new-password"
                    required
                    minlength="8"
                  />
                </label>
                <p class="profile-pwd__hint hint">
                  Минимум 8 символов.
                </p>
                <p
                  v-if="pwdError"
                  class="profile-pwd__err err"
                  role="alert"
                >
                  {{ pwdError }}
                </p>
                <p
                  v-if="pwdOk"
                  class="profile-pwd__ok"
                  role="status"
                >
                  Пароль обновлён.
                </p>
                <button
                  class="btn-primary profile-pwd__submit"
                  type="submit"
                  :disabled="pwdBusy"
                >
                  {{ pwdBusy ? 'Сохранение…' : 'Сохранить новый пароль' }}
                </button>
              </form>
            </details>
            <p
              v-else
              class="hint profile-pwd-missing"
            >
              Вход по паролю на сайте не настроен — задайте пароль при регистрации
              или через привязку email в Telegram-боте.
            </p>
          </div>

          <div
            v-if="referralClientUser"
            class="card card-pad payment-history-card"
            aria-label="История оплат"
          >
            <h2 class="block-title">История оплат</h2>
            <p v-if="paymentHistoryLoading && !paymentHistoryItems.length" class="hint">
              Загрузка…
            </p>
            <p v-else-if="paymentHistoryError" class="err">
              {{ paymentHistoryError }}
            </p>
            <template v-else>
              <p v-if="paymentHistoryTotal === 0" class="hint payment-history-empty">
                Платежей пока нет. После оплаты подписки записи появятся здесь.
              </p>
              <template v-else>
                <AppPager
                  class="payment-history-pager"
                  :range-label="paymentHistoryRangeLabel"
                  :can-prev="paymentHistoryCanPrev"
                  :can-next="paymentHistoryCanNext"
                  :loading="paymentHistoryLoading"
                  @prev="paymentHistoryPrev"
                  @next="paymentHistoryNext"
                />
                <ul class="payment-history-list" role="list">
                  <li
                    v-for="row in paymentHistoryItems"
                    :key="row.id"
                    class="payment-history-item"
                  >
                    <div class="payment-history-item__main">
                      <span class="payment-history-item__amount mono">{{
                        formatPaymentAmount(row.amount)
                      }}</span>
                      <span class="payment-history-item__months">{{
                        formatPaymentMonths(row.months)
                      }}</span>
                    </div>
                    <div class="payment-history-item__meta">
                      <span class="payment-history-item__date">{{
                        formatPaymentHistoryDate(row.created_at)
                      }}</span>
                      <span class="payment-history-item__dot" aria-hidden="true">·</span>
                      <span class="payment-history-item__kind">{{
                        paymentKindLabel(row.payment_kind)
                      }}</span>
                      <span class="payment-history-item__dot" aria-hidden="true">·</span>
                      <span class="payment-history-item__provider">{{
                        paymentProviderLabel(row.provider)
                      }}</span>
                    </div>
                  </li>
                </ul>
              </template>
            </template>
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
            <p v-if="referralClientUser" class="hint referral-card-lead">
              Делитесь ссылкой — учитываются клики, регистрации и оплаты приглашённых.
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
                <section
                  class="referral-section"
                  aria-label="Статистика реферальной ссылки"
                >
                  <h3 class="referral-section-title">Статистика</h3>
                  <div class="referral-stat-grid referral-stat-grid--3">
                    <div class="referral-stat referral-stat--row">
                      <span
                        class="referral-stat__icon-wrap"
                        aria-hidden="true"
                      >
                        <MousePointerClick
                          class="referral-stat__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <div class="referral-stat__body">
                        <span class="referral-stat__value">{{
                          myReferralLink.clicks_count ?? 0
                        }}</span>
                        <span class="referral-stat__label">Клики</span>
                      </div>
                    </div>
                    <div class="referral-stat referral-stat--row">
                      <span
                        class="referral-stat__icon-wrap"
                        aria-hidden="true"
                      >
                        <UserPlus
                          class="referral-stat__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <div class="referral-stat__body">
                        <span class="referral-stat__value">{{
                          myReferralLink.registrations_count ?? 0
                        }}</span>
                        <span class="referral-stat__label">Регистрации</span>
                      </div>
                    </div>
                    <div class="referral-stat referral-stat--row">
                      <span
                        class="referral-stat__icon-wrap"
                        aria-hidden="true"
                      >
                        <Wallet
                          class="referral-stat__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <div class="referral-stat__body">
                        <span class="referral-stat__value">{{
                          myReferralLink.payments_count ?? 0
                        }}</span>
                        <span class="referral-stat__label">Оплаты</span>
                      </div>
                    </div>
                  </div>
                </section>

                <section
                  class="referral-section"
                  aria-label="Бонусные дни реферальной программы"
                >
                  <h3 class="referral-section-title">Бонусные дни</h3>
                  <div class="referral-stat-grid referral-stat-grid--2">
                    <div class="referral-stat referral-stat--row referral-stat--bonus">
                      <span
                        class="referral-stat__icon-wrap"
                        aria-hidden="true"
                      >
                        <Gift
                          class="referral-stat__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <div class="referral-stat__body">
                        <span class="referral-stat__value">{{
                          myReferralBonusPending
                        }}</span>
                        <span class="referral-stat__label">Накоплено</span>
                        <span class="referral-stat__hint">
                          Зачислятся при вашей следующей оплате
                        </span>
                      </div>
                    </div>
                    <div class="referral-stat referral-stat--row referral-stat--bonus">
                      <span
                        class="referral-stat__icon-wrap"
                        aria-hidden="true"
                      >
                        <Calendar
                          class="referral-stat__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <div class="referral-stat__body">
                        <span class="referral-stat__value">{{
                          myReferralBonusReceived
                        }}</span>
                        <span class="referral-stat__label">Получено</span>
                        <span class="referral-stat__hint">
                          Уже добавлены к подписке
                        </span>
                      </div>
                    </div>
                  </div>
                </section>

                <section class="referral-section referral-section--share">
                  <h3 class="referral-section-title">Поделиться</h3>
                  <div class="referral-share-stack">
                    <button
                      type="button"
                      class="referral-share-row"
                      :disabled="!effectiveReferralSiteUrl"
                      @click="copyReferralSite"
                    >
                      <span
                        class="referral-share-row__icon-wrap"
                        aria-hidden="true"
                      >
                        <Check
                          v-if="referralCopySite"
                          class="referral-share-row__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                        <Link2
                          v-else
                          class="referral-share-row__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <span class="referral-share-row__text">{{
                        referralCopySite
                          ? 'Скопировано'
                          : 'Скопировать ссылку на сайт'
                      }}</span>
                      <ChevronRight
                        v-if="effectiveReferralSiteUrl && !referralCopySite"
                        class="referral-share-row__chevron"
                        :size="18"
                        :stroke-width="2"
                        aria-hidden="true"
                      />
                    </button>
                    <p
                      v-if="!effectiveReferralSiteUrl"
                      class="hint referral-copy-warn"
                    >
                      Не удалось собрать ссылку: задайте в .env API переменную
                      <code class="inline-code">SITE_ADDRESS</code> (публичный URL сайта).
                    </p>
                    <button
                      type="button"
                      class="referral-share-row"
                      :class="{
                        'referral-share-row--locked': !effectiveReferralTelegramUrl,
                      }"
                      :disabled="!effectiveReferralTelegramUrl"
                      @click="copyReferralTelegram"
                    >
                      <span
                        class="referral-share-row__icon-wrap"
                        aria-hidden="true"
                      >
                        <Check
                          v-if="referralCopyTg"
                          class="referral-share-row__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                        <Send
                          v-else
                          class="referral-share-row__icon"
                          :size="18"
                          :stroke-width="2"
                        />
                      </span>
                      <span class="referral-share-row__text">{{
                        referralCopyTg
                          ? 'Скопировано'
                          : 'Скопировать ссылку на бота (Telegram)'
                      }}</span>
                      <Lock
                        v-if="!effectiveReferralTelegramUrl"
                        class="referral-share-row__lock"
                        :size="16"
                        :stroke-width="2"
                        aria-hidden="true"
                      />
                      <ChevronRight
                        v-else-if="!referralCopyTg"
                        class="referral-share-row__chevron"
                        :size="18"
                        :stroke-width="2"
                        aria-hidden="true"
                      />
                    </button>
                    <p
                      v-if="!effectiveReferralTelegramUrl"
                      class="hint referral-copy-warn"
                    >
                      Ссылка на бота не настроена на сервере — используйте ссылку на сайт.
                    </p>
                  </div>
                </section>
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
  </SitePageLayout>
</template>

<style scoped>
.cabinet-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.35rem;
  margin-bottom: 1rem;
  width: 100%;
  min-width: 0;
}

.cabinet-tab {
  appearance: none;
  margin: 0;
  box-sizing: border-box;
  min-height: 2.5rem;
  padding: 0.5rem 0.65rem;
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

.referral-card-lead {
  margin: -0.35rem 0 0;
  line-height: 1.5;
}

.referral-my-block {
  margin-top: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1.35rem;
  min-width: 0;
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

.referral-section {
  min-width: 0;
}

.referral-section-title {
  margin: 0 0 0.65rem;
  font-size: 0.98rem;
  font-weight: 700;
  color: var(--text-h);
  letter-spacing: normal;
  text-transform: none;
}

.referral-stat-grid {
  display: grid;
  gap: 0.65rem;
  min-width: 0;
}

.referral-stat-grid--3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.referral-stat-grid--2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.referral-stat {
  min-width: 0;
  padding: 0.85rem 0.75rem;
  border-radius: 12px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
}

.referral-stat--row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.referral-stat--bonus {
  align-items: flex-start;
  padding: 0.95rem 0.85rem;
}

.referral-stat__icon-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.35rem;
  height: 2.35rem;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
}

.referral-stat__icon {
  display: block;
}

.referral-stat__body {
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  min-width: 0;
}

.referral-stat__value {
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.15;
  color: var(--text-h);
  font-variant-numeric: tabular-nums;
}

.referral-stat--bonus .referral-stat__value {
  font-size: 1.35rem;
}

.referral-stat__label {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--muted);
  line-height: 1.25;
}

.referral-stat__hint {
  margin-top: 0.15rem;
  font-size: 0.68rem;
  line-height: 1.35;
  color: var(--muted);
}

.referral-section--share {
  padding-top: 0;
  border-top: none;
}

.referral-share-stack {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.referral-share-row {
  appearance: none;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  margin: 0;
  padding: 0.85rem 1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  font: inherit;
  font-size: 0.92rem;
  font-weight: 500;
  color: var(--text-h);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.referral-share-row:hover:not(:disabled) {
  border-color: var(--accent-border);
  background: color-mix(in srgb, var(--accent-soft) 35%, var(--card-bg));
}

.referral-share-row:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.referral-share-row:disabled,
.referral-share-row--locked {
  cursor: not-allowed;
  opacity: 0.72;
}

.referral-share-row__icon-wrap {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
}

.referral-share-row--locked .referral-share-row__icon-wrap {
  background: color-mix(in srgb, var(--muted) 12%, transparent);
  color: var(--muted);
}

.referral-share-row__icon {
  display: block;
}

.referral-share-row__text {
  flex: 1;
  min-width: 0;
  line-height: 1.35;
}

.referral-share-row__chevron,
.referral-share-row__lock {
  flex-shrink: 0;
  color: var(--muted);
}

.referral-copy-warn {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.4;
}

@media (max-width: 520px) {
  .referral-stat-grid--3 {
    gap: 0.45rem;
  }

  .referral-stat--row {
    padding: 0.7rem 0.55rem;
    gap: 0.5rem;
  }

  .referral-stat__icon-wrap {
    width: 2rem;
    height: 2rem;
  }

  .referral-stat__value {
    font-size: 1.05rem;
  }

  .referral-stat--bonus .referral-stat__value {
    font-size: 1.15rem;
  }

  .referral-stat__label {
    font-size: 0.72rem;
  }

  .referral-stat__hint {
    font-size: 0.64rem;
  }

  .referral-share-row {
    padding: 0.75rem 0.85rem;
    font-size: 0.86rem;
  }
}

@media (max-width: 420px) {
  .cabinet-tab {
    min-height: 2.35rem;
    font-size: 0.75rem;
    padding: 0.45rem 0.4rem;
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
  min-width: 0;
}

.cabinet-panel {
  min-width: 0;
  width: 100%;
}

.card {
  min-width: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

@media (max-width: 420px) {
  .card-pad {
    padding: 1.15rem 1rem;
  }
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
  /* minmax(0, 1fr) у второй колонки — иначе грид не сжимает dd ниже min-content и контент вылезает вправо */
  grid-template-columns: 8.5rem minmax(0, 1fr);
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

.connections-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  min-width: 0;
}

.connections-expand {
  width: 100%;
  margin: 0;
}

.connections-expand__summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.35;
  list-style: none;
}

.connections-expand__summary::-webkit-details-marker {
  display: none;
}

.connections-expand__summary::before {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  margin-right: 0.38em;
  border-style: solid;
  border-width: 0.28em 0 0.28em 0.42em;
  border-color: transparent transparent transparent currentColor;
  vertical-align: 0.12em;
  transition: transform 0.15s ease;
}

.connections-expand[open] .connections-expand__summary::before {
  transform: rotate(90deg);
}

.connections-expand__list {
  margin: 0.4rem 0 0;
  padding: 0.35rem 0 0 1rem;
  list-style: disc;
  font-size: 0.82rem;
  border-top: 1px dashed color-mix(in srgb, var(--muted) 40%, transparent);
}

.connections-expand__item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin: 0.22rem 0;
  padding: 0;
  line-height: 1.4;
  word-break: break-word;
}

.connections-expand__line {
  min-width: 0;
  flex: 1;
}

.connections-expand__remove {
  appearance: none;
  margin: 0;
  padding: 0.12rem 0.42rem;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 600;
  line-height: 1.35;
  cursor: pointer;
  flex-shrink: 0;
  color: var(--danger);
  background: transparent;
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  border-radius: 6px;
  transition:
    opacity 0.15s ease,
    border-color 0.15s ease;
}

.connections-expand__remove:hover:not(:disabled) {
  border-color: var(--danger);
}

.connections-expand__remove:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.connections-expand__remove:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.connections-expand__del-err {
  margin: 0.35rem 0 0;
  padding: 0;
  font-size: 0.8rem;
  line-height: 1.35;
  color: var(--danger);
}

.connections-expand__dot {
  color: color-mix(in srgb, var(--muted) 65%, transparent);
  font-weight: 400;
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

.subscription-remaining {
  font-size: 0.85em;
  font-weight: 500;
  color: var(--muted);
  white-space: nowrap;
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

.cabinet-sub-action-stack {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
}

.profile-pay-tg-callout {
  border: 1px solid rgba(129, 140, 248, 0.45);
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.12) 0%,
    rgba(15, 23, 42, 0.35) 100%
  );
}

.profile-pay-tg-callout__title {
  margin: 0 0 0.5rem;
  font-size: 0.98rem;
  font-weight: 600;
  color: var(--text-h);
  line-height: 1.35;
}

.profile-pay-tg-callout__hint {
  margin: 0;
}

.profile-tg-unlinked-hint {
  margin-bottom: 0.65rem;
}

.profile-tg-sync-err {
  margin: 0 0 0.5rem;
  font-size: 0.88rem;
}

.profile-tg-fallback-hint {
  margin: 0.5rem 0 0;
  font-size: 0.82rem;
  line-height: 1.4;
}

.profile-tg-fallback-hint__link {
  color: #229ed9;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.profile-tg-fallback-hint__link:hover {
  color: #1f8fc7;
}

.profile-tg-open-btn {
  margin-top: 0.35rem;
  min-height: 3rem;
  padding: 0.72rem 1rem;
  border-radius: 10px;
}

.profile-tg-open-btn__icon {
  flex-shrink: 0;
  display: flex;
  color: currentColor;
  opacity: 0.98;
}

.profile-tg-open-btn__icon--spin {
  animation: profile-tg-spin 0.85s linear infinite;
}

.profile-tg-open-btn__label {
  min-width: 0;
}

@keyframes profile-tg-spin {
  to {
    transform: rotate(360deg);
  }
}

.profile-pwd {
  margin-top: 1.1rem;
  padding-top: 1.1rem;
  border-top: 1px solid var(--nav-border);
}

.profile-pwd__summary {
  cursor: pointer;
  font-size: 0.98rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.35;
  list-style: none;
  user-select: none;
}

.profile-pwd__summary::-webkit-details-marker {
  display: none;
}

.profile-pwd__summary::before {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  margin-right: 0.38em;
  border-style: solid;
  border-width: 0.28em 0 0.28em 0.42em;
  border-color: transparent transparent transparent currentColor;
  vertical-align: 0.12em;
  transition: transform 0.15s ease;
}

.profile-pwd[open] .profile-pwd__summary::before {
  transform: rotate(90deg);
}

.profile-pwd__summary:focus-visible {
  outline: none;
  border-radius: 6px;
  box-shadow: var(--focus-ring);
}

.profile-pwd__form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  margin-top: 0.85rem;
  padding-top: 0.35rem;
}

.profile-pwd__field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: left;
}

.profile-pwd__label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
}

.profile-pwd__input {
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.profile-pwd__input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.profile-pwd__hint {
  margin: 0;
  font-size: 0.82rem;
}

.profile-pwd__err {
  margin: 0;
  font-size: 0.88rem;
}

.profile-pwd__ok {
  margin: 0;
  font-size: 0.88rem;
  color: var(--accent);
  font-weight: 600;
}

.profile-pwd__submit {
  width: 100%;
  box-sizing: border-box;
  justify-content: center;
  margin-top: 0.15rem;
}

.profile-pwd-missing {
  margin: 1rem 0 0;
  padding-top: 1rem;
  border-top: 1px solid var(--nav-border);
}

.payment-history-card {
  min-width: 0;
}

.payment-history-empty {
  margin: 0;
}

.payment-history-pager {
  margin-bottom: 0.85rem;
}

.payment-history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.payment-history-item {
  padding: 0.75rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface) 55%, var(--card-bg));
}

.payment-history-item__main {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.45rem 0.75rem;
  margin-bottom: 0.25rem;
}

.payment-history-item__amount {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-h);
}

.payment-history-item__months {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--accent);
}

.payment-history-item__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  line-height: 1.35;
  color: var(--muted);
}

.payment-history-item__date {
  font-variant-numeric: tabular-nums;
}

.payment-history-item__dot {
  opacity: 0.55;
}

.payment-history-item__kind,
.payment-history-item__provider {
  white-space: nowrap;
}

.row--telegram dd {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.65rem;
}

.client-btns .client-app-tile {
  min-width: 0;
}

.client-app-tile {
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  gap: 0.65rem;
  min-height: 0;
  padding: 0.62rem 0.75rem;
  border-radius: 14px;
  text-align: left;
  text-decoration: none;
  color: var(--text);
  font-weight: 600;
  font-size: 0.82rem;
  line-height: 1.3;
  background:
    radial-gradient(
      120% 80% at 15% 0%,
      color-mix(in srgb, var(--accent) 14%, transparent),
      transparent 55%
    ),
    radial-gradient(
      100% 70% at 90% 20%,
      color-mix(in srgb, var(--accent-soft) 55%, transparent),
      transparent 50%
    ),
    var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease,
    background 0.18s ease;
}

.client-app-tile:hover {
  border-color: color-mix(in srgb, var(--accent-border) 65%, var(--card-border));
  box-shadow:
    0 4px 14px rgba(0, 0, 0, 0.12),
    0 1px 0 rgba(255, 255, 255, 0.06);
  transform: translateY(-1px);
}

.client-app-tile:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.client-app-tile__logo {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.85rem;
  height: 2.85rem;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  background: transparent;
}

.client-app-tile__logo-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 8px;
}

.client-app-tile__name {
  flex: 1 1 auto;
  min-width: 0;
  display: block;
  padding: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.client-btn {
  display: inline-block;
  padding: 0.62rem 0.85rem;
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
  flex-wrap: nowrap;
  gap: 0.28rem;
  justify-content: center;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  padding-bottom: 0.15rem;
}

.platform-chips::-webkit-scrollbar {
  height: 4px;
}

.platform-chips::-webkit-scrollbar-thumb {
  border-radius: 4px;
  background: var(--nav-border);
}

.platform-chip {
  appearance: none;
  margin: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 0;
  min-width: 0;
  gap: 0.28rem;
  padding: 0.34rem 0.32rem;
  border-radius: var(--radius-pill);
  font: inherit;
  font-size: 0.72rem;
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

.platform-chip__label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.platform-chip__icon {
  display: flex;
  width: 0.92rem;
  height: 0.92rem;
  flex-shrink: 0;
  color: var(--muted);
}

.platform-chip__icon svg {
  width: 100%;
  height: 100%;
}

.platform-chip--active .platform-chip__icon {
  color: var(--accent);
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

.instructions-widget__hint {
  margin-top: -0.35rem;
}

.cabinet-help-action-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-sm);
}

.support-unread-callout {
  margin: 0 0 0.75rem;
  padding: 0.65rem 0.8rem;
  border-radius: 10px;
  font-size: 0.88rem;
  line-height: 1.45;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
}

.cabinet-support-btn-wrap--unread {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent-border) 65%, transparent);
}
</style>
