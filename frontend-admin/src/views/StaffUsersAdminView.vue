<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '../api/client.js'

const items = ref([])
const projects = ref([])
const loading = ref(false)
const error = ref(null)
const editingId = ref(null)
const editDraft = ref(null)
const draft = ref({
  email: '',
  password: '',
  full_name: '',
  role: 'manager',
  projects: [],
  project_role: 'manager',
})

const projectById = computed(() => {
  const map = new Map()
  for (const p of projects.value) map.set(p.id, p)
  return map
})

function projectNames(ids) {
  if (!ids?.length) return '—'
  return ids
    .map((id) => {
      const p = projectById.value.get(id)
      return p ? `${p.name} (${p.slug})` : `#${id}`
    })
    .join(', ')
}

function startEdit(u) {
  editingId.value = u.id
  editDraft.value = {
    full_name: u.full_name || '',
    role: u.role,
    password: '',
    projects: [...(u.projects || [])],
    project_role: u.project_role || 'manager',
    is_active: u.is_active,
  }
}

function cancelEdit() {
  editingId.value = null
  editDraft.value = null
}

async function load() {
  loading.value = true
  error.value = null
  try {
    items.value = await apiFetch('/api/admin/staff-users', { withProject: false })
    projects.value = await apiFetch('/api/admin/projects', { withProject: false })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  try {
    await apiFetch('/api/admin/staff-users', {
      method: 'POST',
      withProject: false,
      body: {
        email: draft.value.email.trim().toLowerCase(),
        password: draft.value.password,
        full_name: draft.value.full_name || null,
        role: draft.value.role,
        projects: draft.value.role === 'super_admin' ? [] : draft.value.projects,
        project_role: draft.value.project_role,
      },
    })
    draft.value = {
      email: '',
      password: '',
      full_name: '',
      role: 'manager',
      projects: [],
      project_role: 'manager',
    }
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function saveEdit() {
  if (!editDraft.value || editingId.value == null) return
  const body = {
    full_name: editDraft.value.full_name || null,
    role: editDraft.value.role,
    is_active: editDraft.value.is_active,
  }
  if (editDraft.value.password) body.password = editDraft.value.password
  if (editDraft.value.role !== 'super_admin') {
    body.projects = editDraft.value.projects
    body.project_role = editDraft.value.project_role
  }
  try {
    await apiFetch(`/api/admin/staff-users/${editingId.value}`, {
      method: 'PATCH',
      withProject: false,
      body,
    })
    cancelEdit()
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function toggle(u) {
  try {
    await apiFetch(`/api/admin/staff-users/${u.id}`, {
      method: 'PATCH',
      withProject: false,
      body: { is_active: !u.is_active },
    })
    await load()
  } catch (e) {
    alert(e.message)
  }
}

async function remove(u) {
  if (!confirm(`Удалить staff «${u.email}» (id=${u.id})?`)) return
  try {
    await apiFetch(`/api/admin/staff-users/${u.id}`, { method: 'DELETE', withProject: false })
    if (editingId.value === u.id) cancelEdit()
    await load()
  } catch (e) {
    alert(e.message)
  }
}

onMounted(load)
</script>

<template>
  <section class="stack">
    <div class="card">
      <h2 style="margin-top: 0;">Персонал</h2>
      <p v-if="loading">Загрузка…</p>
      <p v-if="error" style="color: var(--danger);">{{ error }}</p>
      <table v-if="items.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>ФИО</th>
            <th>Роль</th>
            <th>Проекты</th>
            <th>Активен</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in items" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.email }}</td>
            <td>{{ u.full_name || '—' }}</td>
            <td>{{ u.role }}</td>
            <td>{{ u.role === 'super_admin' ? 'все' : projectNames(u.projects) }}</td>
            <td>
              <button @click="toggle(u)">{{ u.is_active ? 'ON' : 'off' }}</button>
            </td>
            <td>
              <button @click="startEdit(u)">редактировать</button>
              <button @click="remove(u)" style="color: var(--danger); margin-left: 8px;">удалить</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="editDraft" class="card">
      <h3 style="margin-top: 0;">Редактирование: {{ items.find((u) => u.id === editingId)?.email }}</h3>
      <form class="stack" @submit.prevent="saveEdit">
        <label>
          <span>ФИО</span>
          <input v-model="editDraft.full_name" type="text" autocomplete="off" />
        </label>
        <label>
          <span>Новый пароль</span>
          <input
            v-model="editDraft.password"
            type="text"
            autocomplete="off"
            placeholder="оставьте пустым, чтобы не менять"
          />
        </label>
        <label>
          <span>Глобальная роль</span>
          <select v-model="editDraft.role">
            <option value="super_admin">super_admin (все проекты)</option>
            <option value="admin">admin</option>
            <option value="manager">manager</option>
          </select>
        </label>
        <label>
          <span>Активен</span>
          <input v-model="editDraft.is_active" type="checkbox" />
        </label>
        <template v-if="editDraft.role !== 'super_admin'">
          <label>
            <span>Доступные проекты</span>
            <select v-model="editDraft.projects" multiple size="5">
              <option v-for="p in projects" :key="p.id" :value="p.id">
                {{ p.name }} ({{ p.slug }}, id={{ p.id }})
              </option>
            </select>
          </label>
          <label>
            <span>Роль внутри проектов</span>
            <select v-model="editDraft.project_role">
              <option value="admin">admin</option>
              <option value="manager">manager</option>
            </select>
          </label>
        </template>
        <div class="row">
          <button class="primary" type="submit">Сохранить</button>
          <button type="button" @click="cancelEdit">Отмена</button>
        </div>
      </form>
    </div>

    <div class="card">
      <h3 style="margin-top: 0;">Новый staff</h3>
      <form class="stack" @submit.prevent="submitCreate">
        <label>
          <span>Email</span>
          <input v-model="draft.email" type="email" required autocomplete="off" />
        </label>
        <label>
          <span>Пароль</span>
          <input v-model="draft.password" type="text" required autocomplete="off" />
        </label>
        <label>
          <span>ФИО</span>
          <input v-model="draft.full_name" type="text" autocomplete="off" />
        </label>
        <label>
          <span>Глобальная роль</span>
          <select v-model="draft.role">
            <option value="super_admin">super_admin (все проекты)</option>
            <option value="admin">admin</option>
            <option value="manager">manager</option>
          </select>
        </label>
        <template v-if="draft.role !== 'super_admin'">
          <label>
            <span>Доступные проекты</span>
            <select v-model="draft.projects" multiple size="5">
              <option v-for="p in projects" :key="p.id" :value="p.id">
                {{ p.name }} ({{ p.slug }}, id={{ p.id }})
              </option>
            </select>
          </label>
          <label>
            <span>Роль внутри проектов</span>
            <select v-model="draft.project_role">
              <option value="admin">admin</option>
              <option value="manager">manager</option>
            </select>
          </label>
        </template>
        <button class="primary" type="submit">Создать</button>
      </form>
    </div>
  </section>
</template>

<style scoped>
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
}
label span {
  padding-left: 4px;
  font-family: monospace;
}
.row {
  display: flex;
  gap: 8px;
}
</style>
