<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import FinanceOverviewTab from './finance/FinanceOverviewTab.vue'
import FinanceIncomeTab from './finance/FinanceIncomeTab.vue'
import FinanceExpensesTab from './finance/FinanceExpensesTab.vue'
import FinanceOperationsTab from './finance/FinanceOperationsTab.vue'
import FinanceSettingsTab from './finance/FinanceSettingsTab.vue'
import { mskTodayIso } from '../utils/mskDate.js'

const TABS = [
  { key: 'overview', label: 'Обзор' },
  { key: 'income', label: 'Доходы' },
  { key: 'expenses', label: 'Расходы' },
  { key: 'operations', label: 'Операции' },
  { key: 'settings', label: 'Налоги и настройки' },
]
const TAB_KEYS = TABS.map((t) => t.key)

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => {
  const t = String(route.query.tab || '')
  return TAB_KEYS.includes(t) ? t : 'overview'
})

function selectTab(key) {
  if (key === activeTab.value) return
  router.replace({ query: { ...route.query, tab: key } })
}

// --- период (для вкладки «Обзор») ---
const PERIOD_PRESETS = [
  { key: 'month', label: 'Этот месяц' },
  { key: 'prev_month', label: 'Прошлый месяц' },
  { key: 'quarter', label: 'Квартал' },
  { key: 'year', label: 'Этот год' },
  { key: 'all', label: 'Всё время' },
  { key: 'custom', label: 'Период' },
]

const periodPreset = ref('year')
const customFrom = ref('')
const customTo = ref('')

// Период считается по календарю Москвы (как RPC выручки и staff-аналитика),
// а не по TZ браузера: иначе у клиента в другом поясе «этот месяц» съезжает.
const pad2 = (n) => String(n).padStart(2, '0')

function mskParts() {
  const [y, m, d] = mskTodayIso().split('-').map(Number)
  return { y, m, d }
}
function monthStart(y, m) {
  return `${y}-${pad2(m)}-01`
}
function lastDayOfPrevMonth(y, m) {
  // m — 1-based текущий месяц; день 0 текущего месяца = последний день предыдущего.
  const dt = new Date(Date.UTC(y, m - 1, 0))
  return `${dt.getUTCFullYear()}-${pad2(dt.getUTCMonth() + 1)}-${pad2(dt.getUTCDate())}`
}

const computedRange = computed(() => {
  const { y, m } = mskParts()
  const today = mskTodayIso()
  switch (periodPreset.value) {
    case 'month':
      return { from: monthStart(y, m), to: today }
    case 'prev_month': {
      const py = m === 1 ? y - 1 : y
      const pm = m === 1 ? 12 : m - 1
      return { from: monthStart(py, pm), to: lastDayOfPrevMonth(y, m) }
    }
    case 'quarter': {
      const qStart = Math.floor((m - 1) / 3) * 3 + 1
      return { from: monthStart(y, qStart), to: today }
    }
    case 'all':
      return { from: '2020-01-01', to: today }
    case 'custom':
      return {
        from: customFrom.value || monthStart(y, 1),
        to: customTo.value || today,
      }
    case 'year':
    default:
      return { from: monthStart(y, 1), to: today }
  }
})

const rangeFrom = computed(() => computedRange.value.from)
const rangeTo = computed(() => computedRange.value.to)

watch(periodPreset, (p) => {
  if (p === 'custom') {
    const { y } = mskParts()
    if (!customFrom.value) customFrom.value = monthStart(y, 1)
    if (!customTo.value) customTo.value = mskTodayIso()
  }
})

const showPeriod = computed(() => activeTab.value === 'overview')
</script>

<template>
  <AdminStaffShell title="Финансы">
    <template #headerExtras>
      <nav class="subtabs" aria-label="Разделы финансов">
        <button
          v-for="t in TABS"
          :key="t.key"
          type="button"
          class="subtab"
          :class="{ 'subtab--active': activeTab === t.key }"
          @click="selectTab(t.key)"
        >
          {{ t.label }}
        </button>
      </nav>

      <div v-if="showPeriod" class="period-row">
        <div class="period-presets" role="group" aria-label="Период">
          <button
            v-for="p in PERIOD_PRESETS"
            :key="p.key"
            type="button"
            class="period-btn"
            :class="{ 'period-btn--active': periodPreset === p.key }"
            @click="periodPreset = p.key"
          >
            {{ p.label }}
          </button>
        </div>
        <div v-if="periodPreset === 'custom'" class="period-custom">
          <input v-model="customFrom" type="date" class="period-date" aria-label="С" />
          <span class="period-sep">—</span>
          <input v-model="customTo" type="date" class="period-date" aria-label="По" />
        </div>
      </div>
    </template>

    <FinanceOverviewTab v-if="activeTab === 'overview'" :from="rangeFrom" :to="rangeTo" />
    <FinanceIncomeTab v-else-if="activeTab === 'income'" />
    <FinanceExpensesTab v-else-if="activeTab === 'expenses'" />
    <FinanceOperationsTab v-else-if="activeTab === 'operations'" />
    <FinanceSettingsTab v-else-if="activeTab === 'settings'" />
  </AdminStaffShell>
</template>

<style scoped>
/* Сегментированная панель — на всю ширину, без скруглений и зазоров (не как pill admin-tabs). */
.subtabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  width: 100%;
  gap: 0;
  margin: 0 0 0.85rem;
  padding: 0;
  border: 1px solid var(--card-border);
  border-radius: 0;
  overflow: hidden;
  background: color-mix(in srgb, var(--surface) 92%, black);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-h) 6%, transparent);
}
.subtab {
  margin: 0;
  padding: 0.7rem 0.5rem;
  border: none;
  border-radius: 0;
  border-right: 1px solid var(--card-border);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 700;
  line-height: 1.25;
  text-align: center;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  cursor: pointer;
  color: var(--muted);
  background: transparent;
  min-height: 2.75rem;
  transition:
    color 0.15s ease,
    background 0.15s ease,
    box-shadow 0.15s ease;
}
.subtab:last-child {
  border-right: none;
}
.subtab:hover:not(.subtab--active) {
  color: var(--text-h);
  background: color-mix(in srgb, var(--text-h) 5%, transparent);
}
.subtab--active {
  color: var(--text-h);
  background: var(--card-bg, var(--surface));
  box-shadow: inset 0 -3px 0 var(--accent);
}
.subtab:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 2px var(--accent);
  z-index: 1;
}
.subtab--active:focus-visible {
  box-shadow:
    inset 0 -3px 0 var(--accent),
    inset 0 0 0 2px color-mix(in srgb, var(--accent) 55%, transparent);
}

@media (max-width: 720px) {
  .subtabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .subtab {
    font-size: 0.72rem;
    padding: 0.65rem 0.35rem;
    text-transform: none;
    letter-spacing: 0;
  }
  .subtab:nth-child(2) {
    border-right: none;
  }
  .subtab:nth-child(1),
  .subtab:nth-child(2) {
    border-bottom: 1px solid var(--card-border);
  }
}

.period-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
  margin-bottom: 1.1rem;
}
.period-presets {
  display: inline-flex;
  flex-wrap: wrap;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  overflow: hidden;
  background: var(--surface);
}
.period-btn {
  margin: 0;
  padding: 0.4rem 0.7rem;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
  border-right: 1px solid var(--card-border);
}
.period-btn:last-child {
  border-right: none;
}
.period-btn:hover {
  color: var(--text-h);
  background: rgba(127, 127, 127, 0.08);
}
.period-btn--active {
  color: var(--text-h);
  background: rgba(88, 214, 141, 0.14);
}
.period-custom {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}
.period-date {
  font: inherit;
  padding: 0.4rem 0.55rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
}
.period-sep {
  color: var(--muted);
}
</style>
