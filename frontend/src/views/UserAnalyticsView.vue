<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AdminHighlightListLink from '../components/AdminHighlightListLink.vue'
import AdminBarChart from '../components/AdminBarChart.vue'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson, sitePublicUrl, subscriptionPublicUrl } from '../api/client.js'
import { canAccessReferralsAdmin, isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import UserRolePill from '../components/UserRolePill.vue'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import {
  formatTrafficBytes as formatBytes,
  formatTrafficWithLimit,
  isTrafficOverLimit,
} from '../utils/formatTraffic.js'
import { useTableSort } from '../utils/adminTableSort.js'
import {
  formatSubscriptionConnectionOs,
  formatSubscriptionConnectionUserAgent,
} from '../utils/subscription/subscriptionConnectionFormat.js'
import {
  formatLocaleDateRu,
  formatMskApiDateTime,
  formatMskCalendarDayShort,
  formatUtcCalendarDayShort,
} from '../utils/mskDate.js'

const MIB = 1024 * 1024

const route = useRoute()

const loading = ref(false)
const error = ref(null)
const profileError = ref(null)
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const profile = ref(null)
/** @type {import('vue').Ref<object | null>} */
const bundle = ref(null)
/** @type {import('vue').Ref<Array<{ traffic_date: string; cumulative_bytes: number }>>} */
const trafficByDay = ref([])
const trafficByDayError = ref(null)

/** Реферальная ссылка, зафиксированная при регистрации (источник). */
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const sourceReferralLink = ref(null)
const sourceReferralLinkLoading = ref(false)
const sourceReferralLinkError = ref(null)

/** Персональная ссылка пользователя (owner). */
/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const ownedReferralLink = ref(null)
const ownedReferralLinkLoading = ref(false)
const ownedReferralLinkError = ref(null)
const copyHint = ref(null)

/** Пользователи с users.referral_link_id = личная ссылка текущей карточки. */
/** @type {import('vue').Ref<Array<Record<string, unknown>>>} */
const refereeUsers = ref([])
const refereeUsersLoading = ref(false)
const refereeUsersError = ref(null)

/** @type {import('vue').Ref<Array<Record<string, unknown>>>} */
const paymentLedgerItems = ref([])
const paymentLedgerTotal = ref(0)
const paymentsLedgerError = ref(null)

/** @type {import('vue').Ref<Array<Record<string, unknown>>>} */
const taskLedgerItems = ref([])
const taskLedgerTotal = ref(0)
const tasksLedgerError = ref(null)

const paymentLedgerSortAccessors = {
  id: (r) => Number(r.id) || 0,
  user_id: (r) => Number(r.user_id) || 0,
  amount: (r) => Number(r.amount) || 0,
  months: (r) => Number(r.months) || 0,
  provider: (r) => String(r.provider ?? '').toLowerCase(),
  payment_kind: (r) => String(r.payment_kind ?? '').toLowerCase(),
  provider_webhook: (r) => JSON.stringify(r.provider_webhook ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
}

const {
  sortKey: paySortKey,
  sortDir: paySortDir,
  sortedRows: sortedPaymentLedgerRows,
  toggleSort: togglePayLedgerSort,
} = useTableSort(paymentLedgerItems, paymentLedgerSortAccessors)

const taskLedgerSortAccessors = {
  id: (r) => Number(r.id) || 0,
  type: (r) => String(r.type ?? '').toLowerCase(),
  user_id: (r) => Number(r.user_id) || 0,
  referee_id: (r) => (r.referee_id == null ? -1 : Number(r.referee_id)),
  bonus_days: (r) => (r.bonus_days == null ? -1 : Number(r.bonus_days)),
  early_payment_bonus_days: (r) =>
    r.early_payment_bonus_days == null ? -1 : Number(r.early_payment_bonus_days),
  paid_months: (r) => (r.paid_months == null ? -1 : Number(r.paid_months)),
  status: (r) => String(r.status ?? '').toLowerCase(),
  created_at: (r) => String(r.created_at ?? ''),
  done_at: (r) => String(r.done_at ?? ''),
}

const {
  sortKey: taskSortKey,
  sortDir: taskSortDir,
  sortedRows: sortedTaskLedgerRows,
  toggleSort: toggleTaskLedgerSort,
} = useTableSort(taskLedgerItems, taskLedgerSortAccessors)

const refereeSortAccessors = {
  id: (u) => Number(u.id) || 0,
  email: (u) => String(u.email ?? '').toLowerCase(),
  telegram: (u) => u.telegram_id ?? -1,
  registered_at: (u) => Date.parse(String(u.registered_at ?? '')) || 0,
  subscription_until: (u) => Date.parse(String(u.subscription_until ?? '')) || 0,
  traffic: (u) => Number(u.total_traffic_bytes) || 0,
  devices: (u) => Number(u.subscription_devices_count) || 0,
}

const {
  sortKey: refereeSortKey,
  sortDir: refereeSortDir,
  sortedRows: sortedRefereeRows,
  toggleSort: toggleRefereeSort,
} = useTableSort(refereeUsers, refereeSortAccessors)

const userId = computed(() => {
  const raw = route.params.userId
  const n = parseInt(String(raw), 10)
  return Number.isFinite(n) ? n : null
})

const userAnalyticsBackTo = computed(() => '/admin/users/analytics')

const userAnalyticsBackLabel = computed(() => '← Клиенты')

const isAdmin = computed(() => isAdminRole(getSessionRole()))
const canEditTrafficLimit = computed(() =>
  canAccessReferralsAdmin(getSessionRole()),
)

const profileEditing = ref(false)
const profileSaving = ref(false)
const profileEditError = ref(null)
const clearTelegramBusy = ref(false)

const formTelegramId = ref('')
const formSubUntil = ref('')
const formAccountRole = ref('client')
const formRegisteredAt = ref('')
const formTrafficLimitGib = ref('')
const formReferralBonusPolicy = ref('default')

const TRAFFIC_GIB_BYTES = 1024 ** 3

const profileHasTelegramData = computed(() => {
  const p = profile.value
  if (!p) return false
  if (p.telegram_id != null) return true
  const props = p.telegram_properties
  if (!props || typeof props !== 'object') return false
  return Object.keys(props).length > 0
})

function formatDateTime(d) {
  return formatMskApiDateTime(d, { dateStyle: 'short', timeStyle: 'short' })
}

function isoYyyyMmDdToRuDmy(iso) {
  const s = String(iso ?? '').trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return ''
  const [y, m, d] = s.split('-').map(Number)
  if (!y || !m || !d) return ''
  return `${String(d).padStart(2, '0')}.${String(m).padStart(2, '0')}.${y}`
}

function utcIsoToRuDmy(iso) {
  if (iso == null || iso === '') return ''
  const t = Date.parse(String(iso))
  if (Number.isNaN(t)) return ''
  const d = new Date(t)
  const day = String(d.getUTCDate()).padStart(2, '0')
  const month = String(d.getUTCMonth() + 1).padStart(2, '0')
  const y = d.getUTCFullYear()
  return `${day}.${month}.${y}`
}

function dateFormToIsoOrNull(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return null
  const ru = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(s)
  if (ru) {
    const d = Number(ru[1])
    const m = Number(ru[2])
    const y = Number(ru[3])
    if (m < 1 || m > 12 || d < 1 || d > 31 || y < 1 || y > 9999) return null
    const dt = new Date(Date.UTC(y, m - 1, d))
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== m - 1 ||
      dt.getUTCDate() !== d
    ) {
      return null
    }
    return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split('-').map(Number)
    const dt = new Date(Date.UTC(y, m - 1, d))
    if (
      dt.getUTCFullYear() !== y ||
      dt.getUTCMonth() !== m - 1 ||
      dt.getUTCDate() !== d
    ) {
      return null
    }
    return s
  }
  return null
}

function registrationDateTimeUtcOrNull(raw) {
  const d = dateFormToIsoOrNull(raw)
  if (d === null) return null
  return `${d}T00:00:00.000Z`
}

function normalizeTelegramId(raw) {
  const s = String(raw ?? '').trim().replace(/^@/, '')
  if (!s) return null
  if (!/^\d{1,19}$/.test(s)) return null
  return Number(s)
}

function trafficLimitBytesToFormGib(bytes) {
  if (bytes == null || bytes === '') return ''
  const n = Number(bytes)
  if (!Number.isFinite(n) || n <= 0) return ''
  return String(Math.round(n / TRAFFIC_GIB_BYTES))
}

function trafficLimitFormGibToBytes(raw) {
  const s = String(raw ?? '').trim().replace(',', '.')
  if (!s) return null
  const gib = Number.parseFloat(s)
  if (!Number.isFinite(gib) || gib < 0 || gib > 10_000) return undefined
  return Math.round(gib * TRAFFIC_GIB_BYTES)
}

function fillProfileFormFromProfile() {
  const p = profile.value
  if (!p) return
  formTelegramId.value =
    p.telegram_id != null ? String(p.telegram_id) : ''
  const su = p.subscription_until
  formSubUntil.value =
    su != null && String(su).trim()
      ? isoYyyyMmDdToRuDmy(String(su).slice(0, 10))
      : ''
  formAccountRole.value =
    p.account_role === 'manager' || p.account_role === 'admin'
      ? p.account_role
      : 'client'
  formRegisteredAt.value = utcIsoToRuDmy(p.registered_at)
  formTrafficLimitGib.value = trafficLimitBytesToFormGib(p.traffic_limit_bytes)
  formReferralBonusPolicy.value =
    p.referral_bonus_policy === 'fixed_first_payment_instant'
      ? 'fixed_first_payment_instant'
      : 'default'
}

function openProfileEdit() {
  profileEditError.value = null
  fillProfileFormFromProfile()
  profileEditing.value = true
}

function cancelProfileEdit() {
  if (profileSaving.value || clearTelegramBusy.value) return
  profileEditError.value = null
  profileEditing.value = false
}

async function reloadProfileCard() {
  const uid = userId.value
  if (uid == null) return
  const r = await fetchJson(`/api/users/${uid}`)
  profile.value = r && typeof r === 'object' ? r : null
}

async function saveProfileEdit() {
  const uid = userId.value
  if (uid == null) return
  profileSaving.value = true
  profileEditError.value = null
  try {
    const trafficLimitBytes = trafficLimitFormGibToBytes(formTrafficLimitGib.value)
    if (trafficLimitBytes === undefined) {
      profileEditError.value =
        'Лимит трафика: укажите неотрицательное число гигабайт (до 10000) или очистите поле'
      return
    }
    if (!isAdmin.value) {
      await fetchJson(`/api/users/${uid}`, {
        method: 'PATCH',
        body: JSON.stringify({ traffic_limit_bytes: trafficLimitBytes }),
      })
      profileEditing.value = false
      await reloadProfileCard()
      return
    }
    const subRaw = String(formSubUntil.value ?? '').trim()
    const subIso = subRaw === '' ? null : dateFormToIsoOrNull(formSubUntil.value)
    if (subRaw !== '' && subIso === null) {
      profileEditError.value = 'Подписка до: укажите дату как ДД.ММ.ГГГГ'
      return
    }
    const regRaw = String(formRegisteredAt.value ?? '').trim()
    if (regRaw !== '' && dateFormToIsoOrNull(formRegisteredAt.value) === null) {
      profileEditError.value =
        'Дата регистрации: укажите дату как ДД.ММ.ГГГГ или очистите поле'
      return
    }
    const tgRaw = String(formTelegramId.value ?? '').trim()
    const tgId = tgRaw === '' ? null : normalizeTelegramId(formTelegramId.value)
    if (tgRaw !== '' && tgId === null) {
      profileEditError.value =
        'Telegram ID: укажите числовой идентификатор или очистите поле'
      return
    }
    await fetchJson(`/api/users/${uid}`, {
      method: 'PATCH',
      body: JSON.stringify({
        telegram_id: tgId,
        subscription_until: subIso,
        account_role: formAccountRole.value,
        registered_at: registrationDateTimeUtcOrNull(formRegisteredAt.value),
        traffic_limit_bytes: trafficLimitBytes,
        referral_bonus_policy: formReferralBonusPolicy.value,
      }),
    })
    profileEditing.value = false
    await reloadProfileCard()
  } catch (e) {
    profileEditError.value = e.message || String(e)
  } finally {
    profileSaving.value = false
  }
}

async function clearProfileTelegram() {
  const uid = userId.value
  if (uid == null || !profileHasTelegramData.value) return
  const p = profile.value
  const noEmail =
    p &&
    (p.email == null ||
      (typeof p.email === 'string' && p.email.trim() === ''))
  const warn =
    noEmail ?
      '\n\nУ пользователя нет email — после сброса Telegram войти в аккаунт будет нельзя.'
    : ''
  if (
    !window.confirm(
      `Сбросить привязку Telegram (числовой ID и профиль в JSON) у пользователя #${uid}?${warn}`,
    )
  ) {
    return
  }
  clearTelegramBusy.value = true
  profileEditError.value = null
  try {
    await fetchJson(`/api/users/${uid}`, {
      method: 'PATCH',
      body: JSON.stringify({
        telegram_id: null,
        telegram_properties: null,
      }),
    })
    formTelegramId.value = ''
    await reloadProfileCard()
    fillProfileFormFromProfile()
  } catch (e) {
    profileEditError.value = e.message || String(e)
  } finally {
    clearTelegramBusy.value = false
  }
}

function telegramUsername(p) {
  const props = p?.telegram_properties
  if (!props || typeof props !== 'object') return null
  const u = props.username
  if (typeof u !== 'string' || !u.trim()) return null
  const s = u.trim().replace(/^@+/, '')
  return s ? `@${s}` : null
}

/** Ячейка Telegram в таблице приглашённых (как в аналитике клиентов). */
function refereeTelegramCell(u) {
  const props = u?.telegram_properties
  const nestedUsername =
    props && typeof props === 'object'
      ? props.username ?? props.user_name ?? props.telegram_username
      : null
  const directUsername = u?.username ?? u?.user_name ?? u?.telegram_username
  const username = directUsername ?? nestedUsername
  if (username != null && username !== '') {
    const s = String(username)
    return s.startsWith('@') ? s : `@${s}`
  }
  if (u.telegram_id != null && u.telegram_id !== '') {
    return String(u.telegram_id)
  }
  return '—'
}

const trafficDayLabels = computed(() =>
  trafficByDay.value.map((r) => formatUtcCalendarDayShort(r.traffic_date)),
)

const trafficDayDatasets = computed(() => {
  const mib = trafficByDay.value.map(
    (r) => Number(r.cumulative_bytes ?? r.consumed_bytes ?? 0) / MIB,
  )
  return [
    {
      label: 'Накопленно (включая этот день)',
      data: mib,
      rgb: rgbTupleFromVar('--accent', '#58d68d'),
    },
  ]
})

function trafficDayFormatYTick(mib) {
  const n = Number(mib)
  if (!Number.isFinite(n) || n <= 0) return '0'
  if (n >= 1024) return `${(n / 1024).toFixed(n >= 10240 ? 0 : 1)} ГиБ`
  return `${n < 1 ? n.toFixed(2) : n.toFixed(1)} МиБ`
}

function trafficDayTooltipTitle(i) {
  const iso = trafficByDay.value[i]?.traffic_date
  return iso ? formatUtcCalendarDayShort(iso) : ''
}

function trafficDayTooltipLabel(ctx) {
  const i = ctx.dataIndex
  const row = trafficByDay.value[i]
  const b = row
    ? Number(row.cumulative_bytes ?? row.consumed_bytes ?? 0)
    : 0
  return `Накопленно: ${formatBytes(b)}`
}

function serverLabel(row) {
  const n = row.name && String(row.name).trim()
  if (n) return n
  return `${row.host}:${row.port}`
}

function formatPaymentAmount(v) {
  const n = Number(v)
  if (Number.isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function paymentKindLabel(k) {
  const s = String(k ?? '')
  if (s === 'subscription') return 'Подписка'
  if (s === 'one_time') return 'Разовая'
  return s || '—'
}

function formatRefTableDate(iso) {
  return formatMskApiDateTime(iso, { dateStyle: 'short', timeStyle: 'medium' })
}

function referralRowToken(r) {
  if (r == null) return ''
  const raw = r.token ?? r.Token
  if (raw == null || raw === '') return ''
  const s = typeof raw === 'string' ? raw.trim() : String(raw).trim()
  if (!s || s === 'NaN') return ''
  return s
}

function fallbackSiteEntry(token) {
  const base = sitePublicUrl().replace(/\/$/, '')
  const t =
    token == null || token === ''
      ? ''
      : typeof token === 'string'
        ? token.trim()
        : String(token).trim()
  if (!t || t === 'NaN') return ''
  return `${base}/?ref=${encodeURIComponent(t)}`
}

/** Публичные URL из API или сборка с фронта (snake_case / camelCase). */
function siteUrlForReferralRow(r) {
  const raw =
    r.site_entry_url ??
    r.siteEntryUrl ??
    ''
  const fromApi = typeof raw === 'string' ? raw.trim() : ''
  if (
    fromApi
    && fromApi.includes('ref=')
    && !fromApi.includes('ref=NaN')
    && !fromApi.includes('ref=undefined')
  ) {
    return fromApi
  }
  const tok = referralRowToken(r)
  return tok ? fallbackSiteEntry(tok) : ''
}

function telegramUrlForReferralRow(r) {
  const deep = r.telegram_deep_link ?? r.telegramDeepLink ?? ''
  return typeof deep === 'string' ? deep.trim() : ''
}

function referralEntityDisplayId(row) {
  if (row == null || row.id == null || row.id === '') return '—'
  const n = Number(row.id)
  return Number.isFinite(n) ? n : String(row.id)
}

/** Для query-параметров; при невалидном id — null. */
function referralEntityNumericId(row) {
  if (row == null || row.id == null || row.id === '') return null
  const n = Number(row.id)
  return Number.isFinite(n) ? n : null
}

async function copyReferralUrl(url) {
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    copyHint.value = 'Скопировано'
    window.setTimeout(() => {
      copyHint.value = null
    }, 2000)
  } catch {
    copyHint.value = null
  }
}

async function loadSourceReferralLink() {
  sourceReferralLinkError.value = null
  sourceReferralLink.value = null
  const rid = profile.value?.referral_link_id
  if (rid == null) {
    sourceReferralLinkLoading.value = false
    return
  }
  sourceReferralLinkLoading.value = true
  try {
    sourceReferralLink.value = await fetchJson(`/api/referral-links/${rid}`)
  } catch (e) {
    sourceReferralLinkError.value = e.message || String(e)
  } finally {
    sourceReferralLinkLoading.value = false
  }
}

async function loadOwnedReferralLink() {
  ownedReferralLinkError.value = null
  ownedReferralLink.value = null
  const oid = profile.value?.owned_referral_link_id
  if (oid == null) {
    ownedReferralLinkLoading.value = false
    return
  }
  ownedReferralLinkLoading.value = true
  try {
    ownedReferralLink.value = await fetchJson(`/api/referral-links/${oid}`)
  } catch (e) {
    ownedReferralLinkError.value = e.message || String(e)
  } finally {
    ownedReferralLinkLoading.value = false
  }
}

async function loadRefereesByOwnedLink() {
  refereeUsersError.value = null
  refereeUsers.value = []
  const oid = profile.value?.owned_referral_link_id
  if (oid == null) {
    refereeUsersLoading.value = false
    return
  }
  refereeUsersLoading.value = true
  try {
    const data = await fetchJson(
      `/api/users?referral_link_id=${encodeURIComponent(String(oid))}&limit=500&offset=0`,
    )
    refereeUsers.value = Array.isArray(data?.items) ? data.items : []
  } catch (e) {
    refereeUsersError.value = e.message || String(e)
  } finally {
    refereeUsersLoading.value = false
  }
}

const serverBarLabels = computed(() => {
  const b = bundle.value
  if (!b?.servers?.length) return []
  return [...b.servers]
    .sort((a, b) => b.total_bytes - a.total_bytes)
    .map((r) => serverLabel(r))
})

const serverBarDatasets = computed(() => {
  const b = bundle.value
  if (!b?.servers?.length) return []
  const rows = [...b.servers].sort((a, b) => b.total_bytes - a.total_bytes)
  const mib = (x) => x / (1024 * 1024)
  return [
    {
      label: 'К клиенту (down), МиБ',
      data: rows.map((r) => mib(r.down_bytes)),
      rgb: /** @type {[number, number, number]} */ ([88, 214, 141]),
    },
    {
      label: 'От клиента (up), МиБ',
      data: rows.map((r) => mib(r.up_bytes)),
      rgb: /** @type {[number, number, number]} */ ([69, 179, 157]),
    },
  ]
})

function formatServerBarValueTick(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  return n.toLocaleString('ru-RU', { maximumFractionDigits: n < 10 ? 2 : 1 })
}

/** Лимит строк для платежей/задач на странице одного пользователя (совпадает с шагом пагинации в staff-вью). */
const LEDGER_PAGE_LIMIT = 200

function resetAnalyticsPageState() {
  error.value = null
  profileError.value = null
  bundle.value = null
  profile.value = null
  trafficByDay.value = []
  trafficByDayError.value = null
  sourceReferralLink.value = null
  sourceReferralLinkError.value = null
  sourceReferralLinkLoading.value = false
  ownedReferralLink.value = null
  ownedReferralLinkError.value = null
  ownedReferralLinkLoading.value = false
  refereeUsers.value = []
  refereeUsersError.value = null
  refereeUsersLoading.value = false
  copyHint.value = null
  profileEditing.value = false
  profileEditError.value = null
  paymentLedgerItems.value = []
  paymentLedgerTotal.value = 0
  paymentsLedgerError.value = null
  taskLedgerItems.value = []
  taskLedgerTotal.value = 0
  tasksLedgerError.value = null
}

async function load() {
  if (userId.value == null) {
    resetAnalyticsPageState()
    error.value = 'Некорректный id пользователя'
    return
  }
  loading.value = true
  resetAnalyticsPageState()
  try {
    const uid = userId.value
    const [r0, r1, r2, rPay, rTasks] = await Promise.allSettled([
      fetchJson(`/api/users/${uid}`),
      fetchJson(`/api/users/${uid}/traffic-by-server`),
      fetchJson(`/api/users/${uid}/traffic-by-day`),
      fetchJson(
        `/api/admin/payments?limit=${LEDGER_PAGE_LIMIT}&offset=0&user_id=${uid}`,
      ),
      fetchJson(
        `/api/admin/tasks?limit=${LEDGER_PAGE_LIMIT}&offset=0&user_id=${uid}`,
      ),
    ])
    if (r0.status === 'fulfilled') {
      profile.value =
        r0.value && typeof r0.value === 'object' ? r0.value : null
    } else {
      profile.value = null
      profileError.value =
        r0.reason?.message ||
        String(r0.reason ?? 'Ошибка загрузки карточки пользователя')
    }
    if (r1.status === 'fulfilled') {
      bundle.value = r1.value
    } else {
      bundle.value = null
      error.value =
        r1.reason?.message ||
        String(r1.reason ?? 'Ошибка загрузки сводки по узлам')
    }
    if (r2.status === 'fulfilled') {
      trafficByDay.value = Array.isArray(r2.value) ? r2.value : []
    } else {
      trafficByDay.value = []
      trafficByDayError.value =
        r2.reason?.message ||
        String(r2.reason ?? 'Ошибка загрузки трафика по дням')
    }
    if (rPay.status === 'fulfilled') {
      const d = rPay.value
      paymentLedgerItems.value = Array.isArray(d?.items) ? d.items : []
      paymentLedgerTotal.value = Number(d?.total) || 0
    } else {
      paymentLedgerItems.value = []
      paymentLedgerTotal.value = 0
      paymentsLedgerError.value =
        rPay.reason?.message ||
        String(rPay.reason ?? 'Ошибка загрузки платежей')
    }
    if (rTasks.status === 'fulfilled') {
      const d = rTasks.value
      taskLedgerItems.value = Array.isArray(d?.items) ? d.items : []
      taskLedgerTotal.value = Number(d?.total) || 0
    } else {
      taskLedgerItems.value = []
      taskLedgerTotal.value = 0
      tasksLedgerError.value =
        rTasks.reason?.message ||
        String(rTasks.reason ?? 'Ошибка загрузки задач')
    }
    if (profile.value) {
      await Promise.all([
        loadSourceReferralLink(),
        loadOwnedReferralLink(),
        loadRefereesByOwnedLink(),
      ])
    }
  } finally {
    loading.value = false
  }
}

watch(
  () => route.params.userId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Аналитика пользователя"
      :back-to="userAnalyticsBackTo"
      :back-label="userAnalyticsBackLabel"
    />

    <p v-if="profileError" class="banner-err">{{ profileError }}</p>
    <p v-if="error" class="banner-err">{{ error }}</p>
    <p v-if="loading" class="loading-line">Загрузка…</p>

    <div v-if="!loading && profile" class="user-profile glass">
      <div class="profile-head">
        <h2 class="profile-title">Данные пользователя</h2>
        <div v-if="canEditTrafficLimit" class="profile-head__actions">
          <template v-if="profileEditing">
            <button
              type="button"
              class="btn-primary btn-tiny"
              :disabled="profileSaving || clearTelegramBusy"
              @click="saveProfileEdit"
            >
              {{ profileSaving ? 'Сохранение…' : 'Сохранить' }}
            </button>
            <button
              type="button"
              class="btn-secondary btn-tiny"
              :disabled="profileSaving || clearTelegramBusy"
              @click="cancelProfileEdit"
            >
              Отмена
            </button>
          </template>
          <button
            v-else
            type="button"
            class="btn-secondary btn-tiny"
            @click="openProfileEdit"
          >
            Редактировать
          </button>
        </div>
      </div>
      <p v-if="profileEditError" class="banner-err profile-edit-err">{{
        profileEditError
      }}</p>
      <dl class="kv-grid">
        <dt>ID</dt>
        <dd class="mono">{{ profile.id }}</dd>
        <dt>Email</dt>
        <dd>{{ profile.email && String(profile.email).trim() ? profile.email : '—' }}</dd>
        <template v-if="isAdmin">
          <dt>Роль</dt>
          <dd>
            <select
              v-if="profileEditing"
              v-model="formAccountRole"
              class="profile-field-input profile-field-select"
              aria-label="Роль пользователя"
            >
              <option value="client">Клиент (VPN)</option>
              <option value="manager">Менеджер (реферальные токены)</option>
              <option value="admin">Администратор</option>
            </select>
            <UserRolePill v-else :role="profile.account_role" />
          </dd>
          <dt>Ссылка подписки</dt>
          <dd class="subscription-link-cell">
            <template v-if="profile.token">
              <span class="mono subscription-link-cell__token">{{
                profile.token
              }}</span>
              <a
                class="subscription-link-cell__url"
                :href="subscriptionPublicUrl(profile.token)"
                target="_blank"
                rel="noopener noreferrer"
              >{{ subscriptionPublicUrl(profile.token) }}</a>
              <button
                type="button"
                class="btn-secondary btn-tiny"
                aria-label="Копировать ссылку подписки в буфер обмена"
                @click="copyReferralUrl(subscriptionPublicUrl(profile.token))"
              >
                Копировать
              </button>
            </template>
            <span v-else class="muted-dash">—</span>
          </dd>
        </template>
        <dt>Telegram ID</dt>
        <dd class="mono">
          <input
            v-if="isAdmin && profileEditing"
            v-model="formTelegramId"
            type="text"
            class="profile-field-input"
            inputmode="numeric"
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
            placeholder="например 123456789"
          />
          <template v-else>
            {{ profile.telegram_id != null ? profile.telegram_id : '—' }}
          </template>
        </dd>
        <dt>Username в Telegram</dt>
        <dd>{{ telegramUsername(profile) || '—' }}</dd>
        <dt>Профиль Telegram (JSON)</dt>
        <dd>
          <pre v-if="profile.telegram_properties" class="json-pre">{{
            JSON.stringify(profile.telegram_properties, null, 2)
          }}</pre>
          <span v-else class="muted-dash">—</span>
          <button
            v-if="isAdmin && profileEditing && profileHasTelegramData"
            type="button"
            class="btn-secondary btn-tiny profile-telegram-clear"
            :disabled="profileSaving || clearTelegramBusy"
            @click="clearProfileTelegram"
          >
            {{ clearTelegramBusy ? 'Сброс…' : 'Сбросить Telegram' }}
          </button>
        </dd>
        <dt>Регистрация</dt>
        <dd>
          <input
            v-if="isAdmin && profileEditing"
            v-model="formRegisteredAt"
            type="text"
            class="profile-field-input profile-field-date"
            inputmode="numeric"
            maxlength="10"
            placeholder="ДД.ММ.ГГГГ"
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
          />
          <template v-else>{{ formatDateTime(profile.registered_at) }}</template>
        </dd>
        <dt>Подписка до</dt>
        <dd>
          <input
            v-if="isAdmin && profileEditing"
            v-model="formSubUntil"
            type="text"
            class="profile-field-input profile-field-date"
            inputmode="numeric"
            maxlength="10"
            placeholder="ДД.ММ.ГГГГ"
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
          />
          <template v-else>{{
            formatLocaleDateRu(profile.subscription_until)
          }}</template>
        </dd>
        <template v-if="isAdmin">
          <dt>Реферальные бонусы</dt>
          <dd>
            <select
              v-if="profileEditing"
              v-model="formReferralBonusPolicy"
              class="profile-field-input profile-field-select"
              aria-label="Политика реферальных бонусов"
            >
              <option value="default">
                Стандарт: месяцы × коэффициент, при своей оплате
              </option>
              <option value="fixed_first_payment_instant">
                +20 дней при первой оплате друга, сразу
              </option>
            </select>
            <template v-else>
              {{
                profile.referral_bonus_policy === 'fixed_first_payment_instant'
                  ? '+20 дней при первой оплате друга, сразу'
                  : 'Стандарт'
              }}
            </template>
          </dd>
        </template>
        <dt>Трафик</dt>
        <dd
          class="mono"
          :class="{ 'traffic-over-limit': profile && isTrafficOverLimit(profile) }"
        >
          <template v-if="canEditTrafficLimit && profileEditing">
            <input
              v-model="formTrafficLimitGib"
              type="number"
              class="profile-field-input profile-field-traffic"
              min="0"
              max="10000"
              step="1"
              inputmode="decimal"
              placeholder="без лимита"
              autocomplete="off"
            />
            <span class="profile-field-hint">
              Сейчас:
              {{
                formatTrafficWithLimit(
                  profile.total_traffic_bytes ?? 0,
                  profile.traffic_limit_bytes,
                )
              }}
            </span>
          </template>
          <template v-else>
            {{
              formatTrafficWithLimit(
                profile.total_traffic_bytes ?? 0,
                profile.traffic_limit_bytes,
              )
            }}
            <span
              v-if="profile.traffic_limit_bytes == null"
              class="traffic-limit-hint"
            >без лимита</span>
          </template>
        </dd>
        <dt>Устройств по подписке</dt>
        <dd class="kv-dd-devices">
          <span class="mono kv-dd-devices__count">{{
            profile.subscription_devices_count ?? 0
          }}</span>
          <details
            v-if="profile.subscription_devices?.length"
            class="connections-expand panel-subscription-devices"
          >
            <summary class="connections-expand__summary">Устройства</summary>
            <ul class="connections-expand__list" role="list">
              <li
                v-for="conn in profile.subscription_devices"
                :key="conn.id"
                class="connections-expand__item connections-expand__item--readonly"
              >
                <div class="connections-expand__line mono">
                  <span class="connections-expand__os">{{
                    formatSubscriptionConnectionOs(conn.os)
                  }}</span>
                  <span class="connections-expand__dot" aria-hidden="true">
                    ·
                  </span>
                  <span class="connections-expand__ua">{{
                    formatSubscriptionConnectionUserAgent(conn.user_agent)
                  }}</span>
                </div>
              </li>
            </ul>
          </details>
        </dd>
      </dl>

      <div class="personal-ref">
        <h3 class="personal-ref__title">Источник</h3>
        <p
          v-if="profile.referral_link_id == null"
          class="personal-ref__empty"
        >
          Не указан — регистрация без реферальной ссылки.
        </p>
        <template v-else>
          <p v-if="sourceReferralLinkError" class="banner-err personal-ref__err">{{
            sourceReferralLinkError
          }}</p>
          <p
            v-else-if="sourceReferralLinkLoading"
            class="personal-ref__hint muted-inline"
          >
            Загрузка…
          </p>
          <template v-else-if="sourceReferralLink">
            <p v-if="copyHint" class="copy-hint personal-ref__copy-hint">{{
              copyHint
            }}</p>
            <AdminTableWrap
              class="personal-ref__table-wrap"
              aria-label="Реферальная ссылка при регистрации (источник)"
            >
              <table class="admin-table">
                <thead>
                  <tr>
                    <th class="admin-th--num">ID</th>
                    <th>Токен</th>
                    <th>Источник</th>
                    <th class="admin-th--num">User id</th>
                    <th>Сайт</th>
                    <th>Telegram</th>
                    <th class="admin-th--num">Клики</th>
                    <th class="admin-th--num">Рег.</th>
                    <th class="admin-th--num">Оплаты</th>
                    <th>Создан</th>
                    <th class="row-actions-head">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td class="num">{{
                      referralEntityDisplayId(sourceReferralLink)
                    }}</td>
                    <td class="mono-cell">{{
                      referralRowToken(sourceReferralLink) || '—'
                    }}</td>
                    <td>
                      <span
                        class="pill pill-mono"
                        :title="sourceReferralLink.owner_kind"
                      >{{ sourceReferralLink.owner_kind }}</span>
                    </td>
                    <td class="owner-user-id-cell">
                      <span class="owner-user-id-inner">
                        <template
                          v-if="sourceReferralLink.owner_user_id != null"
                        >
                          <span>{{ sourceReferralLink.owner_user_id }}</span>
                          <AdminHighlightListLink
                            list="users"
                            :highlight="sourceReferralLink.owner_user_id"
                          />
                        </template>
                        <template v-else>—</template>
                      </span>
                    </td>
                    <td class="link-actions">
                      <button
                        type="button"
                        class="btn-secondary btn-tiny"
                        title="Копировать ссылку на сайт (?ref)"
                        @click="
                          copyReferralUrl(
                            siteUrlForReferralRow(sourceReferralLink),
                          )
                        "
                      >
                        Копировать
                      </button>
                    </td>
                    <td class="link-actions">
                      <button
                        v-if="telegramUrlForReferralRow(sourceReferralLink)"
                        type="button"
                        class="btn-secondary btn-tiny"
                        title="Копировать ссылку на Telegram-бота (?start)"
                        @click="
                          copyReferralUrl(
                            telegramUrlForReferralRow(sourceReferralLink),
                          )
                        "
                      >
                        Копировать
                      </button>
                      <span v-else class="muted-inline">—</span>
                    </td>
                    <td class="num">{{ sourceReferralLink.clicks_count }}</td>
                    <td class="num">{{
                      sourceReferralLink.registrations_count
                    }}</td>
                    <td class="num">{{ sourceReferralLink.payments_count }}</td>
                    <td class="date-cell">{{
                      formatRefTableDate(sourceReferralLink.created_at)
                    }}</td>
                    <td class="col-actions">
                      <RouterLink
                        v-if="referralEntityNumericId(sourceReferralLink) != null"
                        class="btn-secondary btn-tiny ref-list-link"
                        :to="{
                          path: '/admin/referrals',
                          query: {
                            highlight: String(
                              referralEntityNumericId(sourceReferralLink),
                            ),
                          },
                        }"
                      >
                        В списке токенов
                      </RouterLink>
                      <span v-else class="muted-inline">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </AdminTableWrap>
          </template>
        </template>
      </div>
    </div>

    <div
      v-if="!loading && profile"
      class="referral-widget glass"
    >
      <h2 class="referral-widget__title">Личная реферальная ссылка</h2>
      <p
        v-if="profile.owned_referral_link_id == null"
        class="referral-widget__empty"
      >
        Ещё не создана.
      </p>
      <template v-else>
        <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
        <p v-if="ownedReferralLinkError" class="banner-err referral-widget__err">{{
          ownedReferralLinkError
        }}</p>
        <AdminTableWrap
          v-if="!ownedReferralLinkError"
          aria-label="Личная реферальная ссылка пользователя"
        >
          <table class="admin-table">
            <thead>
              <tr>
                <th class="admin-th--num">ID</th>
                <th>Токен</th>
                <th>Источник</th>
                <th class="admin-th--num">User id</th>
                <th>Сайт</th>
                <th>Telegram</th>
                <th class="admin-th--num">Клики</th>
                <th class="admin-th--num">Рег.</th>
                <th class="admin-th--num">Оплаты</th>
                <th>Создан</th>
                <th class="row-actions-head">Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="ownedReferralLinkLoading">
                <td colspan="11" class="muted-cell">Загрузка…</td>
              </tr>
              <tr v-else-if="ownedReferralLink">
                <td class="num">{{ referralEntityDisplayId(ownedReferralLink) }}</td>
                <td class="mono-cell">{{ referralRowToken(ownedReferralLink) || '—' }}</td>
                <td>
                  <span
                    class="pill pill-mono"
                    :title="ownedReferralLink.owner_kind"
                  >{{ ownedReferralLink.owner_kind }}</span>
                </td>
                <td class="owner-user-id-cell">
                  <span class="owner-user-id-inner">
                    <template v-if="ownedReferralLink.owner_user_id != null">
                      <span>{{ ownedReferralLink.owner_user_id }}</span>
                      <AdminHighlightListLink
                        list="users"
                        :highlight="ownedReferralLink.owner_user_id"
                      />
                    </template>
                    <template v-else>—</template>
                  </span>
                </td>
                <td class="link-actions">
                  <button
                    type="button"
                    class="btn-secondary btn-tiny"
                    title="Копировать ссылку на сайт (?ref)"
                    @click="
                      copyReferralUrl(siteUrlForReferralRow(ownedReferralLink))
                    "
                  >
                    Копировать
                  </button>
                </td>
                <td class="link-actions">
                  <button
                    v-if="telegramUrlForReferralRow(ownedReferralLink)"
                    type="button"
                    class="btn-secondary btn-tiny"
                    title="Копировать ссылку на Telegram-бота (?start)"
                    @click="
                      copyReferralUrl(
                        telegramUrlForReferralRow(ownedReferralLink),
                      )
                    "
                  >
                    Копировать
                  </button>
                  <span v-else class="muted-inline">—</span>
                </td>
                <td class="num">{{ ownedReferralLink.clicks_count }}</td>
                <td class="num">{{ ownedReferralLink.registrations_count }}</td>
                <td class="num">{{ ownedReferralLink.payments_count }}</td>
                <td class="date-cell">{{
                  formatRefTableDate(ownedReferralLink.created_at)
                }}</td>
                <td class="col-actions">
                  <RouterLink
                    class="btn-secondary btn-tiny ref-list-link"
                    :to="{
                      path: '/admin/referrals',
                      query: referralEntityNumericId(ownedReferralLink) != null
                        ? { highlight: String(referralEntityNumericId(ownedReferralLink)) }
                        : {},
                    }"
                  >
                    В списке токенов
                  </RouterLink>
                </td>
              </tr>
              <tr v-else>
                <td colspan="11" class="muted-cell">Нет данных</td>
              </tr>
            </tbody>
          </table>
        </AdminTableWrap>

        <section
          class="referral-referees"
          aria-labelledby="referral-referees-heading"
        >
          <h3 id="referral-referees-heading" class="referral-referees__title">
            Приглашённые по этой ссылке
          </h3>
          <p class="referral-referees__meta">
            {{ refereeUsers.length }} пользователей
          </p>
          <p
            v-if="refereeUsersError"
            class="banner-err referral-referees__err"
          >{{ refereeUsersError }}</p>
          <AdminTableWrap
            v-else
            aria-label="Пользователи, зарегистрированные по личной реферальной ссылке"
          >
            <table class="admin-table">
              <thead>
                <tr>
                  <AdminSortTh
                    label="ID"
                    column-key="id"
                    align="right"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Email"
                    column-key="email"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Telegram ID"
                    column-key="telegram"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Регистрация"
                    column-key="registered_at"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Подписка до"
                    column-key="subscription_until"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Трафик"
                    column-key="traffic"
                    align="right"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                  <AdminSortTh
                    label="Устройства"
                    column-key="devices"
                    align="right"
                    :sort-key="refereeSortKey"
                    :sort-dir="refereeSortDir"
                    @sort="toggleRefereeSort"
                  />
                </tr>
              </thead>
              <tbody>
                <tr v-if="refereeUsersLoading">
                  <td colspan="7" class="muted-cell">Загрузка…</td>
                </tr>
                <tr v-else-if="sortedRefereeRows.length === 0">
                  <td colspan="7" class="muted-cell">Пока никого</td>
                </tr>
                <template v-else>
                  <tr
                    v-for="u in sortedRefereeRows"
                    :key="u.id"
                    :class="{ 'referee-row-active-today': u.active_today }"
                  >
                  <td class="num mono-num referee-id-cell">
                    <RouterLink
                      class="referral-referee-user-link"
                      :to="{
                        name: 'admin-user-analytics',
                        params: { userId: String(u.id) },
                      }"
                    >{{ u.id }}</RouterLink>
                  </td>
                  <td
                    class="email-cell"
                    :title="u.email && String(u.email).trim() ? u.email : undefined"
                  >{{
                    u.email && String(u.email).trim() ? u.email : '—'
                  }}</td>
                  <td class="tg-cell">{{ refereeTelegramCell(u) }}</td>
                  <td>{{ formatLocaleDateRu(u.registered_at) }}</td>
                  <td>{{ formatLocaleDateRu(u.subscription_until) }}</td>
                  <td
                    class="num mono-num"
                    :class="{ 'traffic-over-limit': isTrafficOverLimit(u) }"
                    :title="
                      isTrafficOverLimit(u) ? 'Лимит трафика исчерпан' : undefined
                    "
                  >
                    {{
                      formatTrafficWithLimit(
                        u.total_traffic_bytes,
                        u.traffic_limit_bytes,
                      )
                    }}
                  </td>
                  <td class="num mono-num">{{ u.subscription_devices_count ?? 0 }}</td>
                </tr>
                </template>
              </tbody>
            </table>
          </AdminTableWrap>
        </section>
      </template>
    </div>

    <div v-if="userId != null && !loading" class="ledger-widget glass">
      <div class="ledger-widget__head">
        <h2 class="ledger-widget__title">Платежи</h2>
        <RouterLink class="btn-secondary btn-tiny" to="/admin/payments">
          Полный журнал
        </RouterLink>
      </div>
      <p class="ledger-widget__meta">{{ paymentLedgerTotal }} записей</p>
      <p v-if="paymentsLedgerError" class="banner-err ledger-widget__err">{{
        paymentsLedgerError
      }}</p>
      <AdminTableWrap v-else aria-label="Платежи пользователя">
        <table class="admin-table">
          <thead>
            <tr>
              <AdminSortTh
                label="ID"
                column-key="id"
                align="right"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Пользователь"
                column-key="user_id"
                align="right"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Сумма"
                column-key="amount"
                align="right"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Мес."
                column-key="months"
                align="right"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Тип"
                column-key="payment_kind"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Провайдер"
                column-key="provider"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Webhook провайдера"
                column-key="provider_webhook"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
              <AdminSortTh
                label="Создан"
                column-key="created_at"
                :sort-key="paySortKey"
                :sort-dir="paySortDir"
                @sort="togglePayLedgerSort"
              />
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedPaymentLedgerRows.length === 0">
              <td colspan="8" class="muted-cell">Нет записей</td>
            </tr>
            <tr v-for="row in sortedPaymentLedgerRows" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td class="num">{{ row.user_id }}</td>
              <td class="num">{{ formatPaymentAmount(row.amount) }}</td>
              <td class="num">{{ row.months }}</td>
              <td>
                <span class="pill pill-mono" :title="row.payment_kind">{{
                  paymentKindLabel(row.payment_kind)
                }}</span>
              </td>
              <td>
                <span class="pill pill-mono" :title="row.provider">{{
                  row.provider
                }}</span>
              </td>
              <td
                class="mono-cell"
                :title="row.provider_webhook ? JSON.stringify(row.provider_webhook) : ''"
              >
                {{
                  row.provider_webhook?.name ||
                  row.provider_webhook?.event ||
                  (row.provider_webhook ? JSON.stringify(row.provider_webhook).slice(0, 80) : '—')
                }}
              </td>
              <td class="date-cell">{{ formatRefTableDate(row.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </AdminTableWrap>
    </div>

    <div v-if="userId != null && !loading" class="ledger-widget glass">
      <div class="ledger-widget__head">
        <h2 class="ledger-widget__title">Задачи</h2>
        <RouterLink class="btn-secondary btn-tiny" to="/admin/tasks">
          Полный журнал
        </RouterLink>
      </div>
      <p class="ledger-widget__meta">{{ taskLedgerTotal }} записей</p>
      <p v-if="tasksLedgerError" class="banner-err ledger-widget__err">{{
        tasksLedgerError
      }}</p>
      <AdminTableWrap v-else aria-label="Задачи пользователя">
        <table class="admin-table">
          <thead>
            <tr>
              <AdminSortTh
                label="ID"
                column-key="id"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="Тип"
                column-key="type"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="user_id"
                column-key="user_id"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="referee"
                column-key="referee_id"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="bonus дн."
                column-key="bonus_days"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="досроч."
                column-key="early_payment_bonus_days"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="мес."
                column-key="paid_months"
                align="right"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="Статус"
                column-key="status"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="Создана"
                column-key="created_at"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <AdminSortTh
                label="Завершена"
                column-key="done_at"
                :sort-key="taskSortKey"
                :sort-dir="taskSortDir"
                @sort="toggleTaskLedgerSort"
              />
              <th class="th-actions">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="sortedTaskLedgerRows.length === 0">
              <td colspan="11" class="muted-cell">Нет записей</td>
            </tr>
            <tr v-for="row in sortedTaskLedgerRows" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td class="mono-cell">{{ row.type }}</td>
              <td class="owner-user-id-cell num">
                <span class="owner-user-id-inner">
                  <span>{{ row.user_id }}</span>
                  <AdminHighlightListLink list="users" :highlight="row.user_id" />
                </span>
              </td>
              <td class="owner-user-id-cell num">
                <span class="owner-user-id-inner">
                  <template v-if="row.referee_id != null">
                    <span>{{ row.referee_id }}</span>
                    <AdminHighlightListLink list="users" :highlight="row.referee_id" />
                  </template>
                  <template v-else>—</template>
                </span>
              </td>
              <td class="num">{{ row.bonus_days ?? '—' }}</td>
              <td class="num">{{ row.early_payment_bonus_days ?? '—' }}</td>
              <td class="num">{{ row.paid_months ?? '—' }}</td>
              <td>
                <span class="pill pill-mono" :title="row.status">{{
                  row.status
                }}</span>
              </td>
              <td class="date-cell">{{ formatRefTableDate(row.created_at) }}</td>
              <td class="date-cell">{{ formatRefTableDate(row.done_at) }}</td>
              <td class="td-actions">
                <RouterLink
                  class="btn-secondary btn-compact"
                  :to="{
                    path: '/admin/tasks',
                    query: { edit_task_id: String(row.id) },
                  }"
                >
                  Изменить
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </AdminTableWrap>
    </div>

    <AdminLineChartPanel
      v-if="userId != null && !loading"
      aria-label="Потребление трафика пользователя по календарным дням UTC"
      :error="trafficByDayError"
      :has-data="trafficByDay.length > 0"
      title="Накопительный трафик по дням"
      unit-label="UTC · МиБ"
      hint=""
      :labels="trafficDayLabels"
      :datasets="trafficDayDatasets"
      y-title="МиБ накопленно"
      :format-y-tick="trafficDayFormatYTick"
      :get-tooltip-title="trafficDayTooltipTitle"
      :get-tooltip-label="trafficDayTooltipLabel"
    />

    <template v-if="!loading && bundle">
      <div class="chart-panel glass">
        <div class="chart-head">
          <h3 class="chart-title">Распределение по узлам</h3>
          <span class="chart-unit">МиБ</span>
        </div>
        <div
          v-if="bundle.servers.length === 0"
          class="empty-hint"
        >
          В базе нет серверов.
        </div>
        <AdminBarChart
          v-else
          preset="finance"
          aria-label="Распределение трафика по узлам, МиБ"
          :has-data="serverBarLabels.length > 0"
          :labels="serverBarLabels"
          :datasets="serverBarDatasets"
          stacked
          index-axis="y"
          value-axis-title="МиБ"
          :value-axis-min="0"
          :format-value-tick="formatServerBarValueTick"
        />
      </div>
    </template>
  </AdminPageShell>
</template>

<style scoped>
.inline {
  font-family: var(--mono);
  font-size: 0.82em;
  background: var(--code-bg);
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
}
.glass {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(10px);
}
.user-profile {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1.15rem;
}
.personal-ref {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid color-mix(in srgb, var(--card-border) 85%, transparent);
}
.personal-ref__title {
  margin: 0 0 0.65rem;
  font-size: 0.95rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.personal-ref__empty {
  margin: 0;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}
.personal-ref__err {
  margin: 0 0 0.65rem;
}
.personal-ref__hint {
  margin: 0;
  font-size: 0.88rem;
}
.personal-ref__copy-hint {
  margin: 0 0 0.5rem;
}
.personal-ref__table-wrap {
  margin-top: 0.25rem;
}
.referral-widget {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1.15rem;
}
.referral-widget__title {
  margin: 0 0 0.85rem;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.referral-widget__empty {
  margin: 0;
  font-size: 0.9rem;
  color: var(--muted);
}
.referral-referees {
  margin-top: 1.15rem;
  padding-top: 1rem;
  border-top: 1px solid color-mix(in srgb, var(--card-border) 85%, transparent);
}
.referral-referees__title {
  margin: 0 0 0.35rem;
  font-size: 0.95rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.referral-referees__meta {
  margin: 0 0 0.65rem;
  font-size: 0.82rem;
  color: var(--muted);
}
.referral-referees__err {
  margin: 0 0 0.65rem;
}
.referral-referees .referee-id-cell {
  vertical-align: middle;
  text-align: right;
  white-space: nowrap;
}
.referral-referee-user-link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 700;
}
.referral-referee-user-link:hover {
  text-decoration: underline;
}
.referral-referees .email-cell {
  max-width: 14rem;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
.referral-referees .tg-cell {
  white-space: nowrap;
  vertical-align: middle;
}
tr.referee-row-active-today {
  background-color: color-mix(in srgb, var(--success, #15803d) 10%, transparent);
}
.referral-referees .mono-num {
  font-variant-numeric: tabular-nums;
}
.ledger-widget {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1.15rem;
}
.ledger-widget__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
  margin-bottom: 0.35rem;
}
.ledger-widget__title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.ledger-widget__meta {
  margin: 0 0 0.65rem;
  font-size: 0.82rem;
  color: var(--muted);
}
.ledger-widget__err {
  margin: 0 0 0.75rem;
}
.th-actions {
  width: 1%;
  white-space: nowrap;
  text-align: center;
  vertical-align: middle;
  color: var(--muted);
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
}
.td-actions {
  vertical-align: middle;
  text-align: center;
}
.btn-compact {
  font-size: 0.8rem;
  padding: 0.28rem 0.55rem;
}
.referral-widget__err {
  margin: 0 0 0.75rem;
}
.copy-hint {
  margin: 0 0 0.5rem;
  font-size: 0.82rem;
  color: var(--accent);
  font-weight: 600;
}
.muted-cell {
  color: var(--muted);
}
.muted-inline {
  color: var(--muted);
  font-size: 0.85rem;
}
.mono-cell {
  font-family: var(--mono);
  font-size: 0.78rem;
  word-break: break-all;
  max-width: 14rem;
}
.date-cell {
  white-space: nowrap;
  font-size: 0.8rem;
  color: var(--muted);
}
.link-actions {
  vertical-align: middle;
  text-align: center;
  white-space: nowrap;
}
.col-actions {
  vertical-align: middle;
  text-align: center;
}
.btn-tiny {
  font-size: 0.75rem;
  padding: 0.25rem 0.45rem;
}
.ref-list-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  white-space: nowrap;
}
.ref-list-link:hover {
  text-decoration: none;
}
.pill {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--surface);
  border: 1px solid var(--card-border);
  color: var(--muted);
}
.pill-mono {
  font-family: var(--mono);
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0.02em;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.profile-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}
.profile-head__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.profile-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.profile-edit-err {
  margin: 0 0 0.75rem;
}
.subscription-link-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  min-width: 0;
}
.subscription-link-cell__token {
  font-size: 0.82rem;
  word-break: break-all;
}
.subscription-link-cell__url {
  font-size: 0.82rem;
  color: var(--accent);
  word-break: break-all;
}
.profile-field-input {
  width: 100%;
  max-width: 18rem;
  padding: 0.35rem 0.55rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
}
.profile-field-input:focus {
  outline: 2px solid color-mix(in srgb, var(--accent) 45%, transparent);
  outline-offset: 1px;
}
.profile-field-select {
  max-width: 22rem;
}
.profile-field-date {
  max-width: 10rem;
}
.profile-field-traffic {
  max-width: 8rem;
}
.profile-field-hint {
  display: block;
  margin-top: 0.3rem;
  font-size: 0.78rem;
  color: var(--muted);
  font-family: var(--sans);
}
.profile-telegram-clear {
  margin-top: 0.45rem;
}
.kv-dd-devices {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  min-width: 0;
}
.kv-dd-devices__count {
  font-size: 0.9rem;
}
.user-profile .connections-expand {
  width: 100%;
  margin: 0;
}
.user-profile .connections-expand__summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent);
  line-height: 1.35;
  list-style: none;
}
.user-profile .connections-expand__summary::-webkit-details-marker {
  display: none;
}
.user-profile .connections-expand__summary::before {
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
.user-profile .connections-expand[open] .connections-expand__summary::before {
  transform: rotate(90deg);
}
.user-profile .connections-expand__list {
  margin: 0.4rem 0 0;
  padding: 0.35rem 0 0 1rem;
  list-style: disc;
  font-size: 0.82rem;
  border-top: 1px dashed color-mix(in srgb, var(--muted) 40%, transparent);
}
.user-profile .connections-expand__item {
  margin: 0.22rem 0;
  padding: 0;
  line-height: 1.4;
  word-break: break-word;
}
.user-profile .connections-expand__item--readonly {
  display: block;
}
.user-profile .connections-expand__line {
  min-width: 0;
}
.user-profile .connections-expand__dot {
  color: color-mix(in srgb, var(--muted) 65%, transparent);
  font-weight: 400;
}
.kv-grid {
  display: grid;
  grid-template-columns: minmax(7rem, 12rem) 1fr;
  gap: 0.45rem 1rem;
  margin: 0;
  font-size: 0.86rem;
}
.kv-grid dt {
  margin: 0;
  color: var(--muted);
  font-weight: 600;
  font-size: 0.78rem;
}
.kv-grid dd {
  margin: 0;
  color: var(--text);
  min-width: 0;
}
.json-pre {
  margin: 0;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  background: var(--code-bg);
  border: 1px solid var(--card-border);
  font-family: var(--mono);
  font-size: 0.75rem;
  line-height: 1.45;
  max-height: 12rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.muted-dash {
  color: var(--muted);
}
.banner-err {
  padding: 0.85rem 1.1rem;
  border-radius: 14px;
  background: var(--danger-soft);
  border: 1px solid var(--danger);
  color: var(--danger);
  font-size: 0.9rem;
  margin: 0 0 1rem;
}
.loading-line {
  color: var(--muted);
  font-size: 0.92rem;
}
.chart-panel {
  padding: 1rem 1.15rem 1.15rem;
  margin-bottom: 1.15rem;
}
.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.35rem;
}
.chart-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
}
.chart-unit {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.chart-hint {
  margin: 0 0 0.85rem;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.5;
  max-width: 52rem;
}
.empty-hint {
  padding: 1rem 0;
  color: var(--muted);
  font-size: 0.9rem;
}
.mono {
  font-family: var(--mono);
  font-size: 0.82rem;
}
</style>
