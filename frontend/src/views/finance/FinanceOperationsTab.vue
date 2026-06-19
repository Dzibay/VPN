<script setup>
import { computed, onMounted, ref } from 'vue'
import AdminTableWrap from '../../components/AdminTableWrap.vue'
import AppRefreshButton from '../../components/AppRefreshButton.vue'
import { fetchJson } from '../../api/client.js'
import { mskTodayIso } from '../../utils/mskDate.js'

const loading = ref(false)
const error = ref(null)

const accounts = ref([])
const payables = ref([])
const refunds = ref([])
const withdrawals = ref([])
const transactions = ref([])

const activeAccounts = computed(() => accounts.value.filter((a) => a.active))

const accountForm = ref({
  name: '',
  kind: 'bank',
  opening_balance: '0',
  opened_on: mskTodayIso(),
  is_default: false,
})
const payableForm = ref({
  counterparty_name: '',
  title: '',
  amount: '',
  incurred_on: mskTodayIso(),
  due_on: '',
  note: '',
})
const refundForm = ref({
  payment_id: '',
  user_id: '',
  account_id: '',
  refunded_on: mskTodayIso(),
  amount: '',
  net_amount: '',
  reason: '',
})
const withdrawalForm = ref({
  account_id: '',
  withdrawn_on: mskTodayIso(),
  amount: '',
  recipient_name: '',
  note: '',
})
const transactionForm = ref({
  account_id: '',
  occurred_on: mskTodayIso(),
  amount: '',
  title: '',
  note: '',
})
const payFormById = ref({})

function num(v) {
  const n = Number(String(v ?? '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}
function money(v) {
  return num(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtDate(d) {
  if (!d) return '—'
  const dt = new Date(`${String(d).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(dt.getTime())) return String(d)
  return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
}
function accountLabel(id) {
  if (id == null || id === '') return 'Дефолтный счет'
  return accounts.value.find((a) => Number(a.id) === Number(id))?.name ?? `#${id}`
}
function statusLabel(status) {
  const map = {
    open: 'открыт',
    partial: 'частично',
    paid: 'оплачен',
    cancelled: 'отменен',
    pending: 'ожидает',
    succeeded: 'проведен',
    failed: 'ошибка',
    planned: 'запланирован',
  }
  return map[status] || status
}

async function loadAll() {
  loading.value = true
  error.value = null
  try {
    const [acc, pay, ref, wd, tx] = await Promise.all([
      fetchJson('/api/admin/accounting/cash-accounts'),
      fetchJson('/api/admin/accounting/payables?limit=500&offset=0'),
      fetchJson('/api/admin/accounting/refunds?limit=500&offset=0'),
      fetchJson('/api/admin/accounting/profit-withdrawals?limit=500&offset=0'),
      fetchJson('/api/admin/accounting/cash-transactions?limit=500&offset=0'),
    ])
    accounts.value = Array.isArray(acc?.items) ? acc.items : []
    payables.value = Array.isArray(pay?.items) ? pay.items : []
    for (const p of payables.value) {
      if (!payFormById.value[p.id]) {
        payFormById.value[p.id] = { amount: '', account_id: '', paid_on: mskTodayIso(), note: '' }
      }
    }
    refunds.value = Array.isArray(ref?.items) ? ref.items : []
    withdrawals.value = Array.isArray(wd?.items) ? wd.items : []
    transactions.value = Array.isArray(tx?.items) ? tx.items : []
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function submitAccount() {
  const f = accountForm.value
  await fetchJson('/api/admin/accounting/cash-accounts', {
    method: 'POST',
    body: JSON.stringify({
      name: f.name.trim(),
      kind: f.kind,
      currency: 'RUB',
      opening_balance: num(f.opening_balance),
      opened_on: f.opened_on,
      active: true,
      is_default: Boolean(f.is_default),
    }),
  })
  accountForm.value = { name: '', kind: 'bank', opening_balance: '0', opened_on: mskTodayIso(), is_default: false }
  await loadAll()
}

async function submitPayable() {
  const f = payableForm.value
  await fetchJson('/api/admin/accounting/payables', {
    method: 'POST',
    body: JSON.stringify({
      counterparty_name: f.counterparty_name.trim(),
      title: f.title.trim(),
      amount: num(f.amount),
      source_type: 'manual',
      incurred_on: f.incurred_on,
      due_on: f.due_on || null,
      note: f.note.trim() || null,
    }),
  })
  payableForm.value = { counterparty_name: '', title: '', amount: '', incurred_on: mskTodayIso(), due_on: '', note: '' }
  await loadAll()
}

async function submitPayablePayment(row) {
  const f = payFormById.value[row.id] || {}
  await fetchJson(`/api/admin/accounting/payables/${row.id}/payments`, {
    method: 'POST',
    body: JSON.stringify({
      amount: num(f.amount),
      paid_on: f.paid_on || mskTodayIso(),
      account_id: f.account_id ? Number(f.account_id) : null,
      note: f.note || null,
    }),
  })
  payFormById.value[row.id] = {}
  await loadAll()
}

async function submitRefund() {
  const f = refundForm.value
  await fetchJson('/api/admin/accounting/refunds', {
    method: 'POST',
    body: JSON.stringify({
      payment_id: f.payment_id ? Number(f.payment_id) : null,
      user_id: f.user_id ? Number(f.user_id) : null,
      account_id: f.account_id ? Number(f.account_id) : null,
      refunded_on: f.refunded_on,
      amount: num(f.amount),
      net_amount: f.net_amount ? num(f.net_amount) : null,
      status: 'succeeded',
      reason: f.reason.trim() || null,
    }),
  })
  refundForm.value = { payment_id: '', user_id: '', account_id: '', refunded_on: mskTodayIso(), amount: '', net_amount: '', reason: '' }
  await loadAll()
}

async function submitWithdrawal() {
  const f = withdrawalForm.value
  await fetchJson('/api/admin/accounting/profit-withdrawals', {
    method: 'POST',
    body: JSON.stringify({
      account_id: f.account_id ? Number(f.account_id) : null,
      withdrawn_on: f.withdrawn_on,
      amount: num(f.amount),
      recipient_name: f.recipient_name.trim(),
      status: 'succeeded',
      note: f.note.trim() || null,
    }),
  })
  withdrawalForm.value = { account_id: '', withdrawn_on: mskTodayIso(), amount: '', recipient_name: '', note: '' }
  await loadAll()
}

async function submitTransaction() {
  const f = transactionForm.value
  await fetchJson('/api/admin/accounting/cash-transactions', {
    method: 'POST',
    body: JSON.stringify({
      account_id: Number(f.account_id),
      occurred_on: f.occurred_on,
      amount: num(f.amount),
      kind: 'adjustment',
      title: f.title.trim(),
      note: f.note.trim() || null,
    }),
  })
  transactionForm.value = { account_id: '', occurred_on: mskTodayIso(), amount: '', title: '', note: '' }
  await loadAll()
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <p v-if="error" class="msg-err">{{ error }}</p>

  <div class="ops-head">
    <AppRefreshButton :busy="loading" @click="loadAll" />
  </div>

  <section class="block">
    <h2 class="section-heading">Счета</h2>
    <form class="inline-form" @submit.prevent="submitAccount">
      <input v-model="accountForm.name" class="input-like" required placeholder="Название счета" />
      <select v-model="accountForm.kind" class="input-like">
        <option value="bank">Расчетник</option>
        <option value="psp">Платежная система</option>
        <option value="cash">Наличные</option>
        <option value="person">Личный счет</option>
        <option value="other">Другое</option>
      </select>
      <input v-model="accountForm.opening_balance" class="input-like" inputmode="decimal" placeholder="Начальный остаток" />
      <input v-model="accountForm.opened_on" class="input-like" type="date" />
      <label class="check-inline"><input v-model="accountForm.is_default" type="checkbox" /> Дефолтный</label>
      <button class="btn-primary" type="submit">Добавить счет</button>
    </form>
    <AdminTableWrap aria-label="Счета">
      <table class="admin-table">
        <thead><tr><th>Счет</th><th>Тип</th><th class="num">Начальный остаток</th><th>Статус</th></tr></thead>
        <tbody>
          <tr v-for="a in accounts" :key="a.id">
            <td>{{ a.name }} <span v-if="a.is_default" class="muted">· default</span></td>
            <td>{{ a.kind }}</td>
            <td class="num">{{ money(a.opening_balance) }} ₽</td>
            <td>{{ a.active ? 'активен' : 'архив' }}</td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </section>

  <section class="block">
    <h2 class="section-heading">Долги организации</h2>
    <form class="inline-form" @submit.prevent="submitPayable">
      <input v-model="payableForm.counterparty_name" class="input-like" required placeholder="Кому должны" />
      <input v-model="payableForm.title" class="input-like" required placeholder="За что" />
      <input v-model="payableForm.amount" class="input-like" required inputmode="decimal" placeholder="Сумма" />
      <input v-model="payableForm.incurred_on" class="input-like" type="date" />
      <input v-model="payableForm.due_on" class="input-like" type="date" title="Срок оплаты" />
      <button class="btn-primary" type="submit">Начислить долг</button>
    </form>
    <AdminTableWrap aria-label="Долги">
      <table class="admin-table">
        <thead><tr><th>Кому</th><th>За что</th><th class="num">Долг</th><th class="num">Оплачено</th><th>Статус</th><th>Выплата</th></tr></thead>
        <tbody>
          <tr v-for="p in payables" :key="p.id">
            <td>{{ p.counterparty_name }}</td>
            <td>{{ p.title }}<span class="muted small"> · {{ fmtDate(p.incurred_on) }}</span></td>
            <td class="num">{{ money(p.amount) }} ₽</td>
            <td class="num">{{ money(p.paid_amount) }} ₽</td>
            <td>{{ statusLabel(p.status) }}</td>
            <td>
              <form v-if="p.status !== 'paid' && p.status !== 'cancelled'" class="pay-form" @submit.prevent="submitPayablePayment(p)">
                <input v-model="payFormById[p.id].amount" class="input-like mini" inputmode="decimal" placeholder="Сумма" />
                <select v-model="payFormById[p.id].account_id" class="input-like mini">
                  <option value="">Счет</option>
                  <option v-for="a in activeAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
                </select>
                <button class="btn-secondary btn-mini" type="submit">Выплатить</button>
              </form>
            </td>
          </tr>
        </tbody>
      </table>
    </AdminTableWrap>
  </section>

  <section class="grid-2">
    <div class="block">
      <h2 class="section-heading">Возвраты</h2>
      <form class="stack-form" @submit.prevent="submitRefund">
        <input v-model="refundForm.payment_id" class="input-like" inputmode="numeric" placeholder="ID платежа (если есть)" />
        <input v-model="refundForm.user_id" class="input-like" inputmode="numeric" placeholder="ID клиента (если есть)" />
        <select v-model="refundForm.account_id" class="input-like">
          <option value="">Дефолтный счет</option>
          <option v-for="a in activeAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <input v-model="refundForm.refunded_on" class="input-like" type="date" />
        <input v-model="refundForm.amount" class="input-like" required inputmode="decimal" placeholder="Валовая сумма" />
        <input v-model="refundForm.net_amount" class="input-like" inputmode="decimal" placeholder="Net сумма (если отличается)" />
        <input v-model="refundForm.reason" class="input-like" placeholder="Причина" />
        <button class="btn-primary" type="submit">Записать возврат</button>
      </form>
      <ul class="simple-list">
        <li v-for="r in refunds" :key="r.id">{{ fmtDate(r.refunded_on) }} · {{ money(r.net_amount) }} ₽ · {{ statusLabel(r.status) }}</li>
      </ul>
    </div>

    <div class="block">
      <h2 class="section-heading">Вывод прибыли</h2>
      <form class="stack-form" @submit.prevent="submitWithdrawal">
        <select v-model="withdrawalForm.account_id" class="input-like">
          <option value="">Дефолтный счет</option>
          <option v-for="a in activeAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <input v-model="withdrawalForm.withdrawn_on" class="input-like" type="date" />
        <input v-model="withdrawalForm.amount" class="input-like" required inputmode="decimal" placeholder="Сумма" />
        <input v-model="withdrawalForm.recipient_name" class="input-like" required placeholder="Получатель" />
        <input v-model="withdrawalForm.note" class="input-like" placeholder="Комментарий" />
        <button class="btn-primary" type="submit">Записать вывод</button>
      </form>
      <ul class="simple-list">
        <li v-for="w in withdrawals" :key="w.id">{{ fmtDate(w.withdrawn_on) }} · {{ money(w.amount) }} ₽ · {{ w.recipient_name }}</li>
      </ul>
    </div>
  </section>

  <section class="block">
    <h2 class="section-heading">Ручные корректировки cash</h2>
    <form class="inline-form" @submit.prevent="submitTransaction">
      <select v-model="transactionForm.account_id" class="input-like" required>
        <option value="">Счет</option>
        <option v-for="a in activeAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
      </select>
      <input v-model="transactionForm.occurred_on" class="input-like" type="date" />
      <input v-model="transactionForm.amount" class="input-like" required inputmode="decimal" placeholder="+/- сумма" />
      <input v-model="transactionForm.title" class="input-like" required placeholder="Основание" />
      <button class="btn-primary" type="submit">Добавить</button>
    </form>
    <ul class="simple-list">
      <li v-for="t in transactions" :key="t.id">{{ fmtDate(t.occurred_on) }} · {{ accountLabel(t.account_id) }} · {{ money(t.amount) }} ₽ · {{ t.title }}</li>
    </ul>
  </section>
</template>

<style scoped>
.msg-err { color: var(--danger); margin-bottom: 0.75rem; }
.muted { color: var(--muted); }
.small { font-size: 0.78rem; }
.ops-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}
.block {
  margin-bottom: 1.6rem;
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: 14px;
  background: var(--surface-glass, var(--surface));
}
.section-heading {
  margin: 0 0 0.75rem;
  font-size: 1.05rem;
  color: var(--text-h);
}
.inline-form,
.pay-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.stack-form {
  display: grid;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.check-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--muted);
  font-size: 0.86rem;
}
.mini {
  max-width: 8rem;
  padding: 0.35rem 0.5rem;
}
.btn-mini {
  padding: 0.35rem 0.6rem;
}
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}
.simple-list {
  margin: 0.5rem 0 0;
  padding-left: 1.1rem;
  color: var(--muted);
  font-size: 0.88rem;
}
@media (max-width: 860px) {
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
</style>
