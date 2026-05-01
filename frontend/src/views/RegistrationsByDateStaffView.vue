<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AdminLineChartPanel from '../components/AdminLineChartPanel.vue'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import { rgbTupleFromVar } from '../utils/adminChartTheme.js'
import { isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import { fetchJson } from '../api/client.js'

const route = useRoute()
/** @type {import('vue').Ref<Array<{ stats_date: string | null; users_count: number; users_with_traffic_count?: number; active_users_count?: number }>>} */
const rows = ref([])
const loading = ref(false)
const error = ref(null)

const isFullAdmin = computed(() => isAdminRole(getSessionRole()))

const undatedCount = computed(() => {
  const row = rows.value.find((r) => r.stats_date == null || r.stats_date === '')
  return row ? Number(row.users_count) || 0 : 0
})

const undatedTrafficCount = computed(() => {
  const row = rows.value.find((r) => r.stats_date == null || r.stats_date === '')
  return row ? Number(row.users_with_traffic_count) || 0 : 0
})

const chartPoints = computed(() => {
  const extraUsers = undatedCount.value
  const extraTraffic = undatedTrafficCount.value
  const sorted = rows.value
    .filter((r) => r.stats_date != null && r.stats_date !== '')
    .map((r) => ({
      iso: String(r.stats_date),
      dayUsers: Number(r.users_count) || 0,
      dayTraffic: Number(r.users_with_traffic_count) || 0,
      dayActive: Number(r.active_users_count) || 0,
    }))
    .sort((a, b) => a.iso.localeCompare(b.iso))

  let cumDatedUsers = 0
  let cumDatedTraffic = 0
  return sorted.map((row) => {
    cumDatedUsers += row.dayUsers
    cumDatedTraffic += row.dayTraffic
    return {
      iso: row.iso,
      dayUsers: row.dayUsers,
      dayTraffic: row.dayTraffic,
      dayActive: row.dayActive,
      cumDatedUsers,
      cumDatedTraffic,
      totalUsers: cumDatedUsers + extraUsers,
      totalTraffic: cumDatedTraffic + extraTraffic,
    }
  })
})

const totalUsers = computed(() =>
  rows.value.reduce((acc, r) => acc + (Number(r.users_count) || 0), 0),
)

const totalWithTraffic = computed(() =>
  rows.value.reduce(
    (acc, r) => acc + (Number(r.users_with_traffic_count) || 0),
    0,
  ),
)

/** Склонение «день» для числа n */
function pluralRuDays(n) {
  const k = Math.abs(Math.trunc(Number(n))) % 100
  const d = k % 10
  if (k > 10 && k < 20) return 'дней'
  if (d === 1) return 'день'
  if (d >= 2 && d <= 4) return 'дня'
  return 'дней'
}

function fmtRu(n) {
  return Number(n).toLocaleString('ru-RU')
}

/** Дельта для подсказки: +7, −3, 0 */
function fmtDeltaRu(n) {
  const v = Number(n) || 0
  if (v > 0) return `+${fmtRu(v)}`
  if (v < 0) return fmtRu(v)
  return '0'
}

const registrationChartLabels = computed(() =>
  chartPoints.value.map((p) => formatDayShort(p.iso)),
)

const activeSkyRgb = [56, 189, 248]

const registrationChartDatasets = computed(() => {
  const pts = chartPoints.value
  const accentRgb = rgbTupleFromVar('--accent', '#58d68d')
  const trafficOrange = [251, 146, 60]
  return [
    {
      label: 'Всего пользователей · накопительно',
      data: pts.map((p) => p.totalUsers),
      rgb: accentRgb,
    },
    {
      label: 'С трафиком · накопительно',
      data: pts.map((p) => p.totalTraffic),
      rgb: trafficOrange,
    },
    {
      label: 'Активные · за день',
      data: pts.map((p) => p.dayActive),
      rgb: activeSkyRgb,
      filled: false,
    },
  ]
})

function registrationTooltipTitle(i) {
  const iso = chartPoints.value[i]?.iso
  return iso ? formatDayShort(iso) : ''
}

function registrationTooltipLabel(ctx) {
  const i = ctx.dataIndex
  const pts = chartPoints.value
  const p = pts[i]
  if (!p) return ''
  const und = undatedCount.value
  const undT = undatedTrafficCount.value
  const prevUsers = i > 0 ? pts[i - 1].totalUsers : und
  const prevTraffic = i > 0 ? pts[i - 1].totalTraffic : undT
  const dUsers = p.totalUsers - prevUsers
  const dTraffic = p.totalTraffic - prevTraffic

  if (ctx.datasetIndex === 0) {
    return [
      `Пользователи: ${fmtRu(p.totalUsers)}`,
      `Без даты регистрации: ${fmtRu(und)}`,
      `Прирост с предыдущего дня: ${fmtDeltaRu(dUsers)}`,
    ]
  }
  if (ctx.datasetIndex === 1) {
    return [
      `С трафиком: ${fmtRu(p.totalTraffic)}`,
      `Без даты регистрации: ${fmtRu(undT)}`,
      `Прирост с предыдущего дня: ${fmtDeltaRu(dTraffic)}`,
    ]
  }
  const prevA = i > 0 ? pts[i - 1].dayActive : 0
  const dA = p.dayActive - prevA
  return [
    `Активных за день: ${fmtRu(p.dayActive)}`,
    `К предыдущему дню: ${fmtDeltaRu(dA)}`,
  ]
}

function formatDayShort(iso) {
  if (iso == null || iso === '') return '—'
  try {
    return new Date(iso + 'T12:00:00Z').toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return String(iso)
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const data = await fetchJson('/api/users/daily-stats')
    rows.value = Array.isArray(data.stats_by_date) ? data.stats_by_date : []
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
  await nextTick()
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Статистика по дням"
      :tabs-aria-label="isFullAdmin ? 'Разделы админки' : 'Раздел менеджера'"
    >
      <template #back>
        <RouterLink v-if="isFullAdmin" class="back" to="/admin/users">
          ← Управление данными
        </RouterLink>
        <RouterLink v-else class="back" to="/cabinet">← Личный кабинет</RouterLink>
      </template>
      <template #tabs>
        <template v-if="isFullAdmin">
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users' }"
            :to="{ path: '/admin/users' }"
          >
            Пользователи
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-servers' }"
            :to="{ path: '/admin/servers' }"
          >
            Серверы
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Статистика по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-analytics' }"
            :to="{ path: '/admin/analytics' }"
          >
            Нагрузка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink class="tab" :to="{ path: '/admin/referrals' }">
            Реферальные токены
          </RouterLink>
        </template>
        <template v-else>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-staff-analytics' }"
            :to="{ path: '/admin/users/analytics' }"
          >
            Клиенты
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-users-registrations-by-date' }"
            :to="{ path: '/admin/users/registrations-by-date' }"
          >
            Статистика по дням
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-funnel' }"
            :to="{ path: '/admin/funnel' }"
          >
            Воронка
          </RouterLink>
          <RouterLink
            class="tab"
            :class="{ 'tab-active': route.name === 'admin-referrals' }"
            :to="{ path: '/admin/referrals' }"
          >
            Реферальные токены
          </RouterLink>
        </template>
      </template>
      <div class="head-row">
        <div class="head-text">
          <h2 class="section-heading">Статистика по дням (UTC)</h2>
          <p class="section-sub">
            Две первые кривые — накопление по дате регистрации: всего пользователей и
            сколько из них с ненулевым трафиком
            (<span class="mono-inline">user_server_traffic</span>). Синяя линия —
            сколько пользователей в этот календарный день увеличили суммарный
            накопленный трафик относительно предыдущего дня; все линии в одной шкале по оси Y.
          </p>
        </div>
        <div class="head-actions">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="load"
          >
            {{ loading ? 'Обновление…' : 'Обновить' }}
          </button>
        </div>
      </div>
    </AdminPageHeader>

    <section class="stats" aria-live="polite">
      <p v-if="loading" class="stats-status muted">Загрузка…</p>
      <p v-else-if="error" class="stats-status stats-status--err">
        Не удалось загрузить сводку (подробности ниже).
      </p>
      <dl v-else class="stats-grid">
        <div class="stats-card">
          <dt class="stats-label">Дней на графике</dt>
          <dd class="stats-value">
            {{ chartPoints.length.toLocaleString('ru-RU') }}
            <span class="stats-unit">{{ pluralRuDays(chartPoints.length) }}</span>
          </dd>
        </div>
        <div class="stats-card">
          <dt class="stats-label">Всего пользователей</dt>
          <dd class="stats-value">
            {{ totalUsers.toLocaleString('ru-RU') }}
          </dd>
          <p class="stats-hint">Записей в БД</p>
        </div>
        <div class="stats-card">
          <dt class="stats-label">С ненулевым трафиком</dt>
          <dd class="stats-value stats-value--traffic">
            {{ totalWithTraffic.toLocaleString('ru-RU') }}
          </dd>
          <p class="stats-hint">Up+down по последнему дню на узел</p>
        </div>
      </dl>
    </section>

    <AdminLineChartPanel
      aria-label="Пользователи и трафик по дням: накопление по регистрации и активные за день по UTC"
      :loading="loading"
      :error="error"
      :has-data="chartPoints.length > 0"
      y-title="Пользователей"
      :labels="registrationChartLabels"
      :datasets="registrationChartDatasets"
      :get-tooltip-title="registrationTooltipTitle"
      :get-tooltip-label="registrationTooltipLabel"
    >
      <template #empty>
        <p
          v-if="chartPoints.length === 0 && undatedCount > 0"
          class="empty-hint"
        >
          Нет ни одной известной даты регистрации — только пользователи без
          даты:
          <strong>{{ undatedCount.toLocaleString('ru-RU') }}</strong>
          . Добавить их к точкам по дням нельзя — появится график после появления
          записей с датой.
        </p>
        <p v-else class="empty-hint">Нет данных для графика.</p>
      </template>
    </AdminLineChartPanel>
  </AdminPageShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem 1rem;
}

.head-text {
  min-width: min(100%, 42rem);
}

.section-heading {
  margin: 0 0 0.35rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-h);
}

.section-sub {
  margin: 0;
  max-width: 46rem;
  font-size: 0.82rem;
  line-height: 1.45;
  color: var(--muted);
}

.mono-inline {
  font-family: var(--mono);
  font-size: 0.78rem;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stats {
  margin-bottom: 1rem;
}

.stats-status {
  margin: 0;
  font-size: 0.92rem;
}

.stats-status--err {
  color: var(--danger);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr));
  gap: 0.75rem 1rem;
  margin: 0;
}

.stats-card {
  margin: 0;
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--surface);
}

.stats-label {
  margin: 0 0 0.35rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.stats-value {
  margin: 0;
  font-size: 1.12rem;
  font-weight: 800;
  font-family: var(--heading, inherit);
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
  line-height: 1.2;
}

.stats-value--traffic {
  color: #fb923c;
}

@media (prefers-color-scheme: light) {
  .stats-value--traffic {
    color: #ea580c;
  }
}

.stats-unit {
  margin-left: 0.25rem;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
  text-transform: lowercase;
}

.stats-hint {
  margin: 0.35rem 0 0;
  font-size: 0.76rem;
  line-height: 1.4;
  color: var(--muted);
}

.empty-hint {
  margin: 0;
  padding: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.5;
}
</style>
