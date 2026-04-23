<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { fetchJson, subscriptionPublicUrl } from '../api/client.js'

const router = useRouter()

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<null | Record<string, unknown>>} */
const me = ref(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    me.value = await fetchJson('/api/auth/me')
  } catch (e) {
    if (e.status === 401) {
      router.replace({ name: 'login', query: { redirect: '/cabinet' } })
      return
    }
    error.value = e.message || String(e)
    me.value = null
  } finally {
    loading.value = false
  }
}

function formatDate(iso) {
  if (iso == null || iso === '') return '—'
  const s = String(iso)
  const d = s.length >= 10 ? s.slice(0, 10) : s
  return d
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="head">
      <RouterLink class="back" to="/">← На главную</RouterLink>
      <h1>Личный кабинет</h1>
      <p class="sub">Профиль и параметры подписки.</p>
    </header>

    <div v-if="loading" class="card card-pad muted">Загрузка…</div>
    <div v-else-if="error" class="card card-pad err">{{ error }}</div>
    <div v-else-if="me" class="stack">
      <div v-if="me.role === 'admin'" class="card card-pad">
        <h2 class="block-title">Администратор</h2>
        <p class="hint">
          Управление серверами и пользователями — в разделе ниже в шапке или
          <RouterLink class="sub-link" to="/admin">перейти к данным</RouterLink>.
        </p>
        <dl class="dl">
          <div class="row">
            <dt>Email</dt>
            <dd>{{ me.email }}</dd>
          </div>
        </dl>
      </div>

      <div v-else class="card card-pad">
        <h2 class="block-title">Профиль</h2>
        <dl class="dl">
          <div class="row">
            <dt>Email</dt>
            <dd>{{ me.email }}</dd>
          </div>
          <div v-if="me.telegram_id" class="row">
            <dt>Telegram</dt>
            <dd>{{ me.telegram_id }}</dd>
          </div>
          <div class="row">
            <dt>ID</dt>
            <dd>{{ me.id }}</dd>
          </div>
        </dl>
      </div>

      <div v-if="me.role === 'user'" class="card card-pad">
        <h2 class="block-title">Подписка</h2>
        <dl class="dl">
          <div class="row">
            <dt>Статус</dt>
            <dd>
              <span
                class="pill"
                :class="
                  me.subscription_active ? 'pill--ok' : 'pill--off'
                "
              >
                {{
                  me.subscription_active ? 'Активна' : 'Неактивна / истекла'
                }}
              </span>
            </dd>
          </div>
          <div class="row">
            <dt>Действует до</dt>
            <dd>{{ formatDate(me.subscription_until) }}</dd>
          </div>
        </dl>
      </div>

      <div v-if="me.role === 'user'" class="card card-pad">
        <h2 class="block-title">Ссылка подписки</h2>
        <p class="hint">
          Используйте в VPN-клиенте как subscription URL (если поддерживается).
        </p>
        <a
          class="sub-link"
          :href="subscriptionPublicUrl(me.subscription_token)"
          target="_blank"
          rel="noopener"
        >{{ subscriptionPublicUrl(me.subscription_token) }}</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 520px;
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
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

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1rem;
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

.muted {
  color: var(--muted);
}

.err {
  color: var(--danger);
}

.block-title {
  font-size: 1.05rem;
  margin: 0 0 1rem;
  color: var(--text-h);
}

.dl {
  margin: 0;
}

.row {
  display: grid;
  grid-template-columns: 8.5rem 1fr;
  gap: 0.5rem 1rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--nav-border);
  font-size: 0.92rem;
}

.row:last-child {
  border-bottom: none;
}

dt {
  margin: 0;
  color: var(--muted);
  font-weight: 600;
}

dd {
  margin: 0;
  color: var(--text-h);
  word-break: break-word;
}

.pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
}

.pill--ok {
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.pill--off {
  background: var(--danger-soft);
  color: var(--danger);
  border: 1px solid rgba(225, 29, 72, 0.35);
}

.hint {
  margin: 0 0 0.65rem;
  font-size: 0.88rem;
  color: var(--muted);
  line-height: 1.45;
}

.sub-link {
  font-size: 0.85rem;
  word-break: break-all;
  color: var(--accent);
  font-weight: 500;
}
</style>
