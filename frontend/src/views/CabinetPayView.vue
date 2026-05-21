<script setup>
import { computed, onMounted, ref } from 'vue'
import { Send } from 'lucide-vue-next'
import { fetchJson } from '../api/client.js'
import AppActionButton from '../components/AppActionButton.vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'

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

// Вспомогательная функция для красивого отображения периода
function formatPeriod(months) {
  if (!months) return ''
  if (months === 1) return '1 месяц'
  if (months === 3) return '3 месяца'
  if (months === 6) return '6 месяцев'
  if (months === 12) return '1 год'
  return `${months} мес.`
}

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
  <main class="app-dl">
    <div class="app-dl-wrap">
      <CabinetBackLink :to="{ name: 'cabinet', query: { tab: 'subscription' } }" />

      <div v-if="loading" class="card card-pad muted loader-block">
          <div class="spinner" />
          <span>Загрузка доступных тарифов…</span>
      </div>

      <div v-else-if="error" class="card card-pad err" role="alert">
        {{ error }}
      </div>

      <div v-else class="stack">
          <p v-if="!hasAnyOption" class="card card-pad muted pay-empty">
        Способы оплаты на сервере пока не настроены. Напишите в поддержку или попробуйте позже.
      </p>

      <section v-if="hasRecurring" class="pay-group">
        <div class="recurring-grid">
          <div
            v-for="(rec, i) in recurringOptions"
            :key="`${rec.name}-${rec.web_link}-${i}`"
            class="card card-pad product-card product-card--recurring"
          >
            <div class="product-badge" v-if="i === 0">Рекомендуем</div>
            <h3 class="product-title">{{ rec.name }}</h3>
            
            <div class="product-price-block" v-if="rec.price">
              <span class="price-amount">{{ rec.price }} ₽</span>
              <span class="price-period">/ месяц</span>
            </div>
            <p class="product-hint">Можно оформить в браузере или через Telegram с привязкой карты для ежемесячного списания. Будьте всегда на связи.</p>

            <div class="recurring-actions">
              <AppActionButton
                v-if="rec.tg_link"
                variant="telegram"
                block
                class="pay-tg-open-btn"
                :href="rec.tg_link"
                target="_blank"
                rel="noopener noreferrer"
              >
                <template #icon>
                  <Send
                    :size="20"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                </template>
                Оплатить в Telegram
              </AppActionButton>
              <AppActionButton
                variant="secondary"
                block
                :href="rec.web_link"
                target="_blank"
                rel="noopener noreferrer"
              >
                Оплатить картой на сайте
              </AppActionButton>
            </div>
          </div>
        </div>
      </section>

      <section v-if="hasSingles" class="pay-group">
        <div class="section-header">
          <h2 class="section-title">Разовые тарифы (СБП)</h2>
          <p class="section-desc">Оплачивайте фиксированный период в браузере. Без привязки карты и автоматических списаний. Доступна оплата через СПБ.</p>
        </div>
        
        <div class="tariffs-grid">
          <div 
            v-for="row in singleOptions" 
            :key="`${row.months}-${row.web_link}`" 
            class="card card-pad product-card"
            :class="{ 'product-card--popular': row.months === 12 || row.months === 6 }"
          >
            <div class="product-badge" v-if="row.months === 12">Лучшая цена</div>
            
            <div class="product-main-info">
              <span class="product-duration">
                {{ row.months ? formatPeriod(row.months) : row.name }}
              </span>
            </div>

            <div class="product-price-block" v-if="row.price">
              <span class="price-amount">{{ row.price }} ₽</span>
              <span class="price-calc-hint" v-if="row.months && row.months > 1">
                (~{{ Math.round(row.price / row.months) }} ₽/мес)
              </span>
            </div>

            <AppActionButton
              variant="primary"
              block
              :href="row.web_link"
              target="_blank"
              rel="noopener noreferrer"
            >
              Выбрать тариф
            </AppActionButton>
          </div>
        </div>
      </section>

      <p v-if="hasAnyOption && !hasSingles" class="hint foot-hint">
        Разовые тарифы сейчас недоступны — при необходимости используйте регулярную подписку.
      </p>
      <p v-if="hasAnyOption && !hasRecurring" class="hint foot-hint">
        Автоматическая подписка сейчас не настроена — доступны только разовые пакеты дней.
      </p>
      </div>
    </div>
  </main>
</template>

<style scoped>
.app-dl {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  font: inherit;
  color: var(--text);
  background: var(--bg-gradient);
}

.app-dl-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: min(var(--page-content-max, 25rem), 100%);
  min-width: 0;
  margin-inline: auto;
  padding: 1.5rem max(1rem, env(safe-area-inset-left, 0px)) 2.5rem
    max(1rem, env(safe-area-inset-right, 0px));
  box-sizing: border-box;
  gap: 0.75rem;
}

.app-dl-wrap > .card {
  width: 100%;
  box-sizing: border-box;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  width: 100%;
  min-width: 0;
}

/* Карточки общего контейнера */
.card {
  min-width: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.card-pad {
  padding: 1.25rem 1.35rem;
}

/* Группировка секций */
.pay-group {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.section-header {
  text-align: left;
}

.section-title {
  font-size: 1.15rem;
  margin: 0 0 0.25rem;
  color: var(--text-h);
  font-weight: 600;
}

.section-desc {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.4;
  color: var(--muted);
}

/* Сетки для карточек товаров */
.tariffs-grid, .recurring-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

@media (min-width: 420px) {
  .tariffs-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Базовые стили карточки продукта */
.product-card {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 1rem;
  background: var(--card-bg);
  overflow: hidden;
}

.product-card:hover {
  border-color: rgba(var(--accent-rgb, 59, 130, 246), 0.4);
}

/* Выделение популярных/выгодных вариантов */
.product-card--popular, .product-card--recurring {
  border-color: rgba(var(--accent-rgb, 59, 130, 246), 0.25);
  background: linear-gradient(to bottom right, var(--card-bg), var(--surface-glass, rgba(255, 255, 255, 0.01)));
}

.product-badge {
  position: absolute;
  top: 0;
  right: 0;
  background: var(--accent);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 700;
  padding: 0.25rem 0.65rem;
  border-bottom-left-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

/* Информация внутри карточки */
.product-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-h);
}

.product-main-info {
  display: flex;
  flex-direction: column;
}

.product-duration {
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--muted);
  line-height: 1.35;
}

/* Блок цены */
.product-price-block {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
  margin-top: auto;
}

.price-amount {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-h);
  letter-spacing: -0.01em;
}

.price-period {
  font-size: 0.85rem;
  color: var(--muted);
}

.price-calc-hint {
  font-size: 0.78rem;
  color: var(--accent);
  font-weight: 500;
}

.product-hint {
  margin: -0.25rem 0 0.25rem;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--muted);
}

.recurring-actions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
}

.pay-tg-open-btn {
  min-height: 3rem;
  padding: 0.72rem 1rem;
  border-radius: 10px;
}

/* Вспомогательные элементы */
.loader-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  text-align: center;
  padding: 2.5rem 1rem;
}

.spinner {
  width: 1.75rem;
  height: 1.75rem;
  border: 2px solid var(--card-border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.pay-empty {
  text-align: center;
  padding: 2rem 1rem;
}

.err {
  color: var(--danger);
  text-align: center;
}

.foot-hint {
  margin: 0;
  text-align: center;
  font-size: 0.82rem;
  color: var(--muted);
}
</style>