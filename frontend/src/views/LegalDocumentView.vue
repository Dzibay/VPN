<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import SitePageLayout from '../components/SitePageLayout.vue'
import { getLegalDocument } from '../content/legal.js'

const route = useRoute()

const doc = computed(() => getLegalDocument(route.meta.legalDoc))
</script>

<template>
  <SitePageLayout class="legal-page">
    <template #header>
      <header class="head">
        <h1>{{ doc?.title ?? 'Документ' }}</h1>
        <p v-if="doc?.subtitle" class="sub">{{ doc.subtitle }}</p>
      </header>
    </template>

    <CabinetBackLink to="/" label="На главную" />

    <article v-if="doc" class="card card-pad doc">
      <p v-if="doc.intro" class="intro">{{ doc.intro }}</p>

      <template v-for="(p, i) in doc.paragraphs ?? []" :key="`p-${i}`">
        <p>{{ p }}</p>
      </template>

      <ul v-if="doc.list?.length" class="list">
        <li v-for="(item, i) in doc.list" :key="`l-${i}`">{{ item }}</li>
      </ul>

      <section
        v-for="(section, si) in doc.sections ?? []"
        :key="`s-${si}`"
        class="section"
      >
        <h2>{{ section.heading }}</h2>
        <p v-for="(p, pi) in section.paragraphs ?? []" :key="`sp-${si}-${pi}`">
          {{ p }}
        </p>
        <ul v-if="section.list?.length" class="list">
          <li v-for="(item, li) in section.list" :key="`sl-${si}-${li}`">
            {{ item }}
          </li>
        </ul>
        <p
          v-for="(p, pi) in section.paragraphsAfter ?? []"
          :key="`spa-${si}-${pi}`"
        >
          {{ p }}
        </p>
        <ul v-if="section.listAfter?.length" class="list">
          <li v-for="(item, li) in section.listAfter" :key="`sla-${si}-${li}`">
            {{ item }}
          </li>
        </ul>
      </section>

      <p v-if="doc.outro" class="outro">{{ doc.outro }}</p>
    </article>
  </SitePageLayout>
</template>

<style scoped>
.legal-page {
  --page-content-max: 44rem;
}

.legal-page :deep(.site-page-layout__body) {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

h1 {
  font-size: clamp(1.35rem, 3vw, 1.65rem);
  margin: 0 0 0.45rem;
  line-height: 1.25;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.45;
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
}

.card-pad {
  padding: 1.35rem 1.4rem;
}

.doc {
  font-size: 0.95rem;
  line-height: 1.65;
  color: var(--text);
}

.doc :is(p, ul) {
  margin: 0 0 0.85rem;
}

.intro {
  color: var(--text-h);
}

.section {
  margin-top: 1.35rem;
}

.section h2 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-h);
  margin: 0 0 0.65rem;
}

.list {
  padding-left: 1.25rem;
}

.list li {
  margin-bottom: 0.35rem;
}

.outro {
  margin-top: 1rem;
  white-space: pre-line;
}
</style>
