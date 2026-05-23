<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchJson } from '../api/client.js'
import AppActionButton from '../components/AppActionButton.vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'

const loading = ref(true)
const error = ref(null)
const payingMonths = ref(null)
/** @type {import('vue').Ref<{ tariffs: Array<{ months: number, price: number, name: string }> } | null>} */
const tariffsData = ref(null)

const tariffList = computed(() => tariffsData.value?.tariffs ?? [])
const hasAnyOption = computed(() => tariffList.value.length > 0)

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
    tariffsData.value = await fetchJson('/api/me/payments/yookassa-tariffs')
  } catch (e) {
    error.value = e.message || String(e)
    tariffsData.value = null
  } finally {
    loading.value = false
  }
}

async function startCheckout(months) {
  if (payingMonths.value != null) return
  payingMonths.value = months
  error.value = null
  try {
    const res = await fetchJson('/api/me/payments/yookassa/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ months }),
    })
    const url = res?.confirmation_url
    if (!url || typeof url !== 'string') {
      throw new Error('Сервер не вернул ссылку на оплату')
    }
    window.location.href = url
  } catch (e) {
    error.value = e.message || String(e)
    payingMonths.value = null
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

        <section v-else class="pay-group">
          <div class="section-header">
            <h2 class="section-title">Разовые тарифы</h2>
            <p class="section-desc">
              Оплата картой или СБП через ЮKassa. Без привязки карты и автоматических списаний.
              Автоподписка — в Telegram-боте.
            </p>
          </div>

          <div class="tariffs-grid">
            <div
              v-for="row in tariffList"
              :key="row.months"
              class="card card-pad product-card"
              :class="{ 'product-card--popular': row.months === 12 || row.months === 6 }"
            >
              <div v-if="row.months === 12" class="product-badge">Лучшая цена</div>

              <div class="product-main-info">
                <span class="product-duration">
                  {{ formatPeriod(row.months) }}
                </span>
                <span class="product-name-muted">{{ row.name }}</span>
              </div>

              <div class="product-price-block">
                <span class="price-amount">{{ row.price }} ₽</span>
                <span v-if="row.months > 1" class="price-calc-hint">
                  (~{{ Math.round(row.price / row.months) }} ₽/мес)
                </span>
              </div>

              <AppActionButton
                variant="primary"
                block
                :disabled="payingMonths != null"
                @click="startCheckout(row.months)"
              >
                <template v-if="payingMonths === row.months">Переход к оплате…</template>
                <template v-else>Оплатить</template>
              </AppActionButton>
            </div>
          </div>
        </section>
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

.stack {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  width: 100%;
  min-width: 0;
}

.card {
  min-width: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 16px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.25rem 1.35rem;
}

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
  line-height: 1.45;
  color: var(--muted);
}

.tariffs-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

@media (min-width: 420px) {
  .tariffs-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.product-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow: hidden;
}

.product-card--popular {
  border-color: rgba(var(--accent-rgb, 59, 130, 246), 0.25);
  background: linear-gradient(
    to bottom right,
    var(--card-bg),
    var(--surface-glass, rgba(255, 255, 255, 0.01))
  );
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

.product-main-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.product-duration {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-h);
}

.product-name-muted {
  font-size: 0.82rem;
  color: var(--muted);
}

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
}

.price-calc-hint {
  font-size: 0.78rem;
  color: var(--accent);
  font-weight: 500;
}

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
  to {
    transform: rotate(360deg);
  }
}

.pay-empty {
  text-align: center;
  padding: 2rem 1rem;
}

.err {
  color: var(--danger);
  text-align: center;
}
</style>
