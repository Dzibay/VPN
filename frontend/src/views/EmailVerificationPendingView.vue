<script setup>
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { fetchJson } from '../api/client.js'
import SitePageLayout from '../components/SitePageLayout.vue'

const route = useRoute()

const email = computed(() => {
  const raw = route.query.email
  return typeof raw === 'string' ? raw.trim() : ''
})

const message = computed(() => {
  const raw = route.query.message
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null
})

const resending = ref(false)
const resendError = ref(null)
const resendOk = ref(false)

async function resend() {
  if (!email.value) return
  resending.value = true
  resendError.value = null
  resendOk.value = false
  try {
    await fetchJson('/api/auth/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email: email.value }),
    })
    resendOk.value = true
  } catch (e) {
    resendError.value = e.message || String(e)
  } finally {
    resending.value = false
  }
}
</script>

<template>
  <SitePageLayout>
    <template #header>
      <header class="head">
        <RouterLink class="back" to="/">← На главную</RouterLink>
        <h1>Подтвердите email</h1>
      </header>
    </template>

    <div class="card card-pad">
      <p class="lead">
        {{
          message ||
            'На указанный адрес отправлено письмо со ссылкой для подтверждения. Перейдите по ссылке, чтобы войти в личный кабинет.'
        }}
      </p>
      <p v-if="email" class="email-line">
        Адрес: <strong>{{ email }}</strong>
      </p>
      <p class="muted">
        Не пришло письмо? Проверьте папку «Спам» или запросите отправку ещё раз.
      </p>
      <button
        v-if="email"
        class="btn-primary btn-block"
        type="button"
        :disabled="resending"
        @click="resend"
      >
        {{ resending ? 'Отправка…' : 'Отправить письмо ещё раз' }}
      </button>
      <p v-if="resendOk" class="ok">Письмо отправлено повторно.</p>
      <p v-if="resendError" class="err">{{ resendError }}</p>
      <p class="extra">
        Уже подтвердили?
        <RouterLink to="/login">Войти</RouterLink>
      </p>
    </div>
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
}

.back:hover {
  color: var(--accent);
}

h1 {
  font-size: 1.6rem;
  margin: 0;
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

.lead {
  margin: 0 0 1rem;
  line-height: 1.5;
}

.email-line {
  margin: 0 0 1rem;
}

.muted {
  margin: 0 0 1rem;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.btn-block {
  width: 100%;
}

.ok {
  margin: 0.75rem 0 0;
  color: var(--accent);
  font-size: 0.9rem;
}

.err {
  margin: 0.75rem 0 0;
  color: var(--danger);
  font-size: 0.9rem;
}

.extra {
  margin: 1.25rem 0 0;
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
