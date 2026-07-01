<script setup>
import { onMounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client.js'
import { getStaffProfile } from '../auth/staffSession.js'

const props = defineProps({ id: [Number, String] })

const items = ref([])
const loading = ref(false)
const error = ref(null)
const draft = ref({
  provider: 'yookassa', months: 1, amount: 0, name: '',
  external_link: '', external_tg_link: '', external_product_id: '', kind: '',
  is_active: true, sort_order: 0,
})

const canEdit = () => getStaffProfile()?.role === 'super_admin'

async function load() {
  loading.value = true; error.value = null
  try {
    items.value = await apiFetch(`/api/admin/projects/${props.id}/tariffs`, { withProject: false })
  } catch (e) { error.value = e.message } finally { loading.value = false }
}

async function submitCreate() {
  try {
    await apiFetch(`/api/admin/projects/${props.id}/tariffs`, {
      method: 'POST', withProject: false, body: { ...draft.value },
    })
    draft.value = {
      provider: 'yookassa', months: 1, amount: 0, name: '',
      external_link: '', external_tg_link: '', external_product_id: '', kind: '',
      is_active: true, sort_order: 0,
    }
    await load()
  } catch (e) { alert(e.message) }
}

async function remove(t) {
  if (!confirm(`Удалить тариф id=${t.id} (${t.provider}/${t.months}m)?`)) return
  try {
    await apiFetch(`/api/admin/tariffs/${t.id}`, { method: 'DELETE', withProject: false })
    await load()
  } catch (e) { alert(e.message) }
}

async function toggle(t) {
  try {
    await apiFetch(`/api/admin/tariffs/${t.id}`, {
      method: 'PATCH', withProject: false, body: { is_active: !t.is_active },
    })
    await load()
  } catch (e) { alert(e.message) }
}

watch(() => props.id, load)
onMounted(load)
</script>

<template>
  <section class="stack">
    <div class="card">
      <h2 style="margin-top: 0;">Тарифы проекта #{{ id }}</h2>
      <p v-if="loading">Загрузка…</p>
      <p v-if="error" style="color: var(--danger);">{{ error }}</p>
      <table v-if="items.length">
        <thead>
          <tr>
            <th>ID</th><th>Провайдер</th><th>Мес</th><th>Сумма</th>
            <th>Название</th><th>Web link</th><th>TG link</th><th>Активен</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in items" :key="t.id">
            <td>{{ t.id }}</td>
            <td>{{ t.provider }}</td>
            <td>{{ t.months }}</td>
            <td>{{ t.amount }}</td>
            <td>{{ t.name || '—' }}</td>
            <td>{{ t.external_link || '—' }}</td>
            <td>{{ t.external_tg_link || '—' }}</td>
            <td>
              <button v-if="canEdit()" @click="toggle(t)">
                {{ t.is_active ? 'ON' : 'off' }}
              </button>
              <span v-else>{{ t.is_active ? 'ON' : 'off' }}</span>
            </td>
            <td>
              <button v-if="canEdit()" @click="remove(t)" style="color: var(--danger);">
                удалить
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loading">Тарифов ещё нет.</p>
    </div>

    <div class="card" v-if="canEdit()">
      <h3 style="margin-top: 0;">Новый тариф</h3>
      <form class="stack" @submit.prevent="submitCreate">
        <label>
          <span>provider</span>
          <select v-model="draft.provider">
            <option value="yookassa">yookassa</option>
            <option value="tribute">tribute</option>
          </select>
        </label>
        <label><span>months</span><input v-model.number="draft.months" type="number" min="1" required /></label>
        <label><span>amount (RUB)</span><input v-model.number="draft.amount" type="number" step="0.01" required /></label>
        <label><span>name (опционально)</span><input v-model="draft.name" /></label>
        <label><span>external_link (tribute)</span><input v-model="draft.external_link" /></label>
        <label><span>external_tg_link (tribute)</span><input v-model="draft.external_tg_link" /></label>
        <label><span>external_product_id</span><input v-model="draft.external_product_id" /></label>
        <label><span>kind</span><input v-model="draft.kind" /></label>
        <label><span>sort_order</span><input v-model.number="draft.sort_order" type="number" /></label>
        <button class="primary" type="submit">Создать</button>
      </form>
    </div>
  </section>
</template>

<style scoped>
label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-muted); }
label span { padding-left: 4px; font-family: monospace; }
</style>
