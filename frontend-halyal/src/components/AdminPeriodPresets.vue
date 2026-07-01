<script setup>
/**
 * Кнопки выбора календарного периода (МСК).
 * variant: pills — отдельные кнопки (Сводка); segmented — сегмент (Финансы).
 */
defineProps({
  presets: { type: Array, required: true },
  modelValue: { type: String, required: true },
  ariaLabel: { type: String, default: 'Период' },
  variant: { type: String, default: 'pills' },
  customFrom: { type: String, default: '' },
  customTo: { type: String, default: '' },
  stacked: { type: Boolean, default: false },
})

defineEmits(['update:modelValue', 'update:customFrom', 'update:customTo'])
</script>

<template>
  <div
    class="admin-period-row"
    :class="{
      'admin-period-row--spaced': variant === 'segmented',
      'admin-period-row--stacked': stacked,
    }"
  >
    <div
      class="admin-period-presets"
      :class="{ 'admin-period-presets--segmented': variant === 'segmented' }"
      role="group"
      :aria-label="ariaLabel"
    >
      <button
        v-for="p in presets"
        :key="p.key"
        type="button"
        class="admin-period-btn"
        :class="{ 'admin-period-btn--active': modelValue === p.key }"
        @click="$emit('update:modelValue', p.key)"
      >
        {{ p.label }}
      </button>
    </div>
    <div v-if="modelValue === 'custom'" class="admin-period-custom">
      <input
        :value="customFrom"
        type="date"
        class="admin-period-date"
        aria-label="С"
        @input="$emit('update:customFrom', $event.target.value)"
      />
      <span class="admin-period-sep">—</span>
      <input
        :value="customTo"
        type="date"
        class="admin-period-date"
        aria-label="По"
        @input="$emit('update:customTo', $event.target.value)"
      />
    </div>
  </div>
</template>
