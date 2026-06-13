<script setup>
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { clearPendingReferralToken, peekPendingReferralToken } from '../referral/refCapture.js'
import { setSession } from '../auth/session.js'
import {
  normalizeEmailInput,
  validateLegalConsent,
  validateNewPasswordPair,
} from '../auth/credentialsValidation.js'
import AuthCredentialsFields from '../components/auth/AuthCredentialsFields.vue'
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
    const pwErr = validateNewPasswordPair(password.value, passwordConfirm.value)
    if (pwErr) {
      error.value = pwErr
      return
    }
    const legalErr = validateLegalConsent(acceptedLegal.value)
    if (legalErr) {
      error.value = legalErr
      return
    }
    const referral_token = peekPendingReferralToken()
    const body = {
      email: normalizeEmailInput(email.value),
      password: password.value,
      password_confirm: passwordConfirm.value,
    }
    if (referral_token) body.referral_token = referral_token
    const data = await fetchJson('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    clearPendingReferralToken()
    if (data.status === 'verification_required') {
      const q = new URLSearchParams({ email: data.email || body.email })
      if (data.message) q.set('message', data.message)
      router.replace({ path: '/verify-email-pending', query: Object.fromEntries(q) })
      return
    }
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
      <AuthCredentialsFields
        v-model:email="email"
        v-model:password="password"
        v-model:password-confirm="passwordConfirm"
        v-model:accepted-legal="acceptedLegal"
        show-password-confirm
        show-legal-consent
      />
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
</style>
