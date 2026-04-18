<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchJson, subscriptionPublicUrl } from '../api/client.js'

const users = ref([])
const usersCount = ref(null)
const loading = ref(true)
const error = ref(null)

const modalOpen = ref(false)
const creating = ref(false)
const createError = ref(null)
const formTelegramId = ref('')
const formSubUntil = ref('')

async function loadUsers() {
  loading.value = true
  error.value = null
  try {
    const [list, countRes] = await Promise.all([
      fetchJson('/api/users'),
      fetchJson('/api/users/count'),
    ])
    users.value = list
    usersCount.value = countRes.users_count
  } catch (e) {
    error.value = e.message || String(e)
    users.value = []
    usersCount.value = null
  } finally {
    loading.value = false
  }
}

function openModal() {
  createError.value = null
  formTelegramId.value = ''
  formSubUntil.value = ''
  modalOpen.value = true
}

function closeModal() {
  if (creating.value) return
  modalOpen.value = false
}

/** `YYYY-MM-DD` из input[type=date] — в API уходит как дата (тип DATE в БД). */
function subscriptionDateOrNull(dateStr) {
  if (!dateStr || !String(dateStr).trim()) return null
  const s = String(dateStr).trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  return s
}

function normalizeTelegramId(raw) {
  let t = String(raw ?? '').trim()
  if (t.startsWith('@')) t = t.slice(1).trim()
  return t === '' ? null : `@${t}`
}

async function submitCreate() {
  creating.value = true
  createError.value = null
  try {
    await fetchJson('/api/users', {
      method: 'POST',
      body: JSON.stringify({
        telegram_id: normalizeTelegramId(formTelegramId.value),
        subscription_until: subscriptionDateOrNull(formSubUntil.value),
      }),
    })
    modalOpen.value = false
    await loadUsers()
  } catch (e) {
    createError.value = e.message || String(e)
  } finally {
    creating.value = false
  }
}

/** Дата с API (YYYY-MM-DD или ISO); без сдвига из‑за часового пояса. */
function formatDate(value) {
  if (!value) return '—'
  const s = String(value)
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (m) {
    return `${m[3]}.${m[2]}.${m[1]}`
  }
  try {
    return new Date(s).toLocaleDateString()
  } catch {
    return s
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* ignore */
  }
}

onMounted(loadUsers)
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <div class="head-row">
        <h1>Пользователи</h1>
        <button type="button" class="btn-primary" @click="openModal">
          Новый пользователь
        </button>
      </div>
      <p class="sub">Токен подписки создаётся на сервере</p>
    </header>

    <section class="stats" aria-live="polite">
      <h2 class="stats-title">Пользователей в базе</h2>
      <p v-if="loading" class="stats-value muted">Загрузка…</p>
      <p v-else-if="error" class="stats-value error" :title="error">
        Не удалось загрузить
      </p>
      <p v-else class="stats-value">{{ usersCount }}</p>
    </section>

    <div v-if="!loading && error" class="card err">
      {{ error }}
      <button type="button" class="btn-secondary" @click="loadUsers">
        Повторить
      </button>
    </div>
    <div v-else-if="!loading && users.length === 0" class="card muted">
      Пока нет пользователей. Создайте первого.
    </div>
    <div v-else-if="!loading" class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Telegram</th>
            <th>Подписка до</th>
            <th>Токен</th>
            <th>Ссылка подписки</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td>
            <td>{{ u.telegram_id ?? '—' }}</td>
            <td>{{ formatDate(u.subscription_until) }}</td>
            <td class="mono">
              <span class="token" :title="u.token">{{ u.token }}</span>
              <button
                type="button"
                class="btn-secondary btn-tiny"
                @click="copyText(u.token)"
              >
                Копировать
              </button>
            </td>
            <td class="link-cell">
              <a
                class="sub-link"
                :href="subscriptionPublicUrl(u.token)"
                target="_blank"
                rel="noopener"
              >{{ subscriptionPublicUrl(u.token) }}</a>
              <button
                type="button"
                class="btn-secondary btn-tiny"
                @click="copyText(subscriptionPublicUrl(u.token))"
              >
                Копировать
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Teleport to="body">
      <div
        v-if="modalOpen"
        class="modal-backdrop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        @click.self="closeModal"
      >
        <div class="modal">
          <h2 id="modal-title">Новый пользователь</h2>
          <form class="form" @submit.prevent="submitCreate">
            <label class="field">
              <span>Telegram (необязательно)</span>
              <div class="input-with-at">
                <span class="input-at" aria-hidden="true">@</span>
                <input
                  v-model="formTelegramId"
                  type="text"
                  inputmode="text"
                  autocomplete="off"
                  autocapitalize="none"
                  spellcheck="false"
                  placeholder="username"
                />
              </div>
            </label>
            <label class="field">
              <span>Подписка до (необязательно)</span>
              <input v-model="formSubUntil" type="date" />
            </label>
            <p v-if="createError" class="form-err">{{ createError }}</p>
            <div class="modal-actions">
              <button
                type="button"
                class="btn-secondary"
                :disabled="creating"
                @click="closeModal"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="btn-primary"
                :disabled="creating"
              >
                {{ creating ? 'Создание…' : 'Создать' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1rem 1rem 2.5rem;
}
.head {
  margin-bottom: 1rem;
}
.back {
  display: inline-block;
  margin-bottom: 0.5rem;
  color: var(--muted);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.2s ease;
}

.back:hover {
  color: var(--accent);
}
.head-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.head-row h1 {
  font-size: 1.65rem;
  margin: 0;
  letter-spacing: -0.02em;
}
.sub {
  color: var(--muted);
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
}
.stats {
  margin: 0 0 1rem;
  max-width: 240px;
  padding: 0.9rem 1.1rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.stats-title {
  margin: 0 0 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}
.stats-value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
}
.stats-value.muted {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--muted);
}
.stats-value.error {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--danger);
}
.card {
  padding: 1rem 1.15rem;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.card.err {
  border-color: var(--danger);
  background: var(--danger-soft);
  color: var(--danger);
}
.card.muted {
  color: var(--muted);
}
.table-wrap {
  overflow-x: auto;
  border-radius: 14px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: var(--shadow-sm);
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.table th,
.table td {
  padding: 0.65rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
  color: var(--text);
}
.table th {
  color: var(--muted);
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
}
.mono {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--text-h);
}

.mono .btn-secondary,
.link-cell .btn-secondary {
  margin-top: 0.45rem;
  margin-right: 0.35rem;
}
.token {
  display: block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-cell {
  font-size: 0.78rem;
}
.sub-link {
  display: inline-block;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--accent);
  font-weight: 600;
  vertical-align: middle;
  transition: color 0.2s ease;
}

.sub-link:hover {
  color: var(--accent-hover);
}
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(26, 18, 38, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 50;
}

@media (prefers-color-scheme: dark) {
  .modal-backdrop {
    background: rgba(8, 6, 12, 0.72);
  }
}

.modal {
  width: 100%;
  max-width: 420px;
  padding: 1.35rem 1.45rem;
  border-radius: 16px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  box-shadow: var(--shadow-lg);
}
.modal h2 {
  margin: 0 0 1rem;
  font-size: 1.15rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--muted);
}

.field input[type='date'] {
  padding: 0.55rem 0.7rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  font-weight: 400;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.field input[type='date']:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.input-with-at {
  display: flex;
  align-items: stretch;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  overflow: hidden;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input-with-at:focus-within {
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.input-at {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  padding: 0 0.5rem 0 0.65rem;
  font-weight: 700;
  font-size: 0.95rem;
  color: var(--accent);
  background: var(--accent-soft);
  border-right: 1px solid var(--card-border);
  user-select: none;
}

.field .input-with-at input {
  flex: 1;
  min-width: 0;
  margin: 0;
  padding: 0.55rem 0.7rem;
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--text-h);
  font: inherit;
  font-weight: 400;
}

.field .input-with-at input:focus {
  outline: none;
  box-shadow: none;
}

.field .input-with-at input::placeholder {
  color: var(--muted);
  opacity: 0.75;
}

.form-err {
  margin: 0;
  font-size: 0.85rem;
  color: var(--danger);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.65rem;
}
</style>
