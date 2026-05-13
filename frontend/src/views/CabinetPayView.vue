<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchJson } from '../api/client.js'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import SitePageLayout from '../components/SitePageLayout.vue'

const loading = ref(true)
const error = ref(null)
/** @type {import('vue').Ref<{ tariffs: Array<{ type: string, name: string, web_link: string, tg_link: string | null, months: number | null, price: number | null }> } | null>} */
const links = ref(null)

const tariffList = computed(() => links.value?.tariffs ?? [])
const singleOptions = computed(() => tariffList.value.filter((o) => o.type === 'single'))
const recurringOptions = computed(() => tariffList.value.filter((o) => o.type === 'recurring'))

const hasSingles = computed(() => singleOptions.value.length > 0)
const hasRecurring = computed(() => recurringOptions.value.length > 0)
const hasAnyOption = computed(() => tariffList.value.length > 0)

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
  <SitePageLayout
    as="main"
    compact-top
  >
    <template #header>
      <header class="head">
        <h1>Оплата и продление</h1>
        <div class="page-back">
          <CabinetBackLink :to="{ name: 'cabinet', query: { tab: 'subscription' } }" />
        </div>
      </header>
    </template>

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

      <section v-if="hasSingles" class="card card-pad pay-section" aria-labelledby="pay-once-title">
        <h2 id="pay-once-title" class="block-title">Разовая оплата</h2>
        <p class="hint">
          Оплатите нужный срок один раз в браузере (без привязки карты к автопродлению). После успешной
          оплаты доступ продлится автоматически.
        </p>
        <ul class="tariff-list" role="list">
          <li v-for="row in singleOptions" :key="`${row.months}-${row.web_link}`" class="tariff-item">
            <a
              class="tariff-link"
              :href="row.web_link"
              target="_blank"
              rel="noopener noreferrer"
            >{{ row.name }}</a>
          </li>
        </ul>
      </section>

      <section
        v-for="(rec, i) in recurringOptions"
        :key="`${rec.name}-${rec.web_link}-${i}`"
        class="card card-pad pay-section"
        :aria-labelledby="'pay-recurring-title-' + i"
      >
        <h2 :id="'pay-recurring-title-' + i" class="block-title">{{ rec.name }}</h2>
        <p class="hint">
          Карта сохраняется для следующих списаний. Можно оформить из
          Telegram или в браузере.
        </p>
        <div class="recurring-actions">
          <a
            v-if="rec.tg_link"
            class="btn-primary recurring-btn"
            :href="rec.tg_link"
            target="_blank"
            rel="noopener noreferrer"
          >Оплатить в Telegram</a>
          <a
            class="btn-secondary recurring-btn"
            :href="rec.web_link"
            target="_blank"
            rel="noopener noreferrer"
          >Оплатить в браузере</a>
        </div>
      </section>

      <p v-if="hasAnyOption && !hasSingles" class="hint foot-hint">
        Разовые тарифы сейчас недоступны — при необходимости используйте подписку или обратитесь в поддержку.
      </p>
      <p v-if="hasAnyOption && !hasRecurring" class="hint foot-hint">
        Подписка с картой сейчас не настроена — доступен только разовый вариант оплаты.
      </p>
    </div>
  </SitePageLayout>
</template>

<style scoped>
.page-back {
  width: 100%;
  max-width: min(var(--page-content-max, 25rem), 100%);
  align-self: start;
  text-align: left;
}

.head {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

h1 {
  font-size: 1.55rem;
  margin: 0;
  color: var(--text-h);
  text-align: center;
  width: 100%;
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
  min-width: 0;
}

.card {
  min-width: 0;
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
