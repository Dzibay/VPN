<script setup>
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { clearPendingReferralToken, peekPendingReferralToken } from '../referral/refCapture.js'
import { setSession } from '../auth/session.js'
import SitePageLayout from '../components/SitePageLayout.vue'

const router = useRouter()

const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const acceptedLegal = ref(false)
const submitting = ref(false)
const error = ref(null)

async function submit() {
  submitting.value = true
  error.value = null
  try {
    if (password.value !== passwordConfirm.value) {
      error.value = 'Пароли не совпадают'
      return
    }
    if (!acceptedLegal.value) {
      error.value = 'Необходимо принять условия и дать согласие на обработку данных'
      return
    }
    const referral_token = peekPendingReferralToken()
    const body = {
      email: email.value.trim(),
      password: password.value,
    }
    if (referral_token) body.referral_token = referral_token
    const data = await fetchJson('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    clearPendingReferralToken()
    setSession(data.access_token, data.role)
    router.replace('/cabinet')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <SitePageLayout>
    <template #header>
      <header class="head">
        <RouterLink class="back" to="/">← На главную</RouterLink>
        <h1>Регистрация</h1>
      </header>
    </template>

    <form class="card card-pad form" @submit.prevent="submit">
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
          autocomplete="new-password"
          minlength="8"
          maxlength="72"
          required
        />
      </label>
      <label class="field">
        <span class="label">Подтверждение пароля</span>
        <input
          v-model="passwordConfirm"
          class="input"
          type="password"
          name="password-confirm"
          autocomplete="new-password"
          minlength="8"
          maxlength="72"
          required
        />
      </label>
      <label class="consent">
        <input
          v-model="acceptedLegal"
          class="consent-input"
          type="checkbox"
          name="legal-consent"
          required
        />
        <span class="consent-text">
          Я принимаю
          <RouterLink to="/terms" target="_blank">публичную оферту</RouterLink>,
          <RouterLink to="/privacy" target="_blank">политику конфиденциальности</RouterLink>
          и даю
          <RouterLink to="/consent" target="_blank">согласие на обработку персональных данных</RouterLink>
        </span>
      </label>
      <p v-if="error" class="err">{{ error }}</p>
      <button
        class="btn-primary btn-block"
        type="submit"
        :disabled="submitting || !acceptedLegal"
      >
        {{ submitting ? 'Регистрация…' : 'Создать аккаунт' }}
      </button>
      <p class="extra">
        Уже есть аккаунт?
        <RouterLink to="/login">Войти</RouterLink>
      </p>
    </form>
  </SitePageLayout>
</template>

<style scoped>
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

.btn-block {
  width: 100%;
  margin-top: 0.25rem;
}

.extra {
  margin: 0;
  text-align: center;
  font-size: 0.9rem;
  color: var(--muted);
}

.extra a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.extra a:hover {
  text-decoration: underline;
}

.consent {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  text-align: left;
  cursor: pointer;
}

.consent-input {
  flex-shrink: 0;
  width: 1.05rem;
  height: 1.05rem;
  margin-top: 0.2rem;
  accent-color: var(--accent);
}

.consent-text {
  font-size: 0.85rem;
  line-height: 1.45;
  color: var(--muted);
}

.consent-text a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.consent-text a:hover {
  text-decoration: underline;
}
</style>
