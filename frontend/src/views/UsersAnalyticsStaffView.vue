<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AdminPageHeader from '../components/AdminPageHeader.vue'
import AdminPageShell from '../components/AdminPageShell.vue'
import AdminTableWrap from '../components/AdminTableWrap.vue'
import { isAdminRole } from '../auth/permissions.js'
import { getSessionRole } from '../auth/session.js'
import { fetchJson } from '../api/client.js'
import { formatTrafficBytes } from '../utils/formatTraffic.js'

const route = useRoute()

const rows = ref([])
const loading = ref(false)
const error = ref(null)

/** id пользователя: подсветка строки после перехода из других разделов */
const highlightUserId = ref(null)

function clientHighlightFromRoute() {
  const raw = route.query.highlight
  const s = raw == null ? '' : Array.isArray(raw) ? raw[0] : raw
  if (s === '') return null
  const n = Number(s)
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : null
}

const isFullAdmin = computed(() => isAdminRole(getSessionRole()))

const statsLine = computed(() => {
  if (loading.value) return 'Загрузка…'
  if (error.value) return 'Ошибка загрузки'
  return `${rows.value.length} пользователей`
})

function formatDate(d) {
  if (d == null || d === '') return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return String(d)
  }
}

function telegramCell(u) {
  if (u.telegram_id != null) {
    const un = u.telegram_properties?.username
    return un ? `${u.telegram_id} @${un}` : String(u.telegram_id)
  }
  if (u.telegram_properties?.username) {
    return `@${u.telegram_properties.username}`
  }
  return '—'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await fetchJson('/api/users')
  } catch (e) {
    error.value = e.message || String(e)
    rows.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () =>
    `${loading.value}:${
      route.query.highlight ?? ''
    }:${rows.value.map((u) => u.id).join(',')}`,
  async () => {
    if (loading.value) return
    const hid = clientHighlightFromRoute()
    highlightUserId.value = null
    if (hid == null) return
    if (!rows.value.some((u) => u.id === hid)) return
    await nextTick()
    const el = document.getElementById(`client-${hid}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    highlightUserId.value = hid
    window.setTimeout(() => {
      if (highlightUserId.value === hid) highlightUserId.value = null
    }, 3400)
  },
  { flush: 'post' },
)

onMounted(() => {
  void load()
})
</script>

<template>
  <AdminPageShell>
    <AdminPageHeader
      title="Аналитика пользователей"
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
        <h2 class="section-heading">Сводка по учётным записям и трафику</h2>
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
      <p class="stats-value">{{ statsLine }}</p>
    </section>

    <AdminTableWrap aria-label="Таблица аналитики пользователей">
      <table class="table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Telegram</th>
            <th>Регистрация</th>
            <th>Подписка до</th>
            <th class="num">Трафик (всего)</th>
            <th class="num">Устройства</th>
            <th class="num">ID реф. ссылки</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="7" class="muted">Загрузка…</td>
          </tr>
          <tr v-else-if="error">
            <td colspan="7" class="error-cell">{{ error }}</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="7" class="muted">Нет пользователей</td>
          </tr>
          <tr
            v-for="u in rows"
            :id="'client-' + u.id"
            :key="u.id"
            :class="{ 'client-row-highlight': highlightUserId === u.id }"
          >
            <td>{{ u.email ?? '—' }}</td>
            <td class="tg-cell">{{ telegramCell(u) }}</td>
            <td>{{ formatDate(u.registered_at) }}</td>
            <td>{{ formatDate(u.subscription_until) }}</td>
            <td class="num mono-num">{{ formatTrafficBytes(u.total_traffic_bytes) }}</td>
            <td class="num mono-num">{{ u.subscription_devices_count ?? 0 }}</td>
            <td class="num ref-id-cell">
              <template v-if="u.referral_link_id != null">
                <span>{{ u.referral_link_id }}</span>
                <RouterLink
                  class="ref-open-in-list"
                  :to="{
                    path: '/admin/referrals',
                    query: { highlight: String(u.referral_link_id) },
                  }"
                  title="Открыть эту запись в списке реферальных ссылок"
                  aria-label="Перейти к реферальной ссылке в таблице токенов"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                </RouterLink>
              </template>
              <template v-else>—</template>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
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

.section-heading {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.stats {
  margin-bottom: 1rem;
}
.stats-value {
  margin: 0;
  font-size: 0.92rem;
  color: var(--muted);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.table th,
.table td {
  padding: 0.55rem 0.65rem;
  text-align: left;
  border-bottom: 1px solid var(--nav-border);
  vertical-align: top;
}
.table th {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  white-space: nowrap;
}
.table .num {
  text-align: right;
  white-space: nowrap;
}
.ref-id-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.35rem;
}
.ref-open-in-list {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 0.1rem;
  padding: 0.12rem;
  border-radius: 6px;
  color: var(--accent);
  line-height: 0;
  transition: background 0.15s ease, color 0.15s ease;
}
.ref-open-in-list:hover {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  color: var(--text-h);
}
.ref-open-in-list:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.table tbody tr.client-row-highlight td {
  animation: clientRowHighlight 3.2s ease-out forwards;
}
@keyframes clientRowHighlight {
  0% {
    background-color: color-mix(in srgb, var(--accent) 30%, transparent);
  }
  35% {
    background-color: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  100% {
    background-color: transparent;
  }
}
.mono-num {
  font-variant-numeric: tabular-nums;
}
/* Одна строка по ширине контента; на узком экране таблица скроллится в AdminTableWrap */
.tg-cell {
  white-space: nowrap;
  vertical-align: middle;
}
.muted {
  color: var(--muted);
}
.error-cell {
  color: var(--danger, #c62828);
}
</style>
