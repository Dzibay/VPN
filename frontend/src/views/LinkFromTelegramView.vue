<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { setSession } from '../auth/session.js'

const route = useRoute()
const router = useRouter()

const linkToken = computed(() => {
  const raw = route.query.token
  return typeof raw === 'string' ? raw.trim() : ''
})

const loading = ref(true)
const previewError = ref(null)
const preview = ref(null)

const email = ref('')
const password = ref('')
const submitting = ref(false)
const submitError = ref(null)

async function loadPreview() {
  loading.value = true
  previewError.value = null
  preview.value = null
  const t = linkToken.value
  if (!t) {
    previewError.value =
      'В ссылке нет параметра token. Откройте полную ссылку из Telegram-бота.'
    loading.value = false
    return
  }
  try {
    const q = new URLSearchParams({ token: t })
    preview.value = await fetchJson(
      `/api/auth/telegram/site-link/preview?${q.toString()}`,
    )
  } catch (e) {
    previewError.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

function telegramLabel(pg) {
  if (!pg) return '—'
  const id = pg.telegram_id
  const u = pg.telegram_properties?.username
  const parts = []
  if (id != null) parts.push(String(id))
  if (u) parts.push(`@${u}`)
  return parts.length ? parts.join(' ') : '—'
}

async function submit() {
  if (!preview.value?.can_add_credentials) return
  submitting.value = true
  submitError.value = null
  try {
    const data = await fetchJson('/api/auth/telegram/site-link/complete', {
      method: 'POST',
      body: JSON.stringify({
        link_token: linkToken.value,
        email: email.value.trim(),
        password: password.value,
      }),
    })
    setSession(data.access_token, data.role)
    router.replace('/cabinet')
  } catch (e) {
    submitError.value = e.message || String(e)
  } finally {
    submitting.value = false
  }
}

onMounted(loadPreview)
watch(linkToken, (next, prev) => {
  if (next !== prev) loadPreview()
})
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1>Доступ из Telegram</h1>
      <p class="sub">
        Если Вы впервые на сайте - введите email и пароль для возможности альтернативного управления аккаунтом.
        Если у Вас уже есть аккаунт на сайте - введите его данные и аккаунты будут обьединены.
      </p>
    </header>

    <div v-if="loading" class="card card-pad hint">Загрузка…</div>

    <div v-else-if="previewError" class="card card-pad">
      <p class="err">{{ previewError }}</p>
      <p class="muted">
        Запросите новую ссылку в боте или напишите в поддержку, если ошибка повторяется.
      </p>
    </div>

    <div v-else-if="preview" class="stack">
      <div class="card card-pad">
        <h2 class="block-title">Ваш аккаунт в Telegram</h2>
        <dl class="dl">
          <div class="row">
            <dt>Telegram</dt>
            <dd>{{ telegramLabel(preview) }}</dd>
          </div>
          <div v-if="preview.subscription_until" class="row">
            <dt>Подписка до</dt>
            <dd>{{ preview.subscription_until }}</dd>
          </div>
          <div v-else class="row">
            <dt>Подписка до</dt>
            <dd>—</dd>
          </div>
          <div class="row">
            <dt>Статус подписки</dt>
            <dd>{{ preview.subscription_active ? 'Активна' : 'Не активна' }}</dd>
          </div>
        </dl>
      </div>

      <div v-if="!preview.can_add_credentials" class="card card-pad">
        <p class="muted">
          К этому аккаунту уже указан email. Если пароль для сайта уже задан — откройте личный кабинет через
          кнопку в Telegram-боте или войдите через
          <RouterLink class="inl" to="/login">«Вход»</RouterLink>.
        </p>
      </div>

      <form
        v-else
        class="card card-pad form"
        @submit.prevent="submit"
      >
        <h2 class="block-title form-title">Email и пароль</h2>
        <p class="hint-form">
          Один пароль подходит для обоих сценариев: для нового email на сайте — не менее 8 символов;
          для уже существующего email на сайте — ваш обычный пароль входа (как при «Входе»).
        </p>
        <label class="field">
          <span class="label">Email</span>
          <input
            v-model="email"
            class="input"
            type="email"
            name="email"
            autocomplete="email"
            required
          />
        </label>
        <label class="field">
          <span class="label">Пароль</span>
          <input
            v-model="password"
            class="input"
            type="password"
            name="password"
            autocomplete="current-password"
            maxlength="72"
            required
          />
        </label>
        <p v-if="submitError" class="err">{{ submitError }}</p>
        <button
          class="btn-primary btn-block"
          type="submit"
          :disabled="submitting"
        >
          {{
            submitting
              ? 'Обработка…'
              : 'Продолжить и войти в кабинет'
          }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.page {
  width: 100%;
  max-width: 420px;
  min-width: min(280px, 100%);
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
  box-sizing: border-box;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

.back {
  display: inline-block;
  color: var(--muted);
  text-decoration: none;
  font-size: 0.9rem;
  font-weight: 500;
  margin-bottom: 1rem;
  transition: color 0.2s ease;
}

.back:hover {
  color: var(--accent);
}

h1 {
  font-size: 1.6rem;
  margin: 0 0 0.4rem;
}

.block-title {
  font-size: 1.05rem;
  margin: 0 0 0.85rem;
  text-align: left;
}

.form-title {
  margin-bottom: 0.5rem;
}

.hint-form {
  margin: 0 0 0.85rem;
  font-size: 0.875rem;
  color: var(--muted);
  line-height: 1.45;
  text-align: left;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.semi {
  font-weight: 600;
  color: var(--text-h);
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

.hint {
  text-align: center;
  color: var(--muted);
}

.dl {
  margin: 0;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 0.5rem 1rem;
  align-items: baseline;
  margin-bottom: 0.65rem;
  text-align: left;
}

.row:last-child {
  margin-bottom: 0;
}

.dt,
.row dt {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--muted);
}

.dd,
.row dd {
  margin: 0;
  font-size: 0.95rem;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: left;
}

.label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
}

.input {
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.err {
  margin: 0;
  color: var(--danger);
  font-size: 0.9rem;
}

.muted {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.inl {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.inl:hover {
  text-decoration: underline;
}

.btn-block {
  width: 100%;
  margin-top: 0.25rem;
}
</style>
