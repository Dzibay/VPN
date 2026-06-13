<script setup>
import { RouterLink } from 'vue-router'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from '../../auth/credentialsValidation.js'

defineProps({
  showPasswordConfirm: {
    type: Boolean,
    default: false,
  },
  showLegalConsent: {
    type: Boolean,
    default: false,
  },
  passwordAutocomplete: {
    type: String,
    default: 'new-password',
  },
  passwordMinLength: {
    type: Number,
    default: PASSWORD_MIN_LENGTH,
  },
  passwordLabel: {
    type: String,
    default: 'Пароль',
  },
  passwordConfirmLabel: {
    type: String,
    default: 'Подтверждение пароля',
  },
})

const email = defineModel('email', { type: String, default: '' })
const password = defineModel('password', { type: String, default: '' })
const passwordConfirm = defineModel('passwordConfirm', { type: String, default: '' })
const acceptedLegal = defineModel('acceptedLegal', { type: Boolean, default: false })
</script>

<template>
  <label class="field">
    <span class="label">Email</span>
    <input
      v-model="email"
      class="input"
      type="email"
      name="email"
      autocomplete="email"
      required
    />
  </label>
  <label class="field">
    <span class="label">{{ passwordLabel }}</span>
    <input
      v-model="password"
      class="input"
      type="password"
      name="password"
      :autocomplete="passwordAutocomplete"
      :minlength="passwordMinLength > 0 ? passwordMinLength : undefined"
      :maxlength="PASSWORD_MAX_LENGTH"
      required
    />
  </label>
  <label
    v-if="showPasswordConfirm"
    class="field"
  >
    <span class="label">{{ passwordConfirmLabel }}</span>
    <input
      v-model="passwordConfirm"
      class="input"
      type="password"
      name="password-confirm"
      autocomplete="new-password"
      :minlength="PASSWORD_MIN_LENGTH"
      :maxlength="PASSWORD_MAX_LENGTH"
      required
    />
  </label>
  <label
    v-if="showLegalConsent"
    class="consent"
  >
    <input
      v-model="acceptedLegal"
      class="consent-input"
      type="checkbox"
      name="legal-consent"
      required
    />
    <span class="consent-text">
      Я принимаю
      <RouterLink to="/terms" target="_blank">публичную оферту</RouterLink>,
      <RouterLink to="/privacy" target="_blank">политику конфиденциальности</RouterLink>
      и даю
      <RouterLink to="/consent" target="_blank">политику обработки персональных данных</RouterLink>
    </span>
  </label>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  text-align: left;
}

.label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--muted);
}

.input {
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  color: var(--text-h);
  font: inherit;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.consent {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  text-align: left;
  cursor: pointer;
}

.consent-input {
  flex-shrink: 0;
  width: 1.05rem;
  height: 1.05rem;
  margin-top: 0.2rem;
  accent-color: var(--accent);
}

.consent-text {
  font-size: 0.85rem;
  line-height: 1.45;
  color: var(--muted);
}

.consent-text a {
  color: var(--accent);
  font-weight: 600;
  text-decoration: none;
}

.consent-text a:hover {
  text-decoration: underline;
}
</style>
