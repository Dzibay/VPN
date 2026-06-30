<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import AppRefreshButton from '../components/AppRefreshButton.vue'
import StaffReferralGroupSuggestInput from '../components/StaffReferralGroupSuggestInput.vue'
import StaffReferralLinkSuggestInput from '../components/StaffReferralLinkSuggestInput.vue'
import StateNote from '../components/StateNote.vue'
import {
  formatUtcCalendarDayShort,
  utcTodayIso,
} from '../utils/mskDate.js'
import { fetchJson } from '../api/client.js'

const loading = ref(false)
const linksLoading = ref(false)
const groupsLoading = ref(false)
const error = ref(null)
/** @type {import('vue').Ref<Array<{ id: number; token: string; owner_kind: string; owner_user_id?: number | null }>>} */
const referralLinks = ref([])
/** @type {import('vue').Ref<Array<{ id: number; name: string; color: string; link_ids: number[] }>>} */
const referralGroups = ref([])

/** all | token | group */
const filterMode = ref('all')
const filterLinkId = ref('')
const filterGroupId = ref('')

/** @type {import('vue').Ref<{ registrations_total: number; users_with_traffic: number; users_with_subscription_device?: number; users_with_payment?: number; active_users_today_utc?: number; clicks_total?: number | null } | null>} */
const data = ref(null)

const filterModes = [
  { value: 'all', label: 'Все' },
  { value: 'token', label: 'Токен' },
  { value: 'group', label: 'Группа' },
]

const hasTokenFilter = computed(
  () => filterMode.value === 'token' && filterLinkId.value !== '',
)
const hasGroupFilter = computed(
  () => filterMode.value === 'group' && filterGroupId.value !== '',
)
const hasScopedFilter = computed(() => hasTokenFilter.value || hasGroupFilter.value)

const selectedGroup = computed(() => {
  if (!hasGroupFilter.value) return null
  const id = Number(filterGroupId.value)
  return referralGroups.value.find((g) => Number(g.id) === id) ?? null
})

function funnelUrl() {
  const base = '/api/referral-links/funnel'
  if (hasGroupFilter.value) {
    const id = Number(filterGroupId.value)
    if (Number.isFinite(id) && id >= 1) {
      return `${base}?referral_link_group_id=${id}`
    }
  }
  if (hasTokenFilter.value) {
    const id = Number(filterLinkId.value)
    if (Number.isFinite(id) && id >= 1) {
      return `${base}?referral_link_id=${id}`
    }
  }
  return base
}

const registrations = computed(() => data.value?.registrations_total ?? 0)
const trafficUsers = computed(() => data.value?.users_with_traffic ?? 0)
const deviceUsers = computed(
  () => data.value?.users_with_subscription_device ?? 0,
)
const activeToday = computed(() => data.value?.active_users_today_utc ?? 0)
const payingUsers = computed(() => data.value?.users_with_payment ?? 0)

const clicks = computed(() => {
  if (!hasScopedFilter.value) return 0
  const c = data.value?.clicks_total
  return c != null && Number.isFinite(Number(c)) ? Math.max(0, Number(c)) : 0
})

const funnelSteps = computed(() => {
  /** @type {Array<{ key: string; label: string; value: number; theme: string; connector: string | null; connectorHint?: string | null }>} */
  const steps = []

  if (hasScopedFilter.value) {
    steps.push({
      key: 'clicks',
      label: hasGroupFilter.value ? 'Клики по группе' : 'Клики по ссылке',
      value: clicks.value,
      theme: 'clicks',
      connector: 'клик → регистрация',
    })
  }

  steps.push({
    key: 'registrations',
    label: hasScopedFilter.value
      ? hasGroupFilter.value
        ? 'Регистрации по группе (Telegram / email ✓)'
        : 'Регистрации по ссылке (Telegram / email ✓)'
      : 'Пользователей в базе (Telegram / email ✓)',
    value: registrations.value,
    theme: 'registrations',
    connector: hasScopedFilter.value
      ? 'регистрации → с устройством'
      : 'доля с устройством',
  })

  steps.push({
    key: 'devices',
    label: 'С подключённым устройством',
    value: deviceUsers.value,
    theme: 'devices',
    connector: 'устройства → трафик',
  })

  steps.push({
    key: 'traffic',
    label: 'Пользователей с трафиком ≠ 0',
    value: trafficUsers.value,
    theme: 'traffic',
    connector: 'трафик → оплаты',
  })

  steps.push({
    key: 'paying',
    label: 'Оплативших пользователей',
    value: payingUsers.value,
    theme: 'paying',
    connector: 'оплаты → активные',
    connectorHint: `(${formatUtcCalendarDayShort(utcTodayIso())}, UTC-день трафика)`,
  })

  steps.push({
    key: 'active',
    label: 'Активные за день',
    value: activeToday.value,
    theme: 'active',
    connector: null,
  })

  return steps.map((step, idx, arr) => {
    const prev = idx > 0 ? arr[idx - 1].value : null
    const next = idx < arr.length - 1 ? arr[idx + 1].value : null
    let connectorPct = null
    if (step.connector && next != null) {
      connectorPct = step.value > 0 ? (next / step.value) * 100 : 0
    }
    return {
      ...step,
      prevValue: prev,
      connectorPct,
    }
  })
})

const funnelBase = computed(() => {
  const first = funnelSteps.value[0]?.value ?? 0
  return Math.max(first, 1)
})

const maxVal = computed(() => {
  const nums = funnelSteps.value.map((s) => s.value)
  return Math.max(...nums, 1)
})

function barPct(n) {
  return Math.min(100, (n / maxVal.value) * 100)
}

function pctOfBase(n) {
  if (!funnelBase.value) return null
  return (n / funnelBase.value) * 100
}

function pctOfPrev(n, prev) {
  if (prev == null || prev === 0) return null
  return (n / prev) * 100
}

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

async function loadReferralGroups() {
  groupsLoading.value = true
  try {
    referralGroups.value = await fetchJson('/api/referral-link-groups')
  } catch {
    referralGroups.value = []
  } finally {
    groupsLoading.value = false
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

function setFilterMode(mode) {
  if (filterMode.value === mode) return
  filterMode.value = mode
  filterLinkId.value = ''
  filterGroupId.value = ''
  void loadFunnel()
}

function onTokenSelect() {
  filterMode.value = 'token'
  filterGroupId.value = ''
  void loadFunnel()
}

function onTokenClear() {
  filterLinkId.value = ''
  void loadFunnel()
}

function onGroupSelect() {
  filterMode.value = 'group'
  filterLinkId.value = ''
  void loadFunnel()
}

function onGroupClear() {
  filterGroupId.value = ''
  void loadFunnel()
}

watch(filterLinkId, (v, prev) => {
  if (v === prev) return
  if (v) filterGroupId.value = ''
})

watch(filterGroupId, (v, prev) => {
  if (v === prev) return
  if (v) filterLinkId.value = ''
})

onMounted(async () => {
  await Promise.all([loadReferralLinks(), loadReferralGroups()])
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
                hasScopedFilter
                  ? 'Клики → регистрации → оплаты → активность'
                  : 'Пользователи → оплаты → активность'
              }}
            </h2>
            <AppRefreshButton :busy="loading" @click="loadFunnel" />
          </div>
          <p v-if="hasGroupFilter && selectedGroup" class="filter-context">
            <span
              class="filter-context__dot"
              :style="{ background: selectedGroup.color }"
              aria-hidden="true"
            />
            Группа «{{ selectedGroup.name }}» ·
            {{ selectedGroup.link_ids?.length ?? 0 }} токенов
          </p>
        </div>

        <div class="head-filter-row">
          <div class="filter-mode" role="tablist" aria-label="Тип фильтра воронки">
            <button
              v-for="m in filterModes"
              :key="m.value"
              type="button"
              class="filter-mode__btn"
              :class="{ 'filter-mode__btn--active': filterMode === m.value }"
              role="tab"
              :aria-selected="filterMode === m.value"
              @click="setFilterMode(m.value)"
            >
              {{ m.label }}
            </button>
          </div>

          <p v-if="filterMode === 'all'" class="filter-hint muted">
            Сводка по всем пользователям
          </p>

          <label v-else-if="filterMode === 'token'" class="filter-field">
            <StaffReferralLinkSuggestInput
              v-model="filterLinkId"
              input-id="funnel-ref-token"
              :items="referralLinks"
              :disabled="linksLoading"
              placeholder="Токен, id или источник"
              @select="onTokenSelect"
              @clear="onTokenClear"
            />
          </label>

          <label v-else-if="filterMode === 'group'" class="filter-field">
            <StaffReferralGroupSuggestInput
              v-model="filterGroupId"
              input-id="funnel-ref-group"
              :items="referralGroups"
              :disabled="groupsLoading"
              placeholder="Название группы"
              @select="onGroupSelect"
              @clear="onGroupClear"
            />
          </label>
        </div>
      </div>
    </template>

    <section class="panel" aria-live="polite">
      <StateNote v-if="loading && !data" loading />
      <p v-else-if="error" class="err">{{ error }}</p>
      <template v-else-if="data">
        <div class="funnel-wrap">
          <article
            v-for="(step, idx) in funnelSteps"
            :key="step.key"
            class="funnel-card"
            :class="`funnel-card--${step.theme}`"
          >
            <div class="funnel-card__main">
              <div class="funnel-card__icon" aria-hidden="true">
                <svg
                  v-if="step.theme === 'clicks'"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <path d="M4 4l7 16 2-7 7-2L4 4z" stroke-linejoin="round" />
                </svg>
                <svg
                  v-else-if="step.theme === 'registrations'"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                <svg
                  v-else-if="step.theme === 'devices'"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <rect x="5" y="2" width="14" height="20" rx="2" />
                  <path d="M12 18h.01" />
                </svg>
                <svg
                  v-else-if="step.theme === 'traffic'"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <path d="M3 3v18h18" />
                  <path d="M7 16l4-5 4 3 5-7" />
                </svg>
                <svg
                  v-else-if="step.theme === 'paying'"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <rect x="2" y="5" width="20" height="14" rx="2" />
                  <path d="M2 10h20" />
                </svg>
                <svg
                  v-else
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.75"
                >
                  <path
                    d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.3.5-2.5 1.5-3.5z"
                  />
                </svg>
              </div>

              <div class="funnel-card__body">
                <div class="funnel-card__head">
                  <span class="funnel-card__label">{{ step.label }}</span>
                  <span class="funnel-card__num">{{
                    step.value.toLocaleString('ru-RU')
                  }}</span>
                </div>
                <div class="funnel-card__track">
                  <div
                    class="funnel-card__fill"
                    :style="{ width: barPct(step.value) + '%' }"
                  />
                </div>
                <p v-if="step.connector" class="funnel-card__connector">
                  <span class="funnel-card__connector-pct">{{
                    fmtPct(step.connectorPct)
                  }}</span>
                  <span class="funnel-card__connector-caption">{{
                    step.connector
                  }}</span>
                  <span
                    v-if="step.connectorHint"
                    class="funnel-card__connector-hint"
                    >{{ step.connectorHint }}</span
                  >
                </p>
              </div>
            </div>

            <aside class="funnel-card__stats">
              <div class="funnel-stat">
                <span class="funnel-stat__label">От общей базы</span>
                <span class="funnel-stat__pct">{{
                  fmtPct(pctOfBase(step.value))
                }}</span>
                <span class="funnel-stat__ratio"
                  >{{ step.value.toLocaleString('ru-RU') }} из
                  {{ funnelBase.toLocaleString('ru-RU') }}</span
                >
              </div>
              <div v-if="idx > 0" class="funnel-stat">
                <span class="funnel-stat__label">От предыдущего этапа</span>
                <span class="funnel-stat__pct">{{
                  fmtPct(pctOfPrev(step.value, step.prevValue))
                }}</span>
                <span class="funnel-stat__ratio"
                  >{{ step.value.toLocaleString('ru-RU') }} из
                  {{
                    (step.prevValue ?? 0).toLocaleString('ru-RU')
                  }}</span
                >
              </div>
            </aside>
          </article>
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
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 1rem;
}

.head-filter-row .filter-field {
  flex: 1;
  min-width: min(100%, 16rem);
  max-width: min(100%, 26rem);
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

.filter-context {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}

.filter-context__dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 999px;
  flex-shrink: 0;
}

.filter-mode {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0.2rem;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--card-border);
  width: fit-content;
}

.filter-mode__btn {
  border: none;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.filter-mode__btn:hover {
  color: var(--text-h);
}

.filter-mode__btn--active {
  background: color-mix(in srgb, var(--accent) 18%, var(--card-bg));
  color: var(--text-h);
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

.filter-hint {
  margin: 0;
  font-size: 0.82rem;
  flex: 1;
  min-width: min(100%, 16rem);
  padding-bottom: 0.35rem;
}

.panel {
  padding: 1rem 0 2rem;
}

.err {
  color: var(--danger);
  margin: 0;
}

.funnel-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 100%;
}

.funnel-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1rem;
  align-items: stretch;
  padding: 1rem 1.1rem;
  border-radius: 1rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: 0 1px 2px color-mix(in srgb, var(--text) 6%, transparent);
}

.funnel-card__main {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  min-width: 0;
}

.funnel-card__icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.funnel-card__icon svg {
  width: 1.25rem;
  height: 1.25rem;
}

.funnel-card__body {
  flex: 1;
  min-width: 0;
}

.funnel-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.55rem;
}

.funnel-card__label {
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text-h);
  line-height: 1.35;
}

.funnel-card__num {
  font-family: ui-monospace, monospace;
  font-size: 1.15rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.funnel-card__track {
  height: 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface) 80%, var(--card-border));
  overflow: hidden;
}

.funnel-card__fill {
  height: 100%;
  border-radius: inherit;
  min-width: 3px;
  transition: width 0.45s ease;
}

.funnel-card__connector {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.5rem;
  margin: 0.45rem 0 0;
  font-size: 0.72rem;
}

.funnel-card__connector-pct {
  font-family: ui-monospace, monospace;
  font-size: 0.82rem;
  font-weight: 800;
  color: var(--text-h);
}

.funnel-card__connector-caption {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}

.funnel-card__connector-hint {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: var(--muted);
}

.funnel-card__stats {
  display: flex;
  gap: 1.25rem;
  padding-left: 1rem;
  border-left: 1px solid var(--card-border);
  align-items: center;
}

.funnel-stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 7.5rem;
}

.funnel-stat__label {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.funnel-stat__pct {
  font-family: ui-monospace, monospace;
  font-size: 1.35rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.funnel-stat__ratio {
  font-size: 0.72rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.funnel-card--clicks .funnel-card__icon {
  background: color-mix(in srgb, var(--accent) 16%, var(--card-bg));
  color: var(--accent);
}

.funnel-card--clicks .funnel-card__num,
.funnel-card--clicks .funnel-stat__pct {
  color: var(--accent);
}

.funnel-card--clicks .funnel-card__fill {
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--accent) 70%, #1a3d32),
    var(--accent)
  );
}

.funnel-card--registrations .funnel-card__icon {
  background: color-mix(in srgb, #22c55e 16%, var(--card-bg));
  color: #22c55e;
}

.funnel-card--registrations .funnel-card__num,
.funnel-card--registrations .funnel-stat__pct {
  color: #22c55e;
}

.funnel-card--registrations .funnel-card__fill {
  background: linear-gradient(90deg, #16a34a, #4ade80);
}

.funnel-card--devices .funnel-card__icon {
  background: color-mix(in srgb, #a78bfa 18%, var(--card-bg));
  color: #a78bfa;
}

.funnel-card--devices .funnel-card__num,
.funnel-card--devices .funnel-stat__pct {
  color: #a78bfa;
}

.funnel-card--devices .funnel-card__fill {
  background: linear-gradient(90deg, #7c3aed, #c4b5fd);
}

.funnel-card--traffic .funnel-card__icon {
  background: color-mix(in srgb, #14b8a6 16%, var(--card-bg));
  color: #14b8a6;
}

.funnel-card--traffic .funnel-card__num,
.funnel-card--traffic .funnel-stat__pct {
  color: #14b8a6;
}

.funnel-card--traffic .funnel-card__fill {
  background: linear-gradient(90deg, #0d9488, #5eead4);
}

.funnel-card--paying .funnel-card__icon {
  background: color-mix(in srgb, #f97316 16%, var(--card-bg));
  color: #f97316;
}

.funnel-card--paying .funnel-card__num,
.funnel-card--paying .funnel-stat__pct {
  color: #f97316;
}

.funnel-card--paying .funnel-card__fill {
  background: linear-gradient(90deg, #ea580c, #fdba74);
}

.funnel-card--active .funnel-card__icon {
  background: color-mix(in srgb, #38bdf8 16%, var(--card-bg));
  color: #38bdf8;
}

.funnel-card--active .funnel-card__num,
.funnel-card--active .funnel-stat__pct {
  color: #38bdf8;
}

.funnel-card--active .funnel-card__fill {
  background: linear-gradient(90deg, #0284c7, #7dd3fc);
}

@media (max-width: 760px) {
  .funnel-card {
    grid-template-columns: 1fr;
  }

  .funnel-card__stats {
    padding-left: 0;
    padding-top: 0.75rem;
    border-left: none;
    border-top: 1px solid var(--card-border);
  }
}

.muted {
  color: var(--muted);
}
</style>
