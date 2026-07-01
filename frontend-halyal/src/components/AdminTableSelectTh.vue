<script setup>
defineProps({
  active: { type: Boolean, default: false },
  checked: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  indeterminate: { type: Boolean, default: false },
})

defineEmits(['toggle'])
</script>

<template>
  <th
    class="admin-bulk-col th-select"
    :class="{ 'admin-bulk-col--visible': active }"
    scope="col"
    aria-label="Выбрать все на странице"
  >
    <div class="admin-bulk-col__inner">
      <label class="admin-bulk-check" @click.stop>
        <input
          type="checkbox"
          class="admin-bulk-check__input"
          :checked="checked"
          :disabled="disabled || !active"
          :indeterminate.prop="indeterminate"
          @change="$emit('toggle')"
        />
        <span class="admin-bulk-check__box" aria-hidden="true" />
      </label>
    </div>
  </th>
</template>
