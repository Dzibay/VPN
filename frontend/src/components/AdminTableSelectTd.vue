<script setup>
defineProps({
  active: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  rowId: { type: [Number, String], required: true },
  disabled: { type: Boolean, default: false },
})

defineEmits(['toggle'])
</script>

<template>
  <td
    class="admin-bulk-col td-select"
    :class="{ 'admin-bulk-col--visible': active }"
    @click.stop="$emit('toggle')"
  >
    <div class="admin-bulk-col__inner">
      <label class="admin-bulk-check" @click.stop>
        <input
          type="checkbox"
          class="admin-bulk-check__input"
          :checked="selected"
          :disabled="disabled || !active"
          tabindex="-1"
          @change="$emit('toggle')"
        />
        <span
          class="admin-bulk-check__box"
          :class="{ 'admin-bulk-check__box--on': selected && active }"
          aria-hidden="true"
        />
      </label>
    </div>
  </td>
</template>
