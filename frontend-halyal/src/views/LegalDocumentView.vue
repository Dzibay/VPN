<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import SitePageLayout from '../components/SitePageLayout.vue'
import { ensureProjectLegalLoaded } from '../composables/useProjectLegal.js'
import {
  LEGAL_FOOTER_LINKS,
  getLegalDocument,
} from '../content/legal.js'
import { linkifyText } from '../utils/linkifyText.js'

const route = useRoute()
const legalReady = ref(false)

onMounted(async () => {
  await ensureProjectLegalLoaded()
  legalReady.value = true
})

const doc = computed(() => (
  legalReady.value ? getLegalDocument(route.meta.legalDoc) : null
))

const toc = computed(() =>
  (doc.value?.sections ?? []).map((section, index) => ({
    id: `section-${index}`,
    label: section.heading,
  })),
)

const otherDocs = computed(() =>
  LEGAL_FOOTER_LINKS.filter((link) => link.to !== route.path),
)

const linkify = linkifyText
</script>

<template>
  <SitePageLayout class="legal-page">
    <template #header>
      <header class="head">
        <p
          v-if="doc?.badge"
          class="badge"
        >
          {{ doc.badge }}
        </p>
        <h1>{{ doc?.title ?? 'Документ' }}</h1>
        <p
          v-if="doc?.subtitle"
          class="sub"
        >
          {{ doc.subtitle }}
        </p>
        <p
          v-if="doc?.effectiveDate"
          class="meta"
        >
          Редакция от {{ doc.effectiveDate }}
        </p>
      </header>
    </template>

    <CabinetBackLink
      to="/"
      label="На главную"
    />

    <p
      v-if="!legalReady"
      class="legal-loading"
    >
      Загрузка документа…
    </p>

    <div
      v-else-if="doc"
      class="legal-layout"
    >
      <nav
        v-if="toc.length > 1"
        class="toc card"
        aria-label="Содержание документа"
      >
        <p class="toc__title">
          Содержание
        </p>
        <ol class="toc__list">
          <li
            v-for="item in toc"
            :key="item.id"
          >
            <a :href="`#${item.id}`">{{ item.label }}</a>
          </li>
        </ol>
      </nav>

      <article class="card card-pad doc">
        <aside
          v-if="doc.disclaimer"
          class="callout callout--disclaimer"
          role="note"
        >
          <p v-html="linkify(doc.disclaimer)" />
        </aside>

        <p
          v-if="doc.intro"
          class="intro"
          v-html="linkify(doc.intro)"
        />

        <template
          v-for="(p, i) in doc.paragraphs ?? []"
          :key="`p-${i}`"
        >
          <p v-html="linkify(p)" />
        </template>

        <ul
          v-if="doc.list?.length"
          class="list"
        >
          <li
            v-for="(item, i) in doc.list"
            :key="`l-${i}`"
            v-html="linkify(item)"
          />
        </ul>

        <section
          v-for="(section, si) in doc.sections ?? []"
          :id="`section-${si}`"
          :key="`s-${si}`"
          class="section"
        >
          <h2>{{ section.heading }}</h2>

          <p
            v-for="(p, pi) in section.paragraphs ?? []"
            :key="`sp-${si}-${pi}`"
            v-html="linkify(p)"
          />

          <ul
            v-if="section.list?.length"
            class="list"
          >
            <li
              v-for="(item, li) in section.list"
              :key="`sl-${si}-${li}`"
              v-html="linkify(item)"
            />
          </ul>

          <div
            v-for="(sub, ssi) in section.subsections ?? []"
            :key="`ss-${si}-${ssi}`"
            class="subsection"
          >
            <h3 v-if="sub.heading">
              {{ sub.heading }}
            </h3>
            <p
              v-for="(p, spi) in sub.paragraphs ?? []"
              :key="`ssp-${si}-${ssi}-${spi}`"
              v-html="linkify(p)"
            />
            <ul
              v-if="sub.list?.length"
              class="list"
            >
              <li
                v-for="(item, sli) in sub.list"
                :key="`ssl-${si}-${ssi}-${sli}`"
                v-html="linkify(item)"
              />
            </ul>
            <aside
              v-if="sub.callout"
              class="callout"
              :class="`callout--${sub.callout.type || 'info'}`"
              role="note"
            >
              <p v-html="linkify(sub.callout.text)" />
            </aside>
          </div>

          <p
            v-for="(p, pi) in section.paragraphsAfter ?? []"
            :key="`spa-${si}-${pi}`"
            v-html="linkify(p)"
          />

          <ul
            v-if="section.listAfter?.length"
            class="list"
          >
            <li
              v-for="(item, li) in section.listAfter"
              :key="`sla-${si}-${li}`"
              v-html="linkify(item)"
            />
          </ul>

          <aside
            v-if="section.callout"
            class="callout"
            :class="`callout--${section.callout.type || 'info'}`"
            role="note"
          >
            <p v-html="linkify(section.callout.text)" />
          </aside>
        </section>

        <p
          v-if="doc.outro"
          class="outro"
          v-html="linkify(doc.outro)"
        />

        <footer
          v-if="doc.contact"
          class="contact"
        >
          <p
            v-if="doc.contact.title"
            class="contact__title"
          >
            {{ doc.contact.title }}
          </p>
          <dl class="contact__list">
            <template
              v-for="(item, ci) in doc.contact.items ?? []"
              :key="`c-${ci}`"
            >
              <dt>{{ item.label }}</dt>
              <dd>
                <a
                  v-if="item.href"
                  :href="item.href"
                  target="_blank"
                  rel="noopener noreferrer"
                >{{ item.value }}</a>
                <span v-else>{{ item.value }}</span>
              </dd>
            </template>
          </dl>
        </footer>
      </article>
    </div>

    <nav
      v-if="otherDocs.length"
      class="related"
      aria-label="Другие документы"
    >
      <p class="related__title">
        Другие документы
      </p>
      <ul class="related__list">
        <li
          v-for="link in otherDocs"
          :key="link.to"
        >
          <RouterLink :to="link.to">{{ link.label }}</RouterLink>
        </li>
      </ul>
    </nav>
  </SitePageLayout>
</template>

<style scoped>
.legal-page {
  --page-content-max: 52rem;
}

.legal-loading {
  margin: 0.5rem 0 1rem;
  color: var(--muted);
  font-size: 0.95rem;
}

.legal-page :deep(.site-page-layout__body) {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.head {
  margin-bottom: 1.1rem;
  text-align: center;
}

.badge {
  display: inline-block;
  margin: 0 0 0.65rem;
  padding: 0.2rem 0.65rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
  border-radius: 999px;
}

h1 {
  font-size: clamp(1.35rem, 3vw, 1.75rem);
  margin: 0 0 0.45rem;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1.45;
  max-width: 36rem;
  margin-inline: auto;
}

.meta {
  margin: 0.55rem 0 0;
  font-size: 0.82rem;
  color: color-mix(in srgb, var(--muted) 85%, transparent);
}

.legal-layout {
  display: grid;
  gap: 0.85rem;
}

@media (min-width: 960px) {
  .legal-layout {
    grid-template-columns: minmax(11rem, 14rem) minmax(0, 1fr);
    align-items: start;
  }
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

@media (min-width: 640px) {
  .card-pad {
    padding: 1.65rem 1.85rem;
  }
}

.toc {
  padding: 1rem 1.1rem;
  position: sticky;
  top: 1rem;
}

@media (max-width: 959px) {
  .toc {
    position: static;
  }
}

.toc__title {
  margin: 0 0 0.55rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
}

.toc__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.35rem;
}

.toc__list a {
  display: block;
  padding: 0.3rem 0;
  font-size: 0.84rem;
  line-height: 1.4;
  color: var(--muted);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color 0.15s ease, border-color 0.15s ease;
}

.toc__list a:hover {
  color: var(--accent);
  border-bottom-color: color-mix(in srgb, var(--accent) 35%, transparent);
}

.doc {
  font-size: 0.94rem;
  line-height: 1.68;
  color: var(--text);
}

.doc :is(p, ul) {
  margin: 0 0 0.85rem;
}

.doc :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-word;
}

.doc :deep(a:hover) {
  color: var(--accent-hover);
}

.intro {
  color: var(--text-h);
  font-size: 0.97rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--card-border);
  margin-bottom: 1.1rem !important;
}

.callout {
  margin: 0.85rem 0 1rem;
  padding: 0.85rem 1rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--card-bg) 70%, var(--accent) 8%);
}

.callout :is(p, ul) {
  margin: 0;
}

.callout--disclaimer {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 8%, var(--card-bg));
}

.callout--info {
  border-color: color-mix(in srgb, var(--accent) 25%, var(--card-border));
}

.callout--warning {
  border-color: color-mix(in srgb, var(--danger, #e74c3c) 35%, var(--card-border));
  background: color-mix(in srgb, var(--danger, #e74c3c) 6%, var(--card-bg));
}

.section {
  margin-top: 1.5rem;
  padding-top: 1.35rem;
  border-top: 1px solid color-mix(in srgb, var(--card-border) 80%, transparent);
  scroll-margin-top: 1.25rem;
}

.section:first-of-type {
  margin-top: 0.25rem;
  padding-top: 0;
  border-top: none;
}

.section h2 {
  font-size: 1.02rem;
  font-weight: 700;
  color: var(--text-h);
  margin: 0 0 0.75rem;
  line-height: 1.35;
}

.subsection {
  margin: 0.75rem 0 0.25rem;
  padding-left: 0.85rem;
  border-left: 2px solid color-mix(in srgb, var(--accent) 30%, transparent);
}

.subsection h3 {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-h);
  margin: 0 0 0.55rem;
  line-height: 1.4;
}

.list {
  padding-left: 1.25rem;
}

.list li {
  margin-bottom: 0.4rem;
}

.list li::marker {
  color: var(--accent);
}

.outro {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border);
  white-space: pre-line;
}

.contact {
  margin-top: 1.35rem;
  padding: 1rem 1.1rem;
  border-radius: 10px;
  background: color-mix(in srgb, var(--card-bg) 85%, var(--accent) 5%);
  border: 1px solid var(--card-border);
}

.contact__title {
  margin: 0 0 0.65rem;
  font-weight: 700;
  color: var(--text-h);
}

.contact__list {
  margin: 0;
  display: grid;
  gap: 0.45rem;
}

.contact__list dt {
  font-size: 0.78rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}

.contact__list dd {
  margin: 0;
  color: var(--text-h);
}

.related {
  margin-top: 0.25rem;
  padding: 0.95rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--card-bg) 92%, transparent);
}

.related__title {
  margin: 0 0 0.55rem;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
}

.related__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.75rem;
}

.related__list a {
  font-size: 0.88rem;
  color: var(--accent);
  text-decoration: none;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
  transition: background 0.15s ease, border-color 0.15s ease;
}

.related__list a:hover {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
}
</style>
