<script setup>
defineProps({
  /** @type {import('vue').PropType<{ title: string, sections: Array<{ heading: string, paragraphs: string[] }> }>} */
  article: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <section
    id="seo-article"
    class="section section-seo-article"
    aria-labelledby="seo-article-heading"
  >
    <div class="section-inner section-seo-article__inner">
      <h2
        id="seo-article-heading"
        class="section-seo-article__title"
      >
        {{ article.title }}
      </h2>

      <div class="section-seo-article__body">
        <article
          v-for="(block, i) in article.sections"
          :key="i"
          class="seo-article-block"
        >
          <h3 class="seo-article-block__heading">
            {{ block.heading }}
          </h3>
          <p
            v-for="(paragraph, j) in block.paragraphs"
            :key="j"
            class="seo-article-block__p"
          >
            {{ paragraph }}
          </p>
        </article>
      </div>
    </div>
  </section>
</template>
