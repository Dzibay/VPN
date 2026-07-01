<script setup>
/**
 * Две колонки показателей внутри StatWidget (dt/dd).
 * @type {{ items: Array<{ label: string, value: string | number }> }}
 */
defineProps({
  items: { type: Array, required: true },
})
</script>

<template>
  <dl class="stat-widget-split">
    <div v-for="(item, idx) in items" :key="idx">
      <dt>{{ item.label }}</dt>
      <dd>{{ item.value }}</dd>
    </div>
  </dl>
</template>
