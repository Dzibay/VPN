<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StateNote from '../components/StateNote.vue'
import {
  formatUtcCalendarDayShort,
  utcTodayIso,
} from '../utils/mskDate.js'
import { fetchJson } from '../api/client.js'

const loading = ref(false)
const linksLoading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number; token: string; owner_kind: string }>>} */
const referralLinks = ref([])
/** '' — без фильтра (воронка по всей базе) */
const filterLinkId = ref('')
/** @type {import('vue').Ref<{ registrations_total: number; users_with_traffic: number; users_with_subscription_device?: number; active_users_today_utc?: number; clicks_total?: number | null } | null>} */
const data = ref(null)

const hasLinkFilter = computed(
  () => filterLinkId.value !== '' && filterLinkId.value != null,
)

function funnelUrl() {
  const base = '/api/referral-links/funnel'
  if (!hasLinkFilter.value) return base
  const id = Number(filterLinkId.value)
  if (!Number.isFinite(id) || id < 1) return base
  return `${base}?referral_link_id=${id}`
}

const registrations = computed(() => data.value?.registrations_total ?? 0)
const trafficUsers = computed(() => data.value?.users_with_traffic ?? 0)
const deviceUsers = computed(
  () => data.value?.users_with_subscription_device ?? 0,
)
const activeToday = computed(() => data.value?.active_users_today_utc ?? 0)

const clicks = computed(() => {
  if (!hasLinkFilter.value) return 0
  const c = data.value?.clicks_total
  return c != null && Number.isFinite(Number(c)) ? Math.max(0, Number(c)) : 0
})

const maxVal = computed(() => {
  const nums = [
    registrations.value,
    trafficUsers.value,
    deviceUsers.value,
    activeToday.value,
  ]
  if (hasLinkFilter.value) {
    return Math.max(clicks.value, ...nums, 1)
  }
  return Math.max(...nums, 1)
})

function barPct(n) {
  return Math.min(100, (n / maxVal.value) * 100)
}

/** Клик → регистрация (только при выбранной реф. ссылке) */
const pctClickToReg = computed(() => {
  if (!hasLinkFilter.value || !clicks.value) return null
  return (registrations.value / clicks.value) * 100
})

/** Регистрации / пользователи в БД → с подключённым устройством */
const pctRegToDevices = computed(() => {
  if (!registrations.value) return null
  return (deviceUsers.value / registrations.value) * 100
})

/** С устройством → пользователи с ненулевым трафиком */
const pctDevicesToTraffic = computed(() => {
  if (!deviceUsers.value) return null
  return (trafficUsers.value / deviceUsers.value) * 100
})

/** С трафиком → активные за текущий день UTC */
const pctTrafficToActive = computed(() => {
  if (!trafficUsers.value) return null
  return (activeToday.value / trafficUsers.value) * 100
})

function fmtPct(x) {
  if (x == null || Number.isNaN(x)) return '—'
  if (x >= 100) return `${x.toFixed(1)}%`
  if (x >= 10) return `${x.toFixed(1)}%`
  return `${x.toFixed(2)}%`
}

async function loadReferralLinks() {
  linksLoading.value = true
  try {
    referralLinks.value = await fetchJson('/api/referral-links')
  } catch {
    referralLinks.value = []
  } finally {
    linksLoading.value = false
  }
}

async function loadFunnel() {
  loading.value = true
  error.value = null
  try {
    data.value = await fetchJson(funnelUrl())
  } catch (e) {
    error.value = e.message || String(e)
    data.value = null
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  void loadFunnel()
}

onMounted(async () => {
  await loadReferralLinks()
  await loadFunnel()
})
</script>

<template>
  <AdminStaffShell title="Воронка">
    <template #headerExtras>
      <div class="head-row">
        <div class="head-text">
          <div class="section-heading-row">
            <h2 class="section-heading">
              {{
                hasLinkFilter
                  ? 'Клики → регистрации → активность'
                  : 'Пользователи → активность'
              }}
            </h2>
            <AppRefreshButton :busy="loading" @click="loadFunnel" />
          </div>
        </div>
        <div class="head-filter-row">
          <label class="filter-field">
            <span class="filter-label">Реферальная ссылка</span>
            <select
              v-model="filterLinkId"
              class="filter-select"
              :disabled="linksLoading"
              aria-label="Фильтр по реферальной ссылке"
              @change="onFilterChange"
            >
              <option value="">Все пользователи</option>
              <option
                v-for="r in referralLinks"
                :key="r.id"
                :value="String(r.id)"
              >
                #{{ r.id }} · {{ r.token }} ({{ r.owner_kind }})
              </option>
            </select>
          </label>
        </div>
      </div>
    </template>

    <section class="panel" aria-live="polite">
      <StateNote v-if="loading && !data" loading />
      <p v-else-if="error" class="err">{{ error }}</p>
      <template v-else-if="data">
        <div class="funnel-wrap">
          <template v-if="hasLinkFilter">
            <div class="funnel-step">
              <div class="funnel-label-row">
                <span class="funnel-label">Клики по ссылке</span>
                <span class="funnel-num">{{ clicks.toLocaleString('ru-RU') }}</span>
              </div>
              <div class="funnel-track">
                <div
                  class="funnel-fill funnel-fill--a"
                  :style="{ width: barPct(clicks) + '%' }"
                />
              </div>
            </div>

            <div class="funnel-connector" aria-hidden="true">
              <span class="connector-pct">{{
                pctClickToReg != null ? fmtPct(pctClickToReg) : '—'
              }}</span>
              <span class="connector-caption">клик → регистрация</span>
            </div>
          </template>

          <div class="funnel-step">
            <div class="funnel-label-row">
              <span class="funnel-label">{{
                hasLinkFilter
                  ? 'Регистрации по ссылке (Telegram / email ✓)'
                  : 'Пользователей в базе (Telegram / email ✓)'
              }}</span>
              <span class="funnel-num">{{ registrations.toLocaleString('ru-RU') }}</span>
            </div>
            <div class="funnel-track">
              <div
                class="funnel-fill"
                :class="hasLinkFilter ? 'funnel-fill--b' : 'funnel-fill--a'"
                :style="{ width: barPct(registrations) + '%' }"
              />
            </div>
          </div>

          <div class="funnel-connector funnel-connector--soft" aria-hidden="true">
            <span class="connector-pct">{{
              pctRegToDevices != null ? fmtPct(pctRegToDevices) : '—'
            }}</span>
            <span class="connector-caption">
              {{
                hasLinkFilter
                  ? 'регистрации → с устройством'
                  : 'доля с устройством'
              }}
            </span>
          </div>

          <div class="funnel-step">
            <div class="funnel-label-row">
              <span class="funnel-label"
                >С подключённым устройством</span
              >
              <span class="funnel-num">{{ deviceUsers.toLocaleString('ru-RU') }}</span>
            </div>
            <div class="funnel-track">
              <div
                class="funnel-fill funnel-fill--d"
                :style="{ width: barPct(deviceUsers) + '%' }"
              />
            </div>
          </div>

          <div class="funnel-connector funnel-connector--soft" aria-hidden="true">
            <span class="connector-pct">{{
              pctDevicesToTraffic != null ? fmtPct(pctDevicesToTraffic) : '—'
            }}</span>
            <span class="connector-caption">устройства → трафик</span>
          </div>

          <div class="funnel-step">
            <div class="funnel-label-row">
              <span class="funnel-label">Пользователей с трафиком ≠ 0</span>
              <span class="funnel-num">{{ trafficUsers.toLocaleString('ru-RU') }}</span>
            </div>
            <div class="funnel-track">
              <div
                class="funnel-fill funnel-fill--c"
                :style="{ width: barPct(trafficUsers) + '%' }"
              />
            </div>
          </div>

          <div class="funnel-connector funnel-connector--soft" aria-hidden="true">
            <span class="connector-pct">{{
              pctTrafficToActive != null ? fmtPct(pctTrafficToActive) : '—'
            }}</span>
            <span class="connector-caption"
              >трафик → активные
              <span class="connector-hint"
                >({{ formatUtcCalendarDayShort(utcTodayIso()) }}, UTC-день трафика)</span
              ></span
            >
          </div>

          <div class="funnel-step">
            <div class="funnel-label-row">
              <span class="funnel-label"
                >Активные за день</span
              >
              <span class="funnel-num">{{ activeToday.toLocaleString('ru-RU') }}</span>
            </div>
            <div class="funnel-track">
              <div
                class="funnel-fill funnel-fill--e"
                :style="{ width: barPct(activeToday) + '%' }"
              />
            </div>
          </div>
        </div>
      </template>
    </section>
  </AdminStaffShell>
</template>

<style scoped>
.head-row {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.85rem;
  margin-bottom: 0.35rem;
}

.head-filter-row {
  width: 100%;
}

.head-filter-row .filter-field {
  max-width: min(100%, 22rem);
}

.head-text {
  width: 100%;
  min-width: 0;
}

.section-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
}

.section-heading {
  margin: 0;
  font-size: 1.05rem;
  color: var(--text-h);
  flex: 1;
  min-width: 0;
}

.section-heading-row .btn-secondary {
  flex-shrink: 0;
}

.filter-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: min(100%, 18rem);
}

.filter-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--muted);
}

.filter-select {
  font: inherit;
  font-size: 0.85rem;
  padding: 0.45rem 0.6rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  max-width: 22rem;
}

.panel {
  padding: 1rem 0 2rem;
}

.err {
  color: var(--danger);
  margin: 0;
}

.funnel-wrap {
  max-width: 40rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.funnel-step {
  padding: 0.65rem 0 0.5rem;
}

.funnel-label-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.4rem;
}

.funnel-label {
  font-size: 0.88rem;
  font-weight: 650;
  color: var(--text-h);
}

.funnel-num {
  font-family: ui-monospace, monospace;
  font-size: 1rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
}

.funnel-track {
  height: 14px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--card-border);
  overflow: hidden;
}

.funnel-fill {
  height: 100%;
  border-radius: inherit;
  min-width: 4px;
  transition: width 0.45s ease;
}

.funnel-fill--a {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--accent) 85%, #1a3d32),
    var(--accent)
  );
}

.funnel-fill--b {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--accent) 55%, #7cb8a8),
    color-mix(in srgb, var(--accent) 75%, #4a8f7c)
  );
}

.funnel-fill--c {
  background: linear-gradient(
    90deg,
    rgba(120, 200, 170, 0.55),
    color-mix(in srgb, var(--accent) 45%, #6bc4a8)
  );
}

.funnel-fill--d {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, #a78bfa 70%, #5b21b6),
    #a78bfa
  );
}

.funnel-fill--e {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, #38bdf8 55%, #0c4a6e),
    #38bdf8
  );
}

.funnel-connector {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 0.35rem 0 0.45rem 0.85rem;
  border-left: 2px solid color-mix(in srgb, var(--accent) 35%, var(--card-border));
  margin-left: 0.35rem;
}

.funnel-connector--soft {
  border-left-style: dashed;
  opacity: 0.92;
}

.connector-pct {
  font-family: ui-monospace, monospace;
  font-size: 0.92rem;
  font-weight: 800;
  color: var(--text-h);
}

.connector-caption {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.connector-hint {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
}
.muted {
  color: var(--muted);
}
</style>
