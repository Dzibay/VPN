<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminTableBulkBar from '../../components/AdminTableBulkBar.vue'
import AdminTableSelectTd from '../../components/AdminTableSelectTd.vue'
import AdminTableSelectTh from '../../components/AdminTableSelectTh.vue'
import AdminTableWrap from '../../components/AdminTableWrap.vue'
import AppModal from '../../components/AppModal.vue'
import AppPager from '../../components/AppPager.vue'
import AppRefreshButton from '../../components/AppRefreshButton.vue'
import { useOffsetPagination } from '../../composables/useOffsetPagination.js'
import { fetchJson } from '../../api/client.js'
import { getSessionRole } from '../../auth/session.js'
import { useAdminTableBulkSelect } from '../../composables/useAdminTableBulkSelect.js'
import { downloadCsv } from '../../utils/csv.js'
import { mskMonthInputDefault, mskTodayIso } from '../../utils/mskDate.js'

const isAdmin = computed(() => getSessionRole() === 'admin')

const loading = ref(false)
const error = ref(null)

/** @type {import('vue').Ref<Array<{id:number,slug:string,title:string,color:string,archived:boolean}>>} */
const categories = ref([])
const categoriesById = computed(() => {
  const m = new Map()
  for (const c of categories.value) m.set(c.id, c)
  return m
})
const activeCategories = computed(() => categories.value.filter((c) => !c.archived))
const cashAccounts = ref([])
const activeCashAccounts = computed(() => cashAccounts.value.filter((a) => a.active))

// --- разовые ---
const expenses = ref([])
const expTotal = ref(0)
const expLimit = 100

const {
  offset: expOffset,
  canPrev,
  canNext,
  rangeLabel: expRangeLabel,
  prev: expPrev,
  next: expNext,
  reset: resetExpPaging,
} = useOffsetPagination({
  limit: expLimit,
  total: () => expTotal.value,
  count: () => expenses.value.length,
  onChange: () => loadExpenses(),
})

const expRowIdsOnPage = computed(() => expenses.value.map((r) => Number(r.id)))
const bulk = useAdminTableBulkSelect({
  rowIdsOnPage: expRowIdsOnPage,
  enabled: isAdmin,
})
const expTableColspan = computed(() => 7 + (bulk.canBulkSelect ? 1 : 0))

// --- повторяющиеся ---
const recurring = ref([])

// --- модалки ---
const expModalOpen = ref(false)
const expSaving = ref(false)
const expFormError = ref(null)
const expForm = ref(blankExpenseForm())

const recModalOpen = ref(false)
const recSaving = ref(false)
const recFormError = ref(null)
const recForm = ref(blankRecurringForm())

function blankExpenseForm() {
  return {
    id: null,
    incurred_on: mskTodayIso(),
    amount: '',
    category_id: '',
    title: '',
    payment_source: 'company',
    paid_by_name: '',
    cash_account_id: '',
    paid_on: mskTodayIso(),
    note: '',
  }
}
function blankRecurringForm() {
  return {
    id: null,
    title: '',
    amount: '',
    category_id: '',
    day_of_month: '1',
    start_month: mskMonthInputDefault(),
    end_month: '',
    active: true,
    note: '',
  }
}

function money(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  if (!Number.isFinite(n)) return '0,00'
  return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtDate(d) {
  if (!d) return '—'
  const dt = new Date(`${d}T00:00:00Z`)
  if (Number.isNaN(dt.getTime())) return String(d)
  return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

function fmtMonth(d) {
  if (!d) return '—'
  const dt = new Date(`${String(d).slice(0, 7)}-01T00:00:00Z`)
  if (Number.isNaN(dt.getTime())) return String(d)
  return dt.toLocaleDateString('ru-RU', { month: 'short', year: 'numeric', timeZone: 'UTC' })
}

function categoryLabel(id) {
  if (id == null) return 'Без категории'
  return categoriesById.value.get(id)?.title ?? 'Без категории'
}
function categoryColor(id) {
  if (id == null) return '#94a3b8'
  return categoriesById.value.get(id)?.color ?? '#94a3b8'
}
function paymentSourceLabel(row) {
  if (row.payment_source === 'person') return `Оплатил: ${row.paid_by_name || 'человек'}`
  if (row.payment_source === 'unpaid') return 'Начислено, не оплачено'
  return 'С расчетника'
}
function accountLabel(id) {
  if (id == null) return 'По умолчанию'
  return cashAccounts.value.find((a) => Number(a.id) === Number(id))?.name ?? 'Счет'
}

function onExpenseRowClick(row, event) {
  if (!bulk.selectionMode) return
  if (event?.target?.closest?.('a, button, input, label')) return
  bulk.toggleRow(row.id)
}

async function deleteSelectedExpenses() {
  await deleteExpenses(bulk.selectedIds)
  bulk.exitSelectionMode()
}

async function loadCategories() {
  const data = await fetchJson('/api/admin/accounting/categories')
  categories.value = Array.isArray(data?.items) ? data.items : []
}
async function loadCashAccounts() {
  const data = await fetchJson('/api/admin/accounting/cash-accounts')
  cashAccounts.value = Array.isArray(data?.items) ? data.items : []
}
async function loadExpenses() {
  const params = new URLSearchParams({ limit: String(expLimit), offset: String(expOffset.value) })
  const data = await fetchJson(`/api/admin/accounting/expenses?${params.toString()}`)
  expenses.value = Array.isArray(data?.items) ? data.items : []
  expTotal.value = Number(data?.total) || 0
}
async function loadRecurring() {
  const data = await fetchJson('/api/admin/accounting/recurring-expenses')
  recurring.value = Array.isArray(data?.items) ? data.items : []
}

async function loadAll() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([loadCategories(), loadCashAccounts(), loadExpenses(), loadRecurring()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

// --- expense modal ---
function openExpenseCreate() {
  expForm.value = blankExpenseForm()
  expFormError.value = null
  expModalOpen.value = true
}
function openExpenseEdit(row) {
  expForm.value = {
    id: row.id,
    incurred_on: String(row.incurred_on).slice(0, 10),
    amount: String(row.amount),
    category_id: row.category_id ?? '',
    title: row.title ?? '',
    payment_source: row.payment_source || 'company',
    paid_by_name: row.paid_by_name ?? '',
    cash_account_id: row.cash_account_id ?? '',
    paid_on: row.paid_on ? String(row.paid_on).slice(0, 10) : String(row.incurred_on).slice(0, 10),
    note: row.note ?? '',
  }
  expFormError.value = null
  expModalOpen.value = true
}
function closeExpenseModal() {
  if (expSaving.value) return
  expModalOpen.value = false
}

async function submitExpense() {
  const f = expForm.value
  const amount = Number(String(f.amount).replace(',', '.'))
  if (!f.incurred_on) {
    expFormError.value = 'Укажите дату расхода.'
    return
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    expFormError.value = 'Сумма: положительное число.'
    return
  }
  if (!String(f.title).trim()) {
    expFormError.value = 'Укажите название расхода.'
    return
  }
  const body = {
    incurred_on: f.incurred_on,
    amount,
    category_id: f.category_id === '' ? null : Number(f.category_id),
    title: String(f.title).trim(),
    payment_source: f.payment_source,
    paid_by_name: f.payment_source === 'person' ? String(f.paid_by_name).trim() : null,
    cash_account_id: f.payment_source === 'company' && f.cash_account_id !== '' ? Number(f.cash_account_id) : null,
    paid_on: f.payment_source === 'company' ? f.paid_on || f.incurred_on : null,
    note: String(f.note).trim() || null,
  }
  if (f.payment_source === 'person' && !body.paid_by_name) {
    expFormError.value = 'Укажите, кто оплатил расход.'
    return
  }
  expSaving.value = true
  expFormError.value = null
  try {
    if (f.id) {
      await fetchJson(`/api/admin/accounting/expenses/${f.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
    } else {
      await fetchJson('/api/admin/accounting/expenses', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      resetExpPaging()
    }
    expModalOpen.value = false
    await loadExpenses()
  } catch (e) {
    expFormError.value = e.message || String(e)
  } finally {
    expSaving.value = false
  }
}

async function exportExpensesCsv() {
  try {
    const params = new URLSearchParams({ limit: '5000', offset: '0' })
    const data = await fetchJson(`/api/admin/accounting/expenses?${params.toString()}`)
    const items = Array.isArray(data?.items) ? data.items : []
    const rows = [['Дата', 'Категория', 'Название', 'Сумма', 'Комментарий']]
    for (const r of items) {
      rows.push([
        String(r.incurred_on).slice(0, 10),
        categoryLabel(r.category_id),
        r.title,
        r.amount,
        r.note ?? '',
      ])
    }
    downloadCsv('expenses.csv', rows)
  } catch (e) {
    error.value = e.message || String(e)
  }
}

async function deleteExpenses(ids) {
  if (!isAdmin.value || ids.length === 0 || bulk.deleting) return
  const ok = window.confirm(`Удалить расходы (${ids.length})? Действие необратимо.`)
  if (!ok) return
  bulk.deleting = true
  error.value = null
  try {
    await fetchJson('/api/admin/accounting/expenses', {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    })
    await loadExpenses()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    bulk.deleting = false
  }
}

// --- recurring modal ---
function openRecurringCreate() {
  recForm.value = blankRecurringForm()
  recFormError.value = null
  recModalOpen.value = true
}
function openRecurringEdit(row) {
  recForm.value = {
    id: row.id,
    title: row.title ?? '',
    amount: String(row.amount),
    category_id: row.category_id ?? '',
    day_of_month: String(row.day_of_month ?? 1),
    start_month: String(row.start_month).slice(0, 7),
    end_month: row.end_month ? String(row.end_month).slice(0, 7) : '',
    active: Boolean(row.active),
    note: row.note ?? '',
  }
  recFormError.value = null
  recModalOpen.value = true
}
function closeRecurringModal() {
  if (recSaving.value) return
  recModalOpen.value = false
}

async function submitRecurring() {
  const f = recForm.value
  const amount = Number(String(f.amount).replace(',', '.'))
  if (!String(f.title).trim()) {
    recFormError.value = 'Укажите название.'
    return
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    recFormError.value = 'Сумма: положительное число.'
    return
  }
  if (!f.start_month) {
    recFormError.value = 'Укажите месяц начала.'
    return
  }
  const day = Number.parseInt(String(f.day_of_month), 10)
  if (!Number.isFinite(day) || day < 1 || day > 28) {
    recFormError.value = 'День месяца: 1–28.'
    return
  }
  const body = {
    title: String(f.title).trim(),
    amount,
    category_id: f.category_id === '' ? null : Number(f.category_id),
    day_of_month: day,
    start_month: `${f.start_month}-01`,
    end_month: f.end_month ? `${f.end_month}-01` : null,
    active: Boolean(f.active),
    note: String(f.note).trim() || null,
  }
  recSaving.value = true
  recFormError.value = null
  try {
    if (f.id) {
      await fetchJson(`/api/admin/accounting/recurring-expenses/${f.id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
    } else {
      await fetchJson('/api/admin/accounting/recurring-expenses', {
        method: 'POST',
        body: JSON.stringify(body),
      })
    }
    recModalOpen.value = false
    await loadRecurring()
  } catch (e) {
    recFormError.value = e.message || String(e)
  } finally {
    recSaving.value = false
  }
}

async function deleteRecurring(row) {
  if (!isAdmin.value) return
  const ok = window.confirm(`Удалить повторяющийся расход «${row.title}»?`)
  if (!ok) return
  try {
    await fetchJson(`/api/admin/accounting/recurring-expenses/${row.id}`, { method: 'DELETE' })
    await loadRecurring()
  } catch (e) {
    error.value = e.message || String(e)
  }
}

onMounted(() => {
  void loadAll()
})

defineExpose({ reload: loadAll })
</script>

<template>
  <p v-if="error" class="msg-err">{{ error }}</p>

  <!-- Разовые расходы -->
  <section class="block">
    <div class="block-head">
      <h2 class="section-heading">Разовые расходы</h2>
      <div class="head-actions">
        <button type="button" class="btn-primary" @click="openExpenseCreate">Добавить расход</button>
        <button type="button" class="btn-secondary" @click="exportExpensesCsv">Экспорт CSV</button>
        <AppRefreshButton :busy="loading" @click="loadAll" />
      </div>
    </div>

    <AppPager
      :range-label="expRangeLabel"
      :can-prev="canPrev"
      :can-next="canNext"
      :loading="loading"
      @prev="expPrev"
      @next="expNext"
    >
      <template v-if="bulk.canBulkSelect" #actions>
        <AdminTableBulkBar
          :active="bulk.selectionMode"
          :selected-count="bulk.selectedCount"
          :deleting="bulk.deleting"
          entity-label="расходов"
          @toggle="bulk.toggleSelectionMode()"
          @delete="deleteSelectedExpenses"
        />
      </template>
    </AppPager>

    <AdminTableWrap
      aria-label="Разовые расходы"
      :bulk-select-active="bulk.selectionMode"
    >
      <table class="admin-table">
        <thead>
          <tr>
            <AdminTableSelectTh
              v-if="bulk.canBulkSelect"
              :active="bulk.selectionMode"
              :checked="bulk.allSelectedOnPage"
              :disabled="expenses.length === 0"
              @toggle="bulk.toggleSelectAllOnPage()"
            />
            <th>Дата</th>
            <th>Категория</th>
            <th>Название</th>
            <th>Оплата</th>
            <th>Счет</th>
            <th class="num">Сумма, ₽</th>
            <th class="th-actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="expenses.length === 0">
            <td :colspan="expTableColspan" class="muted">Расходов пока нет</td>
          </tr>
          <tr
            v-for="row in expenses"
            :key="row.id"
            :class="{
              'admin-bulk-row--selectable': bulk.selectionMode,
              'admin-bulk-row--picked': bulk.selectionMode && bulk.isRowSelected(row.id),
            }"
            @click="onExpenseRowClick(row, $event)"
          >
            <AdminTableSelectTd
              v-if="bulk.canBulkSelect"
              :active="bulk.selectionMode"
              :selected="bulk.isRowSelected(row.id)"
              :row-id="row.id"
              @toggle="bulk.toggleRow(row.id)"
            />
            <td class="date-cell">{{ fmtDate(row.incurred_on) }}</td>
            <td>
              <span class="cat-chip">
                <span class="cat-dot" :style="{ background: categoryColor(row.category_id) }" />
                {{ categoryLabel(row.category_id) }}
              </span>
            </td>
            <td>
              <span class="exp-title">{{ row.title }}</span>
              <span v-if="row.note" class="exp-note" :title="row.note">{{ row.note }}</span>
            </td>
            <td>
              <span class="pill" :class="row.payment_source === 'company' ? 'pill--on' : 'pill--off'">
                {{ paymentSourceLabel(row) }}
              </span>
            </td>
            <td class="date-cell">{{ row.payment_source === 'company' ? accountLabel(row.cash_account_id) : '—' }}</td>
            <td class="num">{{ money(row.amount) }}</td>
            <td class="td-actions">
              <button type="button" class="btn-icon" title="Редактировать" @click="openExpenseEdit(row)">✎</button>
              <button
                v-if="isAdmin"
                type="button"
                class="btn-icon btn-icon--danger"
                title="Удалить"
                @click="deleteExpenses([row.id])"
              >
                ✕
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </section>

  <!-- Повторяющиеся расходы -->
  <section class="block">
    <div class="block-head">
      <h2 class="section-heading">Повторяющиеся расходы (ежемесячно)</h2>
      <div class="head-actions">
        <button type="button" class="btn-primary" @click="openRecurringCreate">Добавить шаблон</button>
      </div>
    </div>

    <AdminTableWrap aria-label="Повторяющиеся расходы">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Название</th>
            <th>Категория</th>
            <th class="num">Сумма/мес, ₽</th>
            <th>День</th>
            <th>Период</th>
            <th>Статус</th>
            <th class="th-actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="recurring.length === 0">
            <td colspan="7" class="muted">Повторяющихся расходов пока нет</td>
          </tr>
          <tr v-for="row in recurring" :key="row.id" :class="{ 'row-inactive': !row.active }">
            <td>
              <span class="exp-title">{{ row.title }}</span>
              <span v-if="row.note" class="exp-note" :title="row.note">{{ row.note }}</span>
            </td>
            <td>
              <span class="cat-chip">
                <span class="cat-dot" :style="{ background: categoryColor(row.category_id) }" />
                {{ categoryLabel(row.category_id) }}
              </span>
            </td>
            <td class="num">{{ money(row.amount) }}</td>
            <td>{{ row.day_of_month }}</td>
            <td class="date-cell">{{ fmtMonth(row.start_month) }} – {{ row.end_month ? fmtMonth(row.end_month) : '∞' }}</td>
            <td>
              <span class="pill" :class="row.active ? 'pill--on' : 'pill--off'">
                {{ row.active ? 'активен' : 'выключен' }}
              </span>
            </td>
            <td class="td-actions">
              <button type="button" class="btn-icon" title="Редактировать" @click="openRecurringEdit(row)">✎</button>
              <button
                v-if="isAdmin"
                type="button"
                class="btn-icon btn-icon--danger"
                title="Удалить"
                @click="deleteRecurring(row)"
              >
                ✕
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </section>

  <!-- Модалка разового расхода -->
  <AppModal
    v-if="expModalOpen"
    :title="expForm.id ? 'Изменить расход' : 'Новый расход'"
    :busy="expSaving"
    @close="closeExpenseModal"
  >
    <form class="modal-form" @submit.prevent="submitExpense">
      <label class="field">
        <span>Дата</span>
        <input v-model="expForm.incurred_on" type="date" class="input-like" required />
      </label>
      <label class="field">
        <span>Категория</span>
        <select v-model="expForm.category_id" class="input-like">
          <option value="">Без категории</option>
          <option v-for="c in activeCategories" :key="c.id" :value="c.id">{{ c.title }}</option>
        </select>
      </label>
      <label class="field">
        <span>Название</span>
        <input v-model="expForm.title" type="text" class="input-like" placeholder="Напр. Аренда сервера Hetzner" />
      </label>
      <label class="field">
        <span>Сумма, ₽</span>
        <input v-model="expForm.amount" type="text" inputmode="decimal" class="input-like" placeholder="Например 1500" />
      </label>
      <label class="field">
        <span>Кто оплатил</span>
        <select v-model="expForm.payment_source" class="input-like">
          <option value="company">Оплата с расчетника / счета компании</option>
          <option value="person">Оплатил человек, создать долг организации</option>
          <option value="unpaid">Начислено, пока не оплачено</option>
        </select>
      </label>
      <div v-if="expForm.payment_source === 'company'" class="field-row">
        <label class="field">
          <span>Счет списания</span>
          <select v-model="expForm.cash_account_id" class="input-like">
            <option value="">Дефолтный расчетный счет</option>
            <option v-for="a in activeCashAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </label>
        <label class="field">
          <span>Дата оплаты</span>
          <input v-model="expForm.paid_on" type="date" class="input-like" />
        </label>
      </div>
      <label v-if="expForm.payment_source === 'person'" class="field">
        <span>Кто оплатил</span>
        <input v-model="expForm.paid_by_name" type="text" class="input-like" placeholder="Напр. Александр" />
      </label>
      <label class="field">
        <span>Комментарий (необязательно)</span>
        <input v-model="expForm.note" type="text" class="input-like" />
      </label>
      <p v-if="expFormError" class="form-err">{{ expFormError }}</p>
      <div class="modal-actions">
        <button type="button" class="btn-secondary" :disabled="expSaving" @click="closeExpenseModal">Отмена</button>
        <button type="submit" class="btn-primary" :disabled="expSaving">{{ expSaving ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </form>
  </AppModal>

  <!-- Модалка повторяющегося расхода -->
  <AppModal
    v-if="recModalOpen"
    :title="recForm.id ? 'Изменить шаблон' : 'Новый повторяющийся расход'"
    :busy="recSaving"
    @close="closeRecurringModal"
  >
    <form class="modal-form" @submit.prevent="submitRecurring">
      <label class="field">
        <span>Название</span>
        <input v-model="recForm.title" type="text" class="input-like" placeholder="Напр. Аренда серверов" />
      </label>
      <label class="field">
        <span>Категория</span>
        <select v-model="recForm.category_id" class="input-like">
          <option value="">Без категории</option>
          <option v-for="c in activeCategories" :key="c.id" :value="c.id">{{ c.title }}</option>
        </select>
      </label>
      <div class="field-row">
        <label class="field">
          <span>Сумма в месяц, ₽</span>
          <input v-model="recForm.amount" type="text" inputmode="decimal" class="input-like" placeholder="Например 5000" />
        </label>
        <label class="field field-narrow">
          <span>День</span>
          <input v-model="recForm.day_of_month" type="text" inputmode="numeric" class="input-like" placeholder="1–28" />
        </label>
      </div>
      <div class="field-row">
        <label class="field">
          <span>Начало (месяц)</span>
          <input v-model="recForm.start_month" type="month" class="input-like" required />
        </label>
        <label class="field">
          <span>Окончание (необязательно)</span>
          <input v-model="recForm.end_month" type="month" class="input-like" />
        </label>
      </div>
      <label class="field">
        <span>Комментарий (необязательно)</span>
        <input v-model="recForm.note" type="text" class="input-like" />
      </label>
      <label class="field-check">
        <input v-model="recForm.active" type="checkbox" />
        <span>Активен (учитывать в сводке)</span>
      </label>
      <p v-if="recFormError" class="form-err">{{ recFormError }}</p>
      <div class="modal-actions">
        <button type="button" class="btn-secondary" :disabled="recSaving" @click="closeRecurringModal">Отмена</button>
        <button type="submit" class="btn-primary" :disabled="recSaving">{{ recSaving ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </form>
  </AppModal>
</template>

<style scoped>
/* Общие .field/.input-like/.btn-danger/.btn-icon/.pill/.modal-* — в styles/admin-ui.css */
.block {
  margin-bottom: 1.75rem;
}
.block-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.section-heading {
  margin: 0;
  font-size: 1.05rem;
  color: var(--text-h);
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.date-cell {
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.85rem;
}
.cat-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
}
.cat-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
}
.exp-title {
  display: block;
  color: var(--text-h);
}
.exp-note {
  display: block;
  font-size: 0.76rem;
  color: var(--muted);
  max-width: 22rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Узкие поля расходов уже глобального .field-narrow (9rem) */
.field-narrow {
  max-width: 6.5rem;
}
</style>
