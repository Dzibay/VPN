<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminTableWrap from '../../components/AdminTableWrap.vue'
import { fetchJson } from '../../api/client.js'
import { getSessionRole } from '../../auth/session.js'

const isAdmin = computed(() => getSessionRole() === 'admin')

const loading = ref(false)
const error = ref(null)

const TAX_MODE_OPTIONS = [
  { value: 'npd', label: 'НПД (самозанятый)' },
  { value: 'usn_income', label: 'УСН «Доходы»' },
  { value: 'usn_profit', label: 'УСН «Доходы минус расходы»' },
  { value: 'none', label: 'Без налога' },
  { value: 'custom', label: 'Своя ставка' },
]
const TAX_BASE_OPTIONS = [
  { value: 'gross', label: 'Валовая выручка' },
  { value: 'net', label: 'Чистая выручка (после комиссии)' },
  { value: 'profit', label: 'Прибыль (выручка − расходы)' },
]
const MODE_PRESETS = {
  npd: { rate: 4, base: 'gross' },
  usn_income: { rate: 6, base: 'gross' },
  usn_profit: { rate: 15, base: 'profit' },
  none: { rate: 0, base: 'gross' },
}

// --- налоговая форма ---
const taxMode = ref('npd')
const taxRatePercent = ref('4')
const taxBase = ref('gross')
const currency = ref('RUB')
const savingTax = ref(false)
const taxError = ref(null)
const taxSaved = ref(false)

function onModeChange() {
  const preset = MODE_PRESETS[taxMode.value]
  if (preset) {
    taxRatePercent.value = String(preset.rate)
    taxBase.value = preset.base
  }
}

const taxBaseDisabled = computed(() => taxMode.value === 'none')

async function loadSettings() {
  const s = await fetchJson('/api/admin/accounting/settings')
  taxMode.value = s.tax_mode || 'npd'
  taxRatePercent.value = String(Math.round(Number(s.tax_rate || 0) * 10000) / 100)
  taxBase.value = s.tax_base || 'gross'
  currency.value = s.currency || 'RUB'
}

async function saveTax() {
  if (!isAdmin.value) return
  const pct = Number(String(taxRatePercent.value).replace(',', '.'))
  if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
    taxError.value = 'Ставка: число от 0 до 100.'
    return
  }
  savingTax.value = true
  taxError.value = null
  taxSaved.value = false
  try {
    const body = {
      tax_mode: taxMode.value,
      tax_rate: pct / 100,
      tax_base: taxBase.value,
      currency: String(currency.value).trim() || 'RUB',
    }
    await fetchJson('/api/admin/accounting/settings', {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    taxSaved.value = true
    setTimeout(() => {
      taxSaved.value = false
    }, 2500)
  } catch (e) {
    taxError.value = e.message || String(e)
  } finally {
    savingTax.value = false
  }
}

// --- категории ---
const categories = ref([])

const catModalOpen = ref(false)
const catSaving = ref(false)
const catError = ref(null)
const catForm = ref(blankCategory())

function blankCategory() {
  return { id: null, slug: '', title: '', color: '#38bdf8', sort_order: '0', archived: false }
}

async function loadCategories() {
  const data = await fetchJson('/api/admin/accounting/categories')
  categories.value = Array.isArray(data?.items) ? data.items : []
}

function openCategoryCreate() {
  catForm.value = blankCategory()
  catError.value = null
  catModalOpen.value = true
}
function openCategoryEdit(row) {
  catForm.value = {
    id: row.id,
    slug: row.slug,
    title: row.title,
    color: row.color || '#38bdf8',
    sort_order: String(row.sort_order ?? 0),
    archived: Boolean(row.archived),
  }
  catError.value = null
  catModalOpen.value = true
}
function closeCategoryModal() {
  if (catSaving.value) return
  catModalOpen.value = false
}

async function submitCategory() {
  const f = catForm.value
  if (!String(f.title).trim()) {
    catError.value = 'Укажите название категории.'
    return
  }
  const sortOrder = Number.parseInt(String(f.sort_order), 10) || 0
  catSaving.value = true
  catError.value = null
  try {
    if (f.id) {
      await fetchJson(`/api/admin/accounting/categories/${f.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: String(f.title).trim(),
          color: f.color,
          sort_order: sortOrder,
          archived: Boolean(f.archived),
        }),
      })
    } else {
      const slug = String(f.slug).trim().toLowerCase()
      if (!/^[a-z0-9_-]+$/.test(slug)) {
        catError.value = 'Slug: только латиница в нижнем регистре, цифры, дефис и подчёркивание.'
        catSaving.value = false
        return
      }
      await fetchJson('/api/admin/accounting/categories', {
        method: 'POST',
        body: JSON.stringify({
          slug,
          title: String(f.title).trim(),
          color: f.color,
          sort_order: sortOrder,
        }),
      })
    }
    catModalOpen.value = false
    await loadCategories()
  } catch (e) {
    catError.value = e.message || String(e)
  } finally {
    catSaving.value = false
  }
}

async function deleteCategory(row) {
  if (!isAdmin.value) return
  const ok = window.confirm(
    `Удалить категорию «${row.title}»? Существующие расходы останутся без категории.`,
  )
  if (!ok) return
  try {
    await fetchJson(`/api/admin/accounting/categories/${row.id}`, { method: 'DELETE' })
    await loadCategories()
  } catch (e) {
    error.value = e.message || String(e)
  }
}

async function loadAll() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([loadSettings(), loadCategories()])
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <p v-if="error" class="msg-err">{{ error }}</p>

  <section class="block">
    <h2 class="section-heading">Налог</h2>

    <div class="form-card">
      <div class="form-grid">
        <label class="field">
          <span>Режим</span>
          <select v-model="taxMode" class="input-like" :disabled="!isAdmin" @change="onModeChange">
            <option v-for="o in TAX_MODE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <label class="field field-narrow">
          <span>Ставка, %</span>
          <input
            v-model="taxRatePercent"
            type="text"
            inputmode="decimal"
            class="input-like"
            :disabled="!isAdmin || taxMode === 'none'"
          />
        </label>
        <label class="field">
          <span>База расчёта</span>
          <select v-model="taxBase" class="input-like" :disabled="!isAdmin || taxBaseDisabled">
            <option v-for="o in TAX_BASE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <label class="field field-narrow">
          <span>Валюта</span>
          <input v-model="currency" type="text" class="input-like" :disabled="!isAdmin" />
        </label>
      </div>

      <p v-if="taxError" class="form-err">{{ taxError }}</p>
      <div class="form-foot">
        <button
          v-if="isAdmin"
          type="button"
          class="btn-primary"
          :disabled="savingTax"
          @click="saveTax"
        >
          {{ savingTax ? 'Сохранение…' : 'Сохранить налог' }}
        </button>
        <span v-else class="muted">Изменение доступно только администратору.</span>
        <span v-if="taxSaved" class="saved-badge">Сохранено</span>
      </div>
    </div>
  </section>

  <section class="block">
    <div class="block-head">
      <h2 class="section-heading">Категории расходов</h2>
      <button v-if="isAdmin" type="button" class="btn-primary" @click="openCategoryCreate">Добавить категорию</button>
    </div>

    <AdminTableWrap aria-label="Категории расходов">
      <table class="admin-table">
        <thead>
          <tr>
            <th>Цвет</th>
            <th>Название</th>
            <th>Slug</th>
            <th class="num">Порядок</th>
            <th>Статус</th>
            <th v-if="isAdmin" class="th-actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="categories.length === 0">
            <td :colspan="isAdmin ? 6 : 5" class="muted">Категорий нет</td>
          </tr>
          <tr v-for="row in categories" :key="row.id" :class="{ 'row-inactive': row.archived }">
            <td><span class="cat-dot" :style="{ background: row.color }" /></td>
            <td>{{ row.title }}</td>
            <td><code class="slug">{{ row.slug }}</code></td>
            <td class="num">{{ row.sort_order }}</td>
            <td>
              <span class="pill" :class="row.archived ? 'pill--off' : 'pill--on'">
                {{ row.archived ? 'архив' : 'активна' }}
              </span>
            </td>
            <td v-if="isAdmin" class="td-actions">
              <button type="button" class="btn-icon" title="Редактировать" @click="openCategoryEdit(row)">✎</button>
              <button type="button" class="btn-icon btn-icon--danger" title="Удалить" @click="deleteCategory(row)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </section>

  <Teleport to="body">
    <div v-if="catModalOpen" class="modal-backdrop" role="presentation" @click.self="closeCategoryModal">
      <div class="modal" role="dialog" aria-modal="true" @click.stop>
        <h2 class="modal-title">{{ catForm.id ? 'Изменить категорию' : 'Новая категория' }}</h2>
        <form class="modal-form" @submit.prevent="submitCategory">
          <label v-if="!catForm.id" class="field">
            <span>Slug (латиница)</span>
            <input v-model="catForm.slug" type="text" class="input-like" placeholder="напр. ads" />
          </label>
          <label class="field">
            <span>Название</span>
            <input v-model="catForm.title" type="text" class="input-like" placeholder="напр. Реклама" />
          </label>
          <div class="field-row">
            <label class="field field-narrow">
              <span>Цвет</span>
              <input v-model="catForm.color" type="color" class="input-color" />
            </label>
            <label class="field field-narrow">
              <span>Порядок</span>
              <input v-model="catForm.sort_order" type="text" inputmode="numeric" class="input-like" />
            </label>
          </div>
          <label v-if="catForm.id" class="field-check">
            <input v-model="catForm.archived" type="checkbox" />
            <span>В архив (скрыть из выбора)</span>
          </label>
          <p v-if="catError" class="form-err">{{ catError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" :disabled="catSaving" @click="closeCategoryModal">Отмена</button>
            <button type="submit" class="btn-primary" :disabled="catSaving">{{ catSaving ? 'Сохранение…' : 'Сохранить' }}</button>
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
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
  color: var(--text-h);
}
.hint {
  margin: 0 0 0.85rem;
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.45;
  max-width: 52rem;
}
.muted {
  color: var(--muted);
}
.msg-err {
  color: var(--danger);
  margin-bottom: 0.75rem;
}
.form-card {
  padding: 1rem 1.15rem;
  border-radius: var(--radius-lg);
  border: 1px solid var(--card-border);
  background: var(--surface-glass, var(--surface));
  max-width: 44rem;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.85rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.field > span:first-child {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}
.field-narrow {
  max-width: 9rem;
}
.form-foot {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
}
.saved-badge {
  font-size: 0.85rem;
  font-weight: 600;
  color: #2bb673;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.th-actions,
.td-actions {
  text-align: right;
  white-space: nowrap;
  width: 1%;
}
.cat-dot {
  display: inline-block;
  width: 16px;
  height: 16px;
  border-radius: 4px;
}
.slug {
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  color: var(--muted);
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
  max-width: 480px;
  max-height: min(90dvh, 720px);
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
  margin-bottom: 0.85rem;
}
.field-row {
  display: flex;
  gap: 0.75rem;
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
.input-like:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.input-color {
  width: 100%;
  height: 2.5rem;
  padding: 0.15rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  cursor: pointer;
}
.form-err {
  margin: 0.5rem 0 0;
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
