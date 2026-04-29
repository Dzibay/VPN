<script setup>
/**
 * Единая оболочка страниц админки: базовая ширина и отступы.
 * Узкие страницы (кабинет, логин, регистрация) этим компонентом не оборачиваются.
 */
</script>

<template>
  <div class="admin-page-shell">
    <slot />
  </div>
</template>

<style scoped>
.admin-page-shell {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.25rem 1rem 2.5rem;
  box-sizing: border-box;
}
</style>
