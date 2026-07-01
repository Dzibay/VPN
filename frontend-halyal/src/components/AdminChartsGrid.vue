<script setup>
defineProps({
  ariaLabel: { type: String, default: 'Графики' },
})
</script>

<template>
  <section class="admin-charts-grid" :aria-label="ariaLabel">
    <slot />
  </section>
</template>
