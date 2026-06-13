<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { setSession } from '../auth/session.js'
import {
  normalizeEmailInput,
  validateEmailInput,
  validateLegalConsent,
  validateNewPasswordPair,
} from '../auth/credentialsValidation.js'
import AuthCredentialsFields from '../components/auth/AuthCredentialsFields.vue'
import SitePageLayout from '../components/SitePageLayout.vue'

const route = useRoute()
const router = useRouter()

const LINK_MODES = {
  new: 'new',
  existing: 'existing',
}

const linkToken = computed(() => {
  const raw = route.query.token
  return typeof raw === 'string' ? raw.trim() : ''
})

const loading = ref(true)
const previewError = ref(null)
const preview = ref(null)

const linkMode = ref(LINK_MODES.new)
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const acceptedLegal = ref(false)
const submitting = ref(false)
const submitError = ref(null)

const isNewEmailMode = computed(() => linkMode.value === LINK_MODES.new)
const submitDisabled = computed(() => {
  if (submitting.value) return true
  if (isNewEmailMode.value && !acceptedLegal.value) return true
  return false
})

function resetFormFields() {
  email.value = ''
  password.value = ''
  passwordConfirm.value = ''
  acceptedLegal.value = false
  submitError.value = null
}

function setLinkMode(mode) {
  if (linkMode.value === mode) return
  linkMode.value = mode
  resetFormFields()
}

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

function validateBeforeSubmit() {
  const emailErr = validateEmailInput(email.value)
  if (emailErr) return emailErr
  if (isNewEmailMode.value) {
    const pwErr = validateNewPasswordPair(password.value, passwordConfirm.value)
    if (pwErr) return pwErr
    const legalErr = validateLegalConsent(acceptedLegal.value)
    if (legalErr) return legalErr
  } else if (!password.value) {
    return 'Введите пароль от аккаунта на сайте'
  }
  return null
}

async function submit() {
  if (!preview.value?.can_add_credentials) return
  submitting.value = true
  submitError.value = null
  try {
    const validationError = validateBeforeSubmit()
    if (validationError) {
      submitError.value = validationError
      return
    }
    const body = {
      link_token: linkToken.value,
      email: normalizeEmailInput(email.value),
      password: password.value,
    }
    if (isNewEmailMode.value) {
      body.password_confirm = passwordConfirm.value
    }
    const data = await fetchJson('/api/auth/telegram/site-link/complete', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (data.status === 'verification_required') {
      const q = new URLSearchParams({
        email: data.email || normalizeEmailInput(email.value),
      })
      if (data.message) q.set('message', data.message)
      router.replace({ path: '/verify-email-pending', query: Object.fromEntries(q) })
      return
    }
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
  <SitePageLayout>
    <template #header>
      <header class="head">
        <RouterLink class="back" to="/">← На главную</RouterLink>
        <h1>Доступ из Telegram</h1>
        <p class="sub">
          Привяжите email к аккаунту Telegram: создайте новый вход на сайте или объедините
          с уже существующим аккаунтом.
        </p>
      </header>
    </template>

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
        <h2 class="block-title form-title">Привязка email</h2>

        <div
          class="mode-tabs"
          role="tablist"
          aria-label="Способ привязки email"
        >
          <button
            type="button"
            role="tab"
            class="mode-tab"
            :class="{ 'mode-tab--active': isNewEmailMode }"
            :aria-selected="isNewEmailMode"
            @click="setLinkMode(LINK_MODES.new)"
          >
            Новый email
          </button>
          <button
            type="button"
            role="tab"
            class="mode-tab"
            :class="{ 'mode-tab--active': !isNewEmailMode }"
            :aria-selected="!isNewEmailMode"
            @click="setLinkMode(LINK_MODES.existing)"
          >
            Уже есть аккаунт
          </button>
        </div>

        <p class="hint-form">
          <template v-if="isNewEmailMode">
            Укажите новый email и пароль для входа на сайте. Пароль нужно ввести дважды для подтверждения.
          </template>
          <template v-else>
            Введите email и пароль от существующего аккаунта на сайте — аккаунты будут объединены.
          </template>
        </p>

        <AuthCredentialsFields
          v-model:email="email"
          v-model:password="password"
          v-model:password-confirm="passwordConfirm"
          v-model:accepted-legal="acceptedLegal"
          :show-password-confirm="isNewEmailMode"
          :show-legal-consent="isNewEmailMode"
          :password-autocomplete="isNewEmailMode ? 'new-password' : 'current-password'"
          :password-min-length="isNewEmailMode ? 8 : 0"
          :password-label="isNewEmailMode ? 'Пароль' : 'Пароль от аккаунта на сайте'"
        />

        <p v-if="submitError" class="err">{{ submitError }}</p>
        <button
          class="btn-primary btn-block"
          type="submit"
          :disabled="submitDisabled"
        >
          {{
            submitting
              ? 'Обработка…'
              : isNewEmailMode
                ? 'Привязать email и войти в кабинет'
                : 'Объединить аккаунты и войти'
          }}
        </button>
      </form>
    </div>
  </SitePageLayout>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
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

.mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem;
}

.mode-tab {
  appearance: none;
  margin: 0;
  min-height: 2.45rem;
  padding: 0.5rem 0.65rem;
  border-radius: var(--radius-pill);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.25;
  cursor: pointer;
  text-align: center;
  color: var(--muted);
  border: 1px solid var(--card-border);
  background: var(--surface);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease;
}

.mode-tab:hover {
  color: var(--accent);
  border-color: var(--accent-border);
}

.mode-tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.mode-tab--active {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

.mode-tab--active:hover {
  color: var(--on-accent);
  background: var(--accent-hover);
  border-color: var(--accent-hover);
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
