<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'
import { getStaffProfile } from '../auth/staffSession.js'

const router = useRouter()

const items = ref([])
const loading = ref(false)
const error = ref(null)
const creating = ref(false)
const draft = ref({ slug: '', name: '', primary_domain: '', extra_domains: '' })

const canCreate = () => getStaffProfile()?.role === 'super_admin'

async function load() {
  loading.value = true
  error.value = null
  try {
    items.value = await apiFetch('/api/admin/projects', { withProject: false })
  } catch (e) { error.value = e.message } finally { loading.value = false }
}

async function submitCreate() {
  try {
    const extra = draft.value.extra_domains
      .split(',').map((s) => s.trim()).filter(Boolean)
    const created = await apiFetch('/api/admin/projects', {
      method: 'POST',
      withProject: false,
      body: {
        slug: draft.value.slug.trim().toLowerCase(),
        name: draft.value.name.trim(),
        primary_domain: draft.value.primary_domain.trim().toLowerCase(),
        extra_domains: extra,
      },
    })
    creating.value = false
    draft.value = { slug: '', name: '', primary_domain: '', extra_domains: '' }
    await load()
    // Сразу перекидываем на детальный экран, чтобы заполнить остальные настройки
    if (created?.id) router.push(`/projects/${created.id}`)
  } catch (e) { alert(e.message) }
}

async function toggleActive(p) {
  try {
    await apiFetch(`/api/admin/projects/${p.id}`, {
      method: 'PATCH',
      withProject: false,
      body: { is_active: !p.is_active },
    })
    await load()
  } catch (e) { alert(e.message) }
}

async function remove(p) {
  if (!confirm(`Удалить проект «${p.name}» (id=${p.id})? Операция необратима.`)) return
  try {
    await apiFetch(`/api/admin/projects/${p.id}`, { method: 'DELETE', withProject: false })
    await load()
  } catch (e) { alert(e.message) }
}

onMounted(load)
</script>

<template>
  <section class="stack">
    <div class="card">
      <div class="row" style="justify-content: space-between;">
        <h2 style="margin: 0;">Проекты</h2>
        <button v-if="canCreate()" class="primary" @click="creating = !creating">
          {{ creating ? 'Отменить' : '+ Новый проект' }}
        </button>
      </div>

      <form v-if="creating" class="stack" style="margin-top: 16px;" @submit.prevent="submitCreate">
        <p style="color: var(--text-muted); margin: 0; font-size: 13px;">
          Заполните минимум (slug, название, домен). Остальные настройки
          (Telegram-бот, платёжные ключи, брендинг, SMTP, реферальная политика)
          — на детальном экране проекта, куда откроется после создания.
        </p>
        <input v-model="draft.slug" placeholder="slug (уникальный, латиницей — используется в webhook URL)" required />
        <input v-model="draft.name" placeholder="Название" required />
        <input v-model="draft.primary_domain" placeholder="primary_domain (например, example.com — без https://)" required />
        <input v-model="draft.extra_domains" placeholder="extra_domains, через запятую (опционально)" />
        <button type="submit" class="primary">Создать и перейти к настройкам →</button>
      </form>
    </div>

    <div class="card">
      <p v-if="loading">Загрузка…</p>
      <p v-if="error" style="color: var(--danger);">{{ error }}</p>
      <table v-if="items.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>Slug</th>
            <th>Название</th>
            <th>Primary domain</th>
            <th>Extra</th>
            <th>Активен</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in items" :key="p.id">
            <td>{{ p.id }}</td>
            <td><router-link :to="`/projects/${p.id}`">{{ p.slug }}</router-link></td>
            <td>{{ p.name }}</td>
            <td>{{ p.primary_domain }}</td>
            <td>{{ (p.extra_domains || []).join(', ') || '—' }}</td>
            <td>
              <button v-if="canCreate()" @click="toggleActive(p)">
                {{ p.is_active ? 'ON' : 'off' }}
              </button>
              <span v-else>{{ p.is_active ? 'ON' : 'off' }}</span>
            </td>
            <td>
              <router-link :to="`/projects/${p.id}/tariffs`">тарифы</router-link>
              <span v-if="canCreate() && p.id !== 1"> · </span>
              <button v-if="canCreate() && p.id !== 1" @click="remove(p)" style="color: var(--danger);">удалить</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
