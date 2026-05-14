<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import Chart from '../utils/chartSetup.js'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import AdminSortTh from '../components/AdminSortTh.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { fetchJson, sitePublicUrl } from '../api/client.js'
import { isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { formatTrafficBytes as formatBytes } from '../utils/formatTraffic.js'
import { useTableSort } from '../utils/adminTableSort.js'

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

/** @type {import('vue').Ref<Record<string, unknown> | null>} */
const referralLink = ref(null)
const referralLinkLoading = ref(false)
const referralLinkError = ref(null)
const copyHint = ref(null)

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
  external_id: (r) => String(r.external_id ?? '').toLowerCase(),
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

/** @type {Chart | null} */
let chartInstance = null

const userId = computed(() => {
  const raw = route.params.userId
  const n = parseInt(String(raw), 10)
  return Number.isFinite(n) ? n : null
})

const userAnalyticsBackTo = computed(() =>
  isAdminRole(getSessionRole()) ? '/admin/users' : '/admin/users/analytics',
)

const userAnalyticsBackLabel = computed(() =>
  isAdminRole(getSessionRole()) ? '← Пользователи' : '← Аналитика клиентов',
)

function formatDateTime(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleString('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return String(d)
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

function formatConnectionOs(raw) {
  if (raw == null || String(raw).trim() === '') return '—'
  return String(raw).trim()
}

/** Часть User-Agent до первого «/» (напр. Happ из Happ/2.9.1/…). */
function formatConnectionUserAgentHead(raw) {
  if (raw == null || String(raw).trim() === '') return '—'
  const s = String(raw).trim()
  const i = s.indexOf('/')
  const head = i === -1 ? s : s.slice(0, i).trim()
  return head || '—'
}

function formatDayShortUtc(iso) {
  if (iso == null || iso === '') return '—'
  const s = String(iso).slice(0, 10)
  try {
    return new Date(s + 'T12:00:00Z').toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return s
  }
}

const trafficDayLabels = computed(() =>
  trafficByDay.value.map((r) => formatDayShortUtc(r.traffic_date)),
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
  return iso ? formatDayShortUtc(iso) : ''
}

function trafficDayTooltipLabel(ctx) {
  const i = ctx.dataIndex
  const row = trafficByDay.value[i]
  const b = row
    ? Number(row.cumulative_bytes ?? row.consumed_bytes ?? 0)
    : 0
  return `Накопленно: ${formatBytes(b)}`
}

function gridColor() {
  return 'rgba(88, 214, 141, 0.12)'
}

function tickColor() {
  return typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(200, 228, 210, 0.55)'
    : 'rgba(45, 85, 65, 0.45)'
}

function serverLabel(row) {
  const n = row.name && String(row.name).trim()
  if (n) return n
  return `${row.host}:${row.port}`
}

function formatDate(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return String(d)
  }
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
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      dateStyle: 'short',
      timeStyle: 'medium',
    })
  } catch {
    return String(iso)
  }
}

function fallbackSiteEntry(token) {
  const base = sitePublicUrl().replace(/\/$/, '')
  return `${base}/?ref=${encodeURIComponent(token)}`
}

function siteUrlForReferralRow(r) {
  return r.site_entry_url || fallbackSiteEntry(r.token)
}

function telegramUrlForReferralRow(r) {
  return r.telegram_deep_link || ''
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

async function loadReferralWidget() {
  referralLinkError.value = null
  referralLink.value = null
  const rid = profile.value?.referral_link_id
  if (rid == null) {
    referralLinkLoading.value = false
    return
  }
  referralLinkLoading.value = true
  try {
    referralLink.value = await fetchJson(`/api/referral-links/${rid}`)
  } catch (e) {
    referralLinkError.value = e.message || String(e)
  } finally {
    referralLinkLoading.value = false
  }
}

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = null
  }
}

function drawChart() {
  const el = chartCanvas.value
  if (!el) return
  destroyChart()
  const b = bundle.value
  if (!b?.servers?.length) return
  const rows = [...b.servers].sort((a, b) => b.total_bytes - a.total_bytes)
  const mib = (x) => x / (1024 * 1024)
  chartInstance = new Chart(el, {
    type: 'bar',
    data: {
      labels: rows.map((r) => serverLabel(r)),
      datasets: [
        {
          label: 'К клиенту (down), МиБ',
          data: rows.map((r) => mib(r.down_bytes)),
          backgroundColor: 'rgba(88, 214, 141, 0.78)',
        },
        {
          label: 'От клиента (up), МиБ',
          data: rows.map((r) => mib(r.up_bytes)),
          backgroundColor: 'rgba(69, 179, 157, 0.78)',
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: tickColor(),
            font: { family: 'var(--sans)', size: 12 },
          },
        },
        tooltip: {
          backgroundColor: 'rgba(4, 12, 9, 0.94)',
          titleFont: { family: 'var(--sans)', size: 12 },
          bodyFont: { family: 'var(--mono)', size: 12 },
        },
      },
      scales: {
        x: {
          stacked: true,
          min: 0,
          ticks: { color: tickColor() },
          grid: { color: gridColor(), drawBorder: false },
          title: {
            display: true,
            text: 'МиБ',
            color: tickColor(),
            font: { size: 11, weight: '600' },
          },
        },
        y: {
          stacked: true,
          ticks: { color: tickColor(), maxRotation: 0 },
          grid: { color: gridColor(), drawBorder: false },
        },
      },
    },
  })
}

const chartCanvas = ref(null)

/** Лимит строк для платежей/задач на странице одного пользователя (совпадает с шагом пагинации в staff-вью). */
const LEDGER_PAGE_LIMIT = 200

function resetAnalyticsPageState() {
  error.value = null
  profileError.value = null
  bundle.value = null
  profile.value = null
  trafficByDay.value = []
  trafficByDayError.value = null
  referralLink.value = null
  referralLinkError.value = null
  referralLinkLoading.value = false
  copyHint.value = null
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
    if (profile.value?.referral_link_id != null) {
      void loadReferralWidget()
    }
  } finally {
    loading.value = false
  }
  await nextTick()
  drawChart()
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

onBeforeUnmount(() => {
  destroyChart()
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
      <h2 class="profile-title">Данные пользователя</h2>
      <dl class="kv-grid">
        <dt>ID</dt>
        <dd class="mono">{{ profile.id }}</dd>
        <dt>Email</dt>
        <dd>{{ profile.email && String(profile.email).trim() ? profile.email : '—' }}</dd>
        <dt>Telegram ID</dt>
        <dd class="mono">
          {{ profile.telegram_id != null ? profile.telegram_id : '—' }}
        </dd>
        <dt>Username в Telegram</dt>
        <dd>{{ telegramUsername(profile) || '—' }}</dd>
        <dt>Профиль Telegram (JSON)</dt>
        <dd>
          <pre v-if="profile.telegram_properties" class="json-pre">{{
            JSON.stringify(profile.telegram_properties, null, 2)
          }}</pre>
          <span v-else class="muted-dash">—</span>
        </dd>
        <dt>Регистрация</dt>
        <dd>{{ formatDateTime(profile.registered_at) }}</dd>
        <dt>Подписка до</dt>
        <dd>{{ formatDate(profile.subscription_until) }}</dd>
        <dt>Трафик</dt>
        <dd class="mono">{{ formatBytes(profile.total_traffic_bytes ?? 0) }}</dd>
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
                    formatConnectionOs(conn.os)
                  }}</span>
                  <span class="connections-expand__dot" aria-hidden="true">
                    ·
                  </span>
                  <span class="connections-expand__ua">{{
                    formatConnectionUserAgentHead(conn.user_agent)
                  }}</span>
                </div>
              </li>
            </ul>
          </details>
        </dd>
      </dl>
    </div>

    <div
      v-if="!loading && profile"
      class="referral-widget glass"
    >
      <h2 class="referral-widget__title">Реферальная ссылка</h2>
      <p
        v-if="profile.referral_link_id == null"
        class="referral-widget__empty"
      >
        Не привязана.
      </p>
      <template v-else>
        <p v-if="copyHint" class="copy-hint">{{ copyHint }}</p>
        <p v-if="referralLinkError" class="banner-err referral-widget__err">{{
          referralLinkError
        }}</p>
        <AdminTableWrap
          v-else
          aria-label="Реферальная ссылка пользователя"
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
              <tr v-if="referralLinkLoading">
                <td colspan="11" class="muted-cell">Загрузка…</td>
              </tr>
              <tr v-else-if="referralLink">
                <td class="num">{{ referralLink.id }}</td>
                <td class="mono-cell">{{ referralLink.token }}</td>
                <td>
                  <span
                    class="pill pill-mono"
                    :title="referralLink.owner_kind"
                  >{{ referralLink.owner_kind }}</span>
                </td>
                <td class="owner-user-id-cell">
                  <span class="owner-user-id-inner">
                    <template v-if="referralLink.owner_user_id != null">
                      <span>{{ referralLink.owner_user_id }}</span>
                      <RouterLink
                        class="ref-open-in-list"
                        :to="{
                          path: '/admin/users/analytics',
                          query: {
                            highlight: String(referralLink.owner_user_id),
                          },
                        }"
                        title="Открыть этого пользователя в списке клиентов"
                        aria-label="Перейти к пользователю в таблице клиентов"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                      </RouterLink>
                    </template>
                    <template v-else>—</template>
                  </span>
                </td>
                <td class="link-actions">
                  <button
                    type="button"
                    class="btn-secondary btn-tiny"
                    title="Копировать ссылку на сайт (?ref)"
                    @click="copyReferralUrl(siteUrlForReferralRow(referralLink))"
                  >
                    Копировать
                  </button>
                </td>
                <td class="link-actions">
                  <button
                    v-if="telegramUrlForReferralRow(referralLink)"
                    type="button"
                    class="btn-secondary btn-tiny"
                    title="Копировать ссылку на Telegram-бота (?start)"
                    @click="
                      copyReferralUrl(telegramUrlForReferralRow(referralLink))
                    "
                  >
                    Копировать
                  </button>
                  <span v-else class="muted-inline">—</span>
                </td>
                <td class="num">{{ referralLink.clicks_count }}</td>
                <td class="num">{{ referralLink.registrations_count }}</td>
                <td class="num">{{ referralLink.payments_count }}</td>
                <td class="date-cell">{{
                  formatRefTableDate(referralLink.created_at)
                }}</td>
                <td class="col-actions">
                  <RouterLink
                    class="btn-secondary btn-tiny ref-list-link"
                    :to="{
                      path: '/admin/referrals',
                      query: { highlight: String(referralLink.id) },
                    }"
                  >
                    В списке токенов
                  </RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </AdminTableWrap>
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
                label="Внешний id"
                column-key="external_id"
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
              <td class="mono-cell" :title="row.external_id || ''">
                {{ row.external_id || '—' }}
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
              <td colspan="10" class="muted-cell">Нет записей</td>
            </tr>
            <tr v-for="row in sortedTaskLedgerRows" :key="row.id">
              <td class="num">{{ row.id }}</td>
              <td class="mono-cell">{{ row.type }}</td>
              <td class="num">{{ row.user_id }}</td>
              <td class="num">{{ row.referee_id ?? '—' }}</td>
              <td class="num">{{ row.bonus_days ?? '—' }}</td>
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
      hint="На каждую дату"
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
        <div v-else class="chart-wrap chart-wrap-tall">
          <canvas ref="chartCanvas" />
        </div>
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
.owner-user-id-cell {
  vertical-align: middle;
}
.owner-user-id-inner {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.ref-open-in-list {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0.12rem;
  border-radius: 6px;
  color: var(--accent);
  line-height: 0;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}
.ref-open-in-list:hover {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-h);
}
.ref-open-in-list:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
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
.profile-title {
  margin: 0 0 0.85rem;
  font-size: 1.05rem;
  font-weight: 800;
  font-family: var(--heading);
  color: var(--text-h);
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
.chart-wrap {
  position: relative;
  min-height: 220px;
}
.chart-wrap-tall {
  min-height: 320px;
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
