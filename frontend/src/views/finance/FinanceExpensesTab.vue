<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import AdminTableWrap from '../../components/AdminTableWrap.vue'
import { fetchJson } from '../../api/client.js'
import { getSessionRole } from '../../auth/session.js'
import { downloadCsv } from '../../utils/csv.js'

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

// --- разовые ---
const expenses = ref([])
const expTotal = ref(0)
const expLimit = 100
const expOffset = ref(0)
const selectedIds = ref([])
const deleting = ref(false)

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

function todayDate() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function thisMonth() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

function blankExpenseForm() {
  return { id: null, incurred_on: todayDate(), amount: '', category_id: '', title: '', note: '' }
}
function blankRecurringForm() {
  return {
    id: null,
    title: '',
    amount: '',
    category_id: '',
    day_of_month: '1',
    start_month: thisMonth(),
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

const expRangeLabel = computed(() => {
  if (expTotal.value === 0) return '0 записей'
  const from = expOffset.value + 1
  const to = expOffset.value + expenses.value.length
  return `${from}–${to} из ${expTotal.value}`
})
const canPrev = computed(() => expOffset.value > 0)
const canNext = computed(() => expOffset.value + expenses.value.length < expTotal.value)

const allSelectedOnPage = computed(() => {
  const ids = expenses.value.map((r) => r.id)
  return ids.length > 0 && ids.every((id) => selectedIds.value.includes(id))
})
function toggleSelectAll() {
  const ids = expenses.value.map((r) => r.id)
  if (allSelectedOnPage.value) {
    const rm = new Set(ids)
    selectedIds.value = selectedIds.value.filter((id) => !rm.has(id))
  } else {
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...ids]))
  }
}

async function loadCategories() {
  const data = await fetchJson('/api/admin/accounting/categories')
  categories.value = Array.isArray(data?.items) ? data.items : []
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
    await Promise.all([loadCategories(), loadExpenses(), loadRecurring()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

function expPrev() {
  expOffset.value = Math.max(0, expOffset.value - expLimit)
  void loadExpenses()
}
function expNext() {
  expOffset.value += expLimit
  void loadExpenses()
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
    note: String(f.note).trim() || null,
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
      expOffset.value = 0
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
  if (!isAdmin.value || ids.length === 0 || deleting.value) return
  const ok = window.confirm(`Удалить расходы (${ids.length})? Действие необратимо.`)
  if (!ok) return
  deleting.value = true
  error.value = null
  try {
    await fetchJson('/api/admin/accounting/expenses', {
      method: 'DELETE',
      body: JSON.stringify({ ids }),
    })
    selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id))
    await loadExpenses()
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    deleting.value = false
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

watch(
  () => expenses.value.map((r) => r.id),
  (ids) => {
    const keep = new Set(ids)
    selectedIds.value = selectedIds.value.filter((id) => keep.has(id))
  },
)

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
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadAll">
          {{ loading ? 'Обновление…' : 'Обновить' }}
        </button>
      </div>
    </div>

    <div class="toolbar">
      <span class="muted">{{ expRangeLabel }}</span>
      <div class="toolbar-btns">
        <button
          v-if="isAdmin"
          type="button"
          class="btn-danger"
          :disabled="selectedIds.length === 0 || deleting"
          @click="deleteExpenses(selectedIds)"
        >
          {{ deleting ? 'Удаление…' : `Удалить выбранные (${selectedIds.length})` }}
        </button>
        <button type="button" class="btn-secondary" :disabled="loading || !canPrev" @click="expPrev">Назад</button>
        <button type="button" class="btn-secondary" :disabled="loading || !canNext" @click="expNext">Вперёд</button>
      </div>
    </div>

    <AdminTableWrap aria-label="Разовые расходы">
      <table class="admin-table">
        <thead>
          <tr>
            <th v-if="isAdmin" class="th-select">
              <input type="checkbox" :checked="allSelectedOnPage" :disabled="expenses.length === 0" @change="toggleSelectAll" />
            </th>
            <th>Дата</th>
            <th>Категория</th>
            <th>Название</th>
            <th class="num">Сумма, ₽</th>
            <th class="th-actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="expenses.length === 0">
            <td :colspan="isAdmin ? 6 : 5" class="muted">Расходов пока нет</td>
          </tr>
          <tr v-for="row in expenses" :key="row.id">
            <td v-if="isAdmin" class="td-select">
              <input v-model="selectedIds" type="checkbox" :value="row.id" />
            </td>
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
  <Teleport to="body">
    <div v-if="expModalOpen" class="modal-backdrop" role="presentation" @click.self="closeExpenseModal">
      <div class="modal" role="dialog" aria-modal="true" @click.stop>
        <h2 class="modal-title">{{ expForm.id ? 'Изменить расход' : 'Новый расход' }}</h2>
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
            <span>Комментарий (необязательно)</span>
            <input v-model="expForm.note" type="text" class="input-like" />
          </label>
          <p v-if="expFormError" class="form-err">{{ expFormError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" :disabled="expSaving" @click="closeExpenseModal">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="expSaving">{{ expSaving ? 'Сохранение…' : 'Сохранить' }}</button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>

  <!-- Модалка повторяющегося расхода -->
  <Teleport to="body">
    <div v-if="recModalOpen" class="modal-backdrop" role="presentation" @click.self="closeRecurringModal">
      <div class="modal" role="dialog" aria-modal="true" @click.stop>
        <h2 class="modal-title">{{ recForm.id ? 'Изменить шаблон' : 'Новый повторяющийся расход' }}</h2>
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
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
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
.hint {
  margin: 0 0 0.75rem;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 52rem;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.6rem;
}
.toolbar-btns {
  display: flex;
  gap: 0.35rem;
}
.muted {
  color: var(--muted);
}
.msg-err {
  color: var(--danger);
  margin-bottom: 0.75rem;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.date-cell {
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.85rem;
}
.th-select,
.td-select {
  width: 1%;
  text-align: center;
  white-space: nowrap;
}
.th-actions,
.td-actions {
  text-align: right;
  white-space: nowrap;
  width: 1%;
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
.row-inactive {
  opacity: 0.55;
}
.pill {
  display: inline-block;
  padding: 0.12rem 0.45rem;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.pill--on {
  background: color-mix(in srgb, #34d399 18%, transparent);
  color: #2bb673;
}
.pill--off {
  background: var(--surface);
  color: var(--muted);
  border: 1px solid var(--card-border);
}
.btn-icon {
  font: inherit;
  cursor: pointer;
  background: var(--surface);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 0.25rem 0.5rem;
  color: var(--text-h);
  margin-left: 0.25rem;
  line-height: 1;
}
.btn-icon:hover {
  border-color: var(--accent-border);
  color: var(--accent);
}
.btn-icon--danger:hover {
  border-color: var(--danger);
  color: var(--danger);
}
.btn-danger {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-lg);
  border: none;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: #fff;
}
.btn-danger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* модалка */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 12, 9, 0.55);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: clamp(1rem, 4vh, 2.5rem) 1rem;
  z-index: 50;
}
.modal {
  width: 100%;
  max-width: 520px;
  max-height: min(90dvh, 760px);
  overflow-y: auto;
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
}
.modal-title {
  margin: 0 0 0.85rem;
  font-size: 1.1rem;
  color: var(--text-h);
}
.modal-form .field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
}
.modal-form .field > span:first-child {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.field-row {
  display: flex;
  gap: 0.75rem;
}
.field-row .field {
  flex: 1;
}
.field-narrow {
  max-width: 6.5rem;
}
.field-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.85rem;
  font-size: 0.88rem;
  color: var(--text-h);
  cursor: pointer;
}
.input-like {
  font: inherit;
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
}
.input-like:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--text-h) 38%, var(--card-border));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--text-h) 14%, transparent);
}
.form-err {
  margin: 0 0 0.65rem;
  font-size: 0.85rem;
  color: var(--danger);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  margin-top: 0.5rem;
}
</style>
