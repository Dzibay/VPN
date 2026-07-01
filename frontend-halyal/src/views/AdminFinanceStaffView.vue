<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminPeriodPresets from '../components/AdminPeriodPresets.vue'
import AdminStaffShell from '../components/AdminStaffShell.vue'
import FinanceOverviewTab from './finance/FinanceOverviewTab.vue'
import FinanceIncomeTab from './finance/FinanceIncomeTab.vue'
import FinanceExpensesTab from './finance/FinanceExpensesTab.vue'
import FinanceOperationsTab from './finance/FinanceOperationsTab.vue'
import FinanceSettingsTab from './finance/FinanceSettingsTab.vue'
import { useMskPeriodRange } from '../composables/useMskPeriodRange.js'
import { FINANCE_PERIOD_PRESETS } from '../utils/mskPeriodRange.js'

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

const {
  periodPreset,
  customFrom,
  customTo,
  computedRange,
} = useMskPeriodRange(FINANCE_PERIOD_PRESETS, 'year')

const rangeFrom = computed(() => computedRange.value.from)
const rangeTo = computed(() => computedRange.value.to)
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

      <AdminPeriodPresets
        v-if="showPeriod"
        v-model="periodPreset"
        v-model:custom-from="customFrom"
        v-model:custom-to="customTo"
        :presets="FINANCE_PERIOD_PRESETS"
        variant="segmented"
      />
    </template>

    <FinanceOverviewTab v-if="activeTab === 'overview'" :from="rangeFrom" :to="rangeTo" />
    <FinanceIncomeTab v-else-if="activeTab === 'income'" />
    <FinanceExpensesTab v-else-if="activeTab === 'expenses'" />
    <FinanceOperationsTab v-else-if="activeTab === 'operations'" />
    <FinanceSettingsTab v-else-if="activeTab === 'settings'" />
  </AdminStaffShell>
</template>

<style scoped>
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
</style>
