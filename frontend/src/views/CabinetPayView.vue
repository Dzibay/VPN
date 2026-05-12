<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchJson } from '../api/client.js'

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<{ tariffs: Record<string, string> | null, recurring_pay: { tg_link: string, web_link: string } | null } | null>} */
const links = ref(null)

const hasTariffs = computed(() => links.value?.tariffs != null)
const hasRecurring = computed(() => links.value?.recurring_pay != null)
const hasAnyOption = computed(() => hasTariffs.value || hasRecurring.value)

const tariffRows = computed(() => {
  const t = links.value?.tariffs
  if (!t) return []
  return [
    { label: '1 месяц', href: t.web_link_1m },
    { label: '3 месяца', href: t.web_link_3m },
    { label: '6 месяцев', href: t.web_link_6m },
    { label: '1 год', href: t.web_link_1y },
  ]
})

async function load() {
  loading.value = true
  error.value = null
  try {
    links.value = await fetchJson('/api/me/payments/tribute-links')
  } catch (e) {
    error.value = e.message || String(e)
    links.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <main class="page">
    <nav class="back-nav" aria-label="Назад">
      <RouterLink class="back-link" :to="{ name: 'cabinet', query: { tab: 'subscription' } }">
        ← Личный кабинет
      </RouterLink>
    </nav>

    <header class="head">
      <h1>Оплата и продление</h1>
      <p class="sub">
        Выберите способ: разовая оплата выбранного периода или подписка с сохранением карты в Tribute.
      </p>
    </header>

    <div v-if="loading" class="card card-pad muted">
      Загрузка вариантов оплаты…
    </div>
    <div v-else-if="error" class="card card-pad err" role="alert">
      {{ error }}
    </div>
    <div v-else class="stack">
      <p v-if="!hasAnyOption" class="card card-pad muted pay-empty">
        Способы оплаты на сервере пока не настроены. Напишите в поддержку или попробуйте позже.
      </p>

      <section v-if="hasTariffs" class="card card-pad pay-section" aria-labelledby="pay-once-title">
        <h2 id="pay-once-title" class="block-title">Разовая оплата</h2>
        <p class="hint">
          Оплатите нужный срок один раз в браузере (без привязки карты к автопродлению). После успешной
          оплаты доступ продлится автоматически.
        </p>
        <ul class="tariff-list" role="list">
          <li v-for="row in tariffRows" :key="row.label" class="tariff-item">
            <a
              class="tariff-link"
              :href="row.href"
              target="_blank"
              rel="noopener noreferrer"
            >{{ row.label }}</a>
          </li>
        </ul>
      </section>

      <section
        v-if="hasRecurring"
        class="card card-pad pay-section"
        aria-labelledby="pay-recurring-title"
      >
        <h2 id="pay-recurring-title" class="block-title">Подписка с картой</h2>
        <p class="hint">
          Рекуррентная подписка Tribute: карта сохраняется для следующих списаний. Можно оформить из
          Telegram или в браузере.
        </p>
        <div class="recurring-actions">
          <a
            class="btn-primary recurring-btn"
            :href="links?.recurring_pay?.tg_link"
            target="_blank"
            rel="noopener noreferrer"
          >Оплатить в Telegram</a>
          <a
            class="btn-secondary recurring-btn"
            :href="links?.recurring_pay?.web_link"
            target="_blank"
            rel="noopener noreferrer"
          >Оплатить в браузере</a>
        </div>
      </section>

      <p v-if="hasAnyOption && !hasTariffs" class="hint foot-hint">
        Разовые тарифы сейчас недоступны — при необходимости используйте подписку или обратитесь в поддержку.
      </p>
      <p v-if="hasAnyOption && !hasRecurring" class="hint foot-hint">
        Подписка с картой сейчас не настроена — доступен только разовый вариант оплаты.
      </p>
    </div>
  </main>
</template>

<style scoped>
.page {
  max-width: 520px;
  margin: 0 auto;
  padding: 1.75rem 1rem 2.5rem;
}

.back-nav {
  margin-bottom: 1rem;
}

.back-link {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
}

.back-link:hover {
  text-decoration: underline;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

h1 {
  font-size: 1.55rem;
  margin: 0 0 0.5rem;
  color: var(--text-h);
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
  margin: 0 0 0.65rem;
  color: var(--text-h);
}

.hint {
  margin: 0 0 1rem;
  font-size: 0.86rem;
  line-height: 1.45;
  color: var(--muted);
}

.pay-empty {
  text-align: center;
}

.pay-section .hint {
  margin-bottom: 1.1rem;
}

.tariff-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

@media (min-width: 400px) {
  .tariff-list {
    grid-template-columns: 1fr 1fr;
  }
}

.tariff-item {
  margin: 0;
}

.tariff-link {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 2.65rem;
  padding: 0.5rem 0.75rem;
  border-radius: 10px;
  font-weight: 600;
  font-size: 0.9rem;
  text-decoration: none;
  text-align: center;
  color: var(--text-h);
  border: 1px solid var(--card-border);
  background: var(--surface);
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}

.tariff-link:hover {
  border-color: var(--accent);
  background: var(--surface);
  filter: brightness(1.03);
}

.recurring-actions {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.recurring-btn {
  display: block;
  width: 100%;
  text-align: center;
  text-decoration: none;
  box-sizing: border-box;
  padding: 0.65rem 1rem;
  border-radius: 10px;
  font: inherit;
  font-weight: 600;
  font-size: 0.92rem;
  cursor: pointer;
}

.foot-hint {
  margin: 0;
  text-align: center;
}
</style>
