<script setup>
/**
 * Единая колонка контента: max-width из :root (--page-content-max),
 * отступы и safe-area. Слот #header — опциональная шапка страницы над основным блоком.
 */
defineProps({
  /** Корневой тег (например main для страницы оплаты) */
  as: {
    type: String,
    default: 'div',
  },
  /** Чуть меньше верхний padding (например /cabinet/pay) */
  compactTop: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <component
    :is="as"
    class="site-page-layout"
    :class="{ 'site-page-layout--compact-top': compactTop }"
  >
    <div class="site-page-layout__inner">
      <div
        v-if="$slots.header"
        class="site-page-layout__header"
      >
        <slot name="header" />
      </div>
      <div class="site-page-layout__body">
        <slot />
      </div>
    </div>
  </component>
</template>

<style scoped>
.site-page-layout {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

.site-page-layout__inner {
  width: 100%;
  max-width: min(var(--page-content-max, 26rem), 100%);
  min-width: 0;
  margin-inline: auto;
  box-sizing: border-box;
  padding: var(--page-content-pad-block-start, 1.75rem)
    max(1rem, env(safe-area-inset-left, 0px))
    var(--page-content-pad-block-end, 2.5rem)
    max(1rem, env(safe-area-inset-right, 0px));
}

.site-page-layout--compact-top .site-page-layout__inner {
  padding-top: var(--page-content-pad-block-start-compact, 1.5rem);
}

.site-page-layout__header:empty {
  display: none;
}

.site-page-layout__body {
  min-width: 0;
}
</style>
