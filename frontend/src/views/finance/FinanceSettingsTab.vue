<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AdminTableWrap from '../../components/AdminTableWrap.vue'
import AppModal from '../../components/AppModal.vue'
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
let taxSavedTimer = null

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
    clearTimeout(taxSavedTimer)
    taxSavedTimer = setTimeout(() => {
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

onBeforeUnmount(() => {
  clearTimeout(taxSavedTimer)
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

  <AppModal
    v-if="catModalOpen"
    :title="catForm.id ? 'Изменить категорию' : 'Новая категория'"
    :max-width="480"
    :busy="catSaving"
    @close="closeCategoryModal"
  >
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
  </AppModal>
</template>

<style scoped>
/* Общие .field/.input-like/.pill/.btn-icon/.modal-* — в styles/admin-ui.css */
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
</style>
