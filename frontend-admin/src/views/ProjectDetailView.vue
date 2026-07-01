<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client.js'
import { getStaffProfile } from '../auth/staffSession.js'

const props = defineProps({ id: [Number, String] })

const project = ref(null)
const loading = ref(false)
const error = ref(null)
const saving = ref(false)
const editable = ref({})
const jsonErrors = ref({}) // key -> строка с текстом ошибки парсинга

const canEdit = computed(() => getStaffProfile()?.role === 'super_admin')

// Секции полей (label, key, тип, hint). Тип: text, secret, checkbox, number,
// number-int (nullable), multiline (для JSON), array-csv (extra_domains через запятую).
// key с точкой (например smtp_settings.host) собирается обратно в JSON-объект.
const sections = [
  {
    title: 'Идентификация',
    fields: [
      { key: 'slug', label: 'Slug', type: 'text', required: true,
        hint: 'Уникальный, латиница, в URL webhook’ов и админ-селектора.' },
      { key: 'name', label: 'Название', type: 'text', required: true },
      { key: 'is_active', label: 'Активен', type: 'checkbox',
        hint: 'Неактивный проект не резолвится по домену/секрету, но остаётся в БД.' },
    ],
  },
  {
    title: 'Домены',
    fields: [
      { key: 'primary_domain', label: 'Основной домен', type: 'text', required: true,
        hint: 'Резолвинг проекта по Host запроса (без схемы и порта).' },
      { key: 'extra_domains', label: 'Extra domains', type: 'array-csv',
        hint: 'Alias/зеркала через запятую. Каждый резолвится в этот проект.' },
    ],
  },
  {
    title: 'Telegram-бот',
    fields: [
      { key: 'telegram_bot_username', label: 'Bot username', type: 'text',
        hint: 'Без @, для ссылок вида t.me/<username>.' },
      { key: 'telegram_bot_api_secret', label: 'Bot API secret', type: 'secret',
        hint: 'Заголовок X-Telegram-Bot-Secret. Должен совпадать с секретом на стороне бота.' },
      { key: 'support_telegram_username', label: 'Support TG username', type: 'text' },
      { key: 'support_email', label: 'Support email', type: 'text' },
    ],
  },
  {
    title: 'Платёжные системы',
    fields: [
      { key: 'tribute_api_key', label: 'Tribute API key', type: 'secret',
        hint: 'Оставить пустым — fallback на глобальный settings.tribute_api_key (если проект #1).' },
      { key: 'yookassa_shop_id', label: 'YooKassa shop_id', type: 'text' },
      { key: 'yookassa_secret_key', label: 'YooKassa secret_key', type: 'secret' },
      { key: 'yookassa_return_url', label: 'YooKassa return URL', type: 'text',
        hint: 'Например: https://<domain>/cabinet/pay/return' },
    ],
  },
  {
    title: 'SMTP',
    fields: [
      { key: 'smtp_settings.host', label: 'SMTP host', type: 'text' },
      { key: 'smtp_settings.port', label: 'SMTP port', type: 'number-int',
        hint: 'Обычно 587 для STARTTLS или 465 для SSL.' },
      { key: 'smtp_settings.username', label: 'SMTP username', type: 'text' },
      { key: 'smtp_settings.password', label: 'SMTP password', type: 'secret' },
      { key: 'smtp_settings.from_email', label: 'From email', type: 'text' },
      { key: 'smtp_settings.from_name', label: 'From name', type: 'text' },
      { key: 'smtp_settings.use_tls', label: 'Use STARTTLS', type: 'checkbox' },
      { key: 'smtp_settings.use_ssl', label: 'Use SSL', type: 'checkbox' },
    ],
  },
  {
    title: 'Реферальная политика',
    fields: [
      { key: 'referral_bonus_days_per_paid_month', label: 'Дней бонуса на 1 оплаченный месяц', type: 'number-int' },
      { key: 'referral_fixed_first_payment_bonus_rub', label: 'Фикс. бонус за первый платёж (руб)', type: 'number-int' },
      { key: 'referral_bonus_policy', label: 'Policy (текст)', type: 'text',
        hint: 'Ключ политики (fixed_days, percent_of_amount, disabled …).' },
    ],
  },
  {
    title: 'Брендинг подписки',
    fields: [
      { key: 'happ_provider_id', label: 'Happ provider ID', type: 'text',
        hint: 'Используется для YAML-подписки клиента.' },
      { key: 'subscription_sub_expire_banner', label: 'Баннер «подписка истекает» (JSON)', type: 'multiline',
        hint: 'Payload YAML-баннера. Пусто → нет баннера.' },
      { key: 'subscription_sub_info_banner', label: 'Info-баннер (JSON)', type: 'multiline' },
      { key: 'brand', label: 'Брендинг (JSON)', type: 'multiline',
        hint: 'Пример: {"brand_name":"Acme VPN"}. Используется в текстах бота и YAML.' },
    ],
  },
]

const allEditableKeys = sections.flatMap((s) => s.fields.map((f) => f.key))
const nestedJsonRoots = ['smtp_settings']

function getFieldValue(row, key) {
  if (!key.includes('.')) return row[key]
  return key.split('.').reduce((acc, part) => (acc == null ? undefined : acc[part]), row)
}

function setNestedValue(target, key, value) {
  const parts = key.split('.')
  const root = parts.shift()
  if (!root) return
  let cursor = target[root]
  if (cursor == null || typeof cursor !== 'object' || Array.isArray(cursor)) {
    cursor = {}
    target[root] = cursor
  }
  for (let i = 0; i < parts.length - 1; i += 1) {
    const part = parts[i]
    if (cursor[part] == null || typeof cursor[part] !== 'object') {
      cursor[part] = {}
    }
    cursor = cursor[part]
  }
  cursor[parts[parts.length - 1]] = value
}

function objectHasMeaningfulValue(value) {
  if (value == null || typeof value !== 'object') return false
  return Object.values(value).some((v) => {
    if (v == null || v === '') return false
    if (typeof v === 'object') return objectHasMeaningfulValue(v)
    if (typeof v === 'boolean') return v
    return true
  })
}

function toEditable(row) {
  const draft = {}
  for (const key of allEditableKeys) {
    const v = getFieldValue(row, key)
    const meta = _fieldMeta(key)
    if (meta.type === 'array-csv') {
      draft[key] = Array.isArray(v) ? v.join(', ') : ''
    } else if (meta.type === 'multiline') {
      draft[key] = v == null ? '' : JSON.stringify(v, null, 2)
    } else if (meta.type === 'checkbox') {
      draft[key] = Boolean(v)
    } else if (v == null) {
      draft[key] = ''
    } else {
      draft[key] = v
    }
  }
  return draft
}

function _fieldMeta(key) {
  for (const s of sections) {
    const f = s.fields.find((x) => x.key === key)
    if (f) return f
  }
  return { key, type: 'text' }
}

function buildPatch() {
  const patch = {}
  jsonErrors.value = {}
  for (const key of allEditableKeys) {
    const meta = _fieldMeta(key)
    const raw = editable.value[key]
    let value
    if (meta.type === 'array-csv') {
      value = String(raw || '')
        .split(',').map((s) => s.trim()).filter(Boolean)
    } else if (meta.type === 'multiline') {
      const s = String(raw || '').trim()
      if (!s) {
        value = null
      } else {
        try {
          value = JSON.parse(s)
        } catch (e) {
          jsonErrors.value[key] = 'Невалидный JSON: ' + e.message
        }
      }
    } else if (meta.type === 'checkbox') {
      value = Boolean(raw)
    } else if (meta.type === 'number-int') {
      if (raw === '' || raw === null || raw === undefined) {
        value = null
      } else {
        const n = Number(raw)
        value = Number.isFinite(n) ? Math.trunc(n) : null
      }
    } else {
      value = raw === '' ? null : raw
    }
    if (key.includes('.')) setNestedValue(patch, key, value)
    else patch[key] = value
  }
  for (const root of nestedJsonRoots) {
    if (root in patch && !objectHasMeaningfulValue(patch[root])) {
      patch[root] = null
    }
  }
  return patch
}

async function load() {
  loading.value = true
  error.value = null
  try {
    project.value = await apiFetch(`/api/admin/projects/${props.id}`, { withProject: false })
    editable.value = toEditable(project.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const patch = buildPatch()
    if (Object.keys(jsonErrors.value).length) {
      alert('Есть ошибки в JSON-полях: ' + Object.keys(jsonErrors.value).join(', '))
      return
    }
    await apiFetch(`/api/admin/projects/${props.id}`, {
      method: 'PATCH', withProject: false, body: patch,
    })
    await load()
    alert('Проект сохранён')
  } catch (e) {
    alert(e.message)
  } finally {
    saving.value = false
  }
}

watch(() => props.id, load)
onMounted(load)
</script>

<template>
  <section class="stack">
    <div class="card" v-if="project">
      <div class="row" style="justify-content: space-between; align-items: baseline;">
        <h2 style="margin: 0;">
          #{{ project.id }} — {{ project.name }}
          <span class="pill" :class="{ off: !project.is_active }">
            {{ project.is_active ? 'active' : 'inactive' }}
          </span>
        </h2>
        <button v-if="canEdit" class="primary" @click="save" :disabled="saving">
          {{ saving ? 'Сохраняем…' : 'Сохранить все изменения' }}
        </button>
      </div>
      <p style="color: var(--text-muted); font-size: 13px;">
        Создан: {{ project.created_at || '—' }}
      </p>

      <form class="stack" @submit.prevent="save">
        <section v-for="s in sections" :key="s.title" class="section">
          <h3>{{ s.title }}</h3>
          <div class="fields">
            <label
              v-for="f in s.fields"
              :key="f.key"
              :class="{ error: jsonErrors[f.key] }"
            >
              <span class="lbl">
                {{ f.label }}
                <em v-if="f.required">*</em>
                <code>{{ f.key }}</code>
              </span>
              <template v-if="f.type === 'checkbox'">
                <input
                  type="checkbox"
                  v-model="editable[f.key]"
                  :disabled="!canEdit"
                />
              </template>
              <template v-else-if="f.type === 'multiline'">
                <textarea
                  v-model="editable[f.key]"
                  :disabled="!canEdit"
                  rows="4"
                  spellcheck="false"
                ></textarea>
              </template>
              <template v-else-if="f.type === 'secret'">
                <input
                  type="password"
                  v-model="editable[f.key]"
                  :disabled="!canEdit"
                  autocomplete="off"
                />
              </template>
              <template v-else-if="f.type === 'number-int'">
                <input
                  type="number"
                  step="1"
                  v-model="editable[f.key]"
                  :disabled="!canEdit"
                />
              </template>
              <template v-else>
                <input
                  type="text"
                  v-model="editable[f.key]"
                  :disabled="!canEdit"
                  autocomplete="off"
                />
              </template>
              <small v-if="jsonErrors[f.key]" class="err">
                {{ jsonErrors[f.key] }}
              </small>
              <small v-else-if="f.hint" class="hint">{{ f.hint }}</small>
            </label>
          </div>
        </section>

        <div v-if="canEdit" class="row" style="gap: 12px;">
          <button type="submit" class="primary" :disabled="saving">
            {{ saving ? 'Сохраняем…' : 'Сохранить все изменения' }}
          </button>
          <router-link :to="`/projects/${id}/tariffs`">Перейти к тарифам →</router-link>
        </div>
      </form>
    </div>

    <p v-if="loading">Загрузка…</p>
    <p v-if="error" style="color: var(--danger);">{{ error }}</p>
  </section>
</template>

<style scoped>
.section {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.section h3 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: var(--accent-2);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
label.error input,
label.error textarea {
  border-color: var(--danger);
}
.lbl {
  font-size: 13px;
  color: var(--text);
}
.lbl em {
  color: var(--danger);
  font-style: normal;
}
.lbl code {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--panel-2);
  color: var(--text-muted);
  font-size: 11px;
}
.hint {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.4;
}
.err {
  color: var(--danger);
  font-size: 12px;
}
textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  min-height: 100px;
  resize: vertical;
}
.pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--success);
  color: #fff;
  margin-left: 8px;
  vertical-align: middle;
  text-transform: uppercase;
}
.pill.off {
  background: var(--panel-2);
  color: var(--text-muted);
}
input[type='checkbox'] {
  width: auto;
  margin-top: 4px;
}
@media (max-width: 720px) {
  .fields { grid-template-columns: 1fr; }
}
</style>
