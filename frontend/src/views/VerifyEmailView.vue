<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { fetchJson } from '../api/client.js'
import { setSession } from '../auth/session.js'
import SitePageLayout from '../components/SitePageLayout.vue'

const route = useRoute()
const router = useRouter()

const token = computed(() => {
  const raw = route.query.token
  return typeof raw === 'string' ? raw.trim() : ''
})

const loading = ref(true)
const error = ref(null)

async function verify() {
  loading.value = true
  error.value = null
  const t = token.value
  if (!t) {
    error.value = 'В ссылке нет параметра token. Откройте полную ссылку из письма.'
    loading.value = false
    return
  }
  try {
    const q = new URLSearchParams({ token: t })
    const data = await fetchJson(`/api/auth/verify-email?${q.toString()}`)
    setSession(data.access_token, data.role)
    router.replace('/cabinet')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(verify)
</script>

<template>
  <SitePageLayout>
    <template #header>
      <header class="head">
        <RouterLink class="back" to="/">← На главную</RouterLink>
        <h1>Подтверждение email</h1>
      </header>
    </template>

    <div class="card card-pad">
      <p v-if="loading" class="hint">Проверяем ссылку…</p>
      <template v-else-if="error">
        <p class="err">{{ error }}</p>
        <p class="muted">
          Запросите новое письмо на странице
          <RouterLink class="inl" to="/login">входа</RouterLink>
          или при повторной регистрации.
        </p>
      </template>
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

.hint {
  margin: 0;
  text-align: center;
  color: var(--muted);
}

.err {
  margin: 0 0 0.75rem;
  color: var(--danger);
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
</style>
