<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  /** @type {import('vue').PropType<Array<object>>} */
  servers: { type: Array, required: true },
  menuOpenId: { type: Number, default: null },
  busyServerId: { type: Number, default: null },
})

const emit = defineEmits(['edit', 'toggle-menu'])

const referencedExitIds = computed(() => {
  const ids = new Set()
  for (const s of props.servers) {
    if (s.cascade_next_server_id != null) ids.add(s.cascade_next_server_id)
  }
  return ids
})

const cascadeGroups = computed(() => {
  const byExit = new Map()
  for (const s of props.servers) {
    if (!s.is_cascade_ru_entry || !s.cascade_next_server_id) continue
    const exitId = s.cascade_next_server_id
    if (!byExit.has(exitId)) {
      const exit = props.servers.find((e) => e.id === exitId) ?? null
      byExit.set(exitId, { exitId, exit, entries: [] })
    }
    byExit.get(exitId).entries.push(s)
  }
  for (const g of byExit.values()) {
    g.entries.sort((a, b) => a.id - b.id)
  }
  return Array.from(byExit.values()).sort((a, b) => a.exitId - b.exitId)
})

const orphanRuEntries = computed(() =>
  props.servers
    .filter((s) => s.is_cascade_ru_entry && !s.cascade_next_server_id)
    .sort((a, b) => a.id - b.id),
)

const standaloneExits = computed(() =>
  props.servers
    .filter(
      (s) => !s.is_cascade_ru_entry && !referencedExitIds.value.has(s.id),
    )
    .sort((a, b) => a.id - b.id),
)

const hasAnyNodes = computed(
  () =>
    cascadeGroups.value.length > 0 ||
    orphanRuEntries.value.length > 0 ||
    standaloneExits.value.length > 0,
)

function proxyKindLabel(kind) {
  if (kind === 'hysteria2') return 'Hysteria2'
  if (kind === 'vless_grpc') return 'gRPC+TLS'
  if (kind === 'vless_ws') return 'WebSocket+TLS'
  if (kind === 'vless_xhttp') return 'XHTTP+TLS'
  if (kind === 'vless_vk_cdn_xhttp') return 'VK CDN XHTTP'
  return 'REALITY'
}

function formatProvisionStatus(status) {
  const key = String(status ?? '').toLowerCase()
  const labels = {
    idle: 'Нет задачи',
    queued: 'В очереди',
    running: 'Установка…',
    success: 'Готово',
    failed: 'Ошибка',
  }
  return labels[key] ?? status ?? '—'
}

function provisionStatusClass(status) {
  const key = String(status ?? '').toLowerCase()
  if (key === 'success') return 'topo-node__status--ok'
  if (key === 'failed') return 'topo-node__status--fail'
  if (key === 'queued' || key === 'running') return 'topo-node__status--busy'
  return ''
}

function roleLabel(server) {
  if (server.is_cascade_ru_entry) return 'Вход (РФ)'
  if (referencedExitIds.value.has(server.id)) return 'Exit'
  return 'Внешний'
}

function roleClass(server) {
  if (server.is_cascade_ru_entry) return 'topo-node__role--entry'
  if (referencedExitIds.value.has(server.id)) return 'topo-node__role--exit'
  return 'topo-node__role--standalone'
}

function analyticsTo(id) {
  return { path: '/admin/analytics', query: { server: id } }
}

function loadStyle(server) {
  return {
    '--load': Math.min(100, Math.max(0, server.load_percent ?? 0)),
  }
}

function onEdit(server) {
  emit('edit', server)
}

function onToggleMenu(server, event) {
  emit('toggle-menu', server, event)
}

/** Линии «N входов → 1 exit» для SVG-хаба */
function hubSvgPath(entryCount) {
  const n = Number(entryCount) || 0
  if (n <= 0) return ''
  if (n === 1) return 'M0,50 L40,50'
  const ys = Array.from({ length: n }, (_, i) => 10 + (i / (n - 1)) * 80)
  const parts = ys.map((y) => `M0,${y.toFixed(1)} L20,${y.toFixed(1)}`)
  parts.push(`M20,${ys[0].toFixed(1)} L20,${ys[n - 1].toFixed(1)}`)
  parts.push('M20,50 L44,50')
  return parts.join(' ')
}
</script>

<template>
  <div class="servers-topology" aria-label="Схема серверов">
    <p v-if="!hasAnyNodes" class="topo-empty muted">
      Серверов для отображения нет. Добавьте внешний exit, затем при необходимости
      — вход (РФ) с привязкой к exit.
    </p>

    <section
      v-if="cascadeGroups.length"
      class="topo-section"
      aria-label="Каскадные группы"
    >
      <h3 class="topo-section__title">Каскады</h3>
      <div class="topo-groups">
        <article
          v-for="group in cascadeGroups"
          :key="`group-${group.exitId}`"
          class="topo-group"
        >
          <header class="topo-group__head">
            <span class="topo-group__badge">Каскад</span>
            <span class="topo-group__meta">
              {{ group.entries.length }}
              {{
                group.entries.length === 1
                  ? 'вход'
                  : group.entries.length < 5
                    ? 'входа'
                    : 'входов'
              }}
              → exit
              <template v-if="group.exit">
                #{{ group.exit.id
                }}<span v-if="group.exit.name"> · {{ group.exit.name }}</span>
              </template>
              <template v-else>#{{ group.exitId }} (не найден)</template>
            </span>
          </header>

          <div class="topo-group__body">
            <div class="topo-group__entries">
              <article
                v-for="entry in group.entries"
                :key="entry.id"
                class="topo-node topo-node--entry"
                :class="{
                  'topo-node--hidden': entry.is_hidden,
                  'topo-node--inactive': !entry.is_active,
                }"
              >
                <div class="topo-node__main">
                  <div class="topo-node__line1">
                    <span class="topo-node__role topo-node__role--entry"
                      >Вход (РФ)</span
                    >
                    <span class="topo-node__id">#{{ entry.id }}</span>
                    <span v-if="entry.is_hidden" class="topo-node__tag"
                      >скрыт</span
                    >
                    <span class="topo-node__name">{{
                      entry.name || entry.host
                    }}</span>
                  </div>
                  <div class="topo-node__line2">
                    <span class="mono">{{ entry.host }}:{{ entry.port }}</span>
                    <span v-if="entry.country" class="topo-node__sep">·</span>
                    <span v-if="entry.country">{{ entry.country }}</span>
                    <span class="topo-node__sep">·</span>
                    <span>{{ proxyKindLabel(entry.proxy_kind) }}</span>
                    <span class="topo-node__load">
                      {{ entry.load_percent ?? 0 }}%
                      <span
                        class="topo-load-bar"
                        :style="loadStyle(entry)"
                        aria-hidden="true"
                      />
                    </span>
                    <span
                      class="topo-node__status"
                      :class="provisionStatusClass(entry.provision_status)"
                    >
                      {{ formatProvisionStatus(entry.provision_status) }}
                    </span>
                  </div>
                </div>
                <div class="topo-node__actions">
                  <RouterLink
                    class="btn-secondary btn-tiny"
                    :to="analyticsTo(entry.id)"
                  >
                    Графики
                  </RouterLink>
                  <button
                    type="button"
                    class="btn-secondary btn-tiny"
                    @click="onEdit(entry)"
                  >
                    Правка
                  </button>
                  <button
                    type="button"
                    class="btn-dropdown-trigger btn-secondary btn-tiny"
                    :aria-expanded="menuOpenId === entry.id"
                    aria-haspopup="menu"
                    :disabled="busyServerId === entry.id"
                    @click.stop="onToggleMenu(entry, $event)"
                  >
                    Действия
                    <span class="btn-dropdown-chevron" aria-hidden="true"
                      >▾</span
                    >
                  </button>
                </div>
              </article>
            </div>

            <div
              class="topo-group__hub"
              aria-hidden="true"
              :data-count="group.entries.length"
            >
              <svg
                class="topo-hub-svg"
                viewBox="0 0 48 100"
                preserveAspectRatio="none"
              >
                <defs>
                  <marker
                    :id="`topo-arrowhead-${group.exitId}`"
                    markerWidth="6"
                    markerHeight="6"
                    refX="5"
                    refY="3"
                    orient="auto"
                  >
                    <path
                      d="M0,0 L6,3 L0,6 Z"
                      class="topo-hub-svg__arrowhead"
                    />
                  </marker>
                </defs>
                <path
                  class="topo-hub-svg__path"
                  :d="hubSvgPath(group.entries.length)"
                  :marker-end="`url(#topo-arrowhead-${group.exitId})`"
                />
              </svg>
            </div>

            <div class="topo-group__exit">
            <article
              class="topo-node topo-node--exit"
              :class="{
                'topo-node--hidden': group.exit?.is_hidden,
                'topo-node--inactive': group.exit && !group.exit.is_active,
                'topo-node--missing': !group.exit,
              }"
            >
              <template v-if="group.exit">
                <div class="topo-node__main">
                  <div class="topo-node__line1">
                    <span class="topo-node__role topo-node__role--exit"
                      >Exit</span
                    >
                    <span class="topo-node__id">#{{ group.exit.id }}</span>
                    <span v-if="group.exit.is_hidden" class="topo-node__tag"
                      >скрыт</span
                    >
                    <span class="topo-node__name">{{
                      group.exit.name || group.exit.host
                    }}</span>
                  </div>
                  <div class="topo-node__line2">
                    <span class="mono"
                      >{{ group.exit.host }}:{{ group.exit.port }}</span
                    >
                    <span v-if="group.exit.country" class="topo-node__sep"
                      >·</span
                    >
                    <span v-if="group.exit.country">{{
                      group.exit.country
                    }}</span>
                    <span class="topo-node__sep">·</span>
                    <span>{{ proxyKindLabel(group.exit.proxy_kind) }}</span>
                    <span class="topo-node__load">
                      {{ group.exit.load_percent ?? 0 }}%
                      <span
                        class="topo-load-bar"
                        :style="loadStyle(group.exit)"
                        aria-hidden="true"
                      />
                    </span>
                    <span
                      class="topo-node__status"
                      :class="
                        provisionStatusClass(group.exit.provision_status)
                      "
                    >
                      {{ formatProvisionStatus(group.exit.provision_status) }}
                    </span>
                  </div>
                </div>
                <div class="topo-node__actions">
                  <RouterLink
                    class="btn-secondary btn-tiny"
                    :to="analyticsTo(group.exit.id)"
                  >
                    Графики
                  </RouterLink>
                  <button
                    type="button"
                    class="btn-secondary btn-tiny"
                    @click="onEdit(group.exit)"
                  >
                    Правка
                  </button>
                  <button
                    type="button"
                    class="btn-dropdown-trigger btn-secondary btn-tiny"
                    :aria-expanded="menuOpenId === group.exit.id"
                    aria-haspopup="menu"
                    :disabled="busyServerId === group.exit.id"
                    @click.stop="onToggleMenu(group.exit, $event)"
                  >
                    Действия
                    <span class="btn-dropdown-chevron" aria-hidden="true"
                      >▾</span
                    >
                  </button>
                </div>
              </template>
              <template v-else>
                <div class="topo-node__main">
                  <div class="topo-node__line1">
                    <span class="topo-node__role topo-node__role--exit"
                      >Exit</span
                    >
                    <span class="topo-node__id">#{{ group.exitId }}</span>
                  </div>
                  <p class="topo-node__missing">
                    Сервер exit не найден. Привяжите вход к существующему exit.
                  </p>
                </div>
              </template>
            </article>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="orphanRuEntries.length"
      class="topo-section"
      aria-label="Входы без exit"
    >
      <h3 class="topo-section__title">Входы без exit</h3>
      <p class="topo-section__hint">
        Отмечены как вход (РФ), но внешний exit ещё не привязан.
      </p>
      <div class="topo-standalone-list">
        <article
          v-for="s in orphanRuEntries"
          :key="`orphan-${s.id}`"
          class="topo-node topo-node--warn"
          :class="{
            'topo-node--hidden': s.is_hidden,
            'topo-node--inactive': !s.is_active,
          }"
        >
          <div class="topo-node__main">
            <div class="topo-node__line1">
              <span :class="['topo-node__role', roleClass(s)]">{{
                roleLabel(s)
              }}</span>
              <span class="topo-node__id">#{{ s.id }}</span>
              <span v-if="s.is_hidden" class="topo-node__tag">скрыт</span>
              <span class="topo-node__name">{{ s.name || s.host }}</span>
            </div>
            <div class="topo-node__line2">
              <span class="mono">{{ s.host }}:{{ s.port }}</span>
              <span class="topo-node__warn">Exit не привязан</span>
            </div>
          </div>
          <div class="topo-node__actions">
            <RouterLink class="btn-secondary btn-tiny" :to="analyticsTo(s.id)">
              Графики
            </RouterLink>
            <button
              type="button"
              class="btn-secondary btn-tiny"
              @click="onEdit(s)"
            >
              Привязать exit
            </button>
            <button
              type="button"
              class="btn-dropdown-trigger btn-secondary btn-tiny"
              :aria-expanded="menuOpenId === s.id"
              aria-haspopup="menu"
              :disabled="busyServerId === s.id"
              @click.stop="onToggleMenu(s, $event)"
            >
              Действия
              <span class="btn-dropdown-chevron" aria-hidden="true">▾</span>
            </button>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="standaloneExits.length"
      class="topo-section"
      aria-label="Отдельные внешние серверы"
    >
      <h3 class="topo-section__title">Отдельные внешние серверы</h3>
      <div class="topo-standalone-list">
        <article
          v-for="s in standaloneExits"
          :key="`standalone-${s.id}`"
          class="topo-node"
          :class="{
            'topo-node--hidden': s.is_hidden,
            'topo-node--inactive': !s.is_active,
          }"
        >
          <div class="topo-node__main">
            <div class="topo-node__line1">
              <span :class="['topo-node__role', roleClass(s)]">{{
                roleLabel(s)
              }}</span>
              <span class="topo-node__id">#{{ s.id }}</span>
              <span v-if="s.is_hidden" class="topo-node__tag">скрыт</span>
              <span class="topo-node__name">{{ s.name || s.host }}</span>
            </div>
            <div class="topo-node__line2">
              <span class="mono">{{ s.host }}:{{ s.port }}</span>
              <span v-if="s.country" class="topo-node__sep">·</span>
              <span v-if="s.country">{{ s.country }}</span>
              <span class="topo-node__sep">·</span>
              <span>{{ proxyKindLabel(s.proxy_kind) }}</span>
              <span class="topo-node__load">
                {{ s.load_percent ?? 0 }}%
                <span
                  class="topo-load-bar"
                  :style="loadStyle(s)"
                  aria-hidden="true"
                />
              </span>
              <span
                class="topo-node__status"
                :class="provisionStatusClass(s.provision_status)"
              >
                {{ formatProvisionStatus(s.provision_status) }}
              </span>
            </div>
          </div>
          <div class="topo-node__actions">
            <RouterLink class="btn-secondary btn-tiny" :to="analyticsTo(s.id)">
              Графики
            </RouterLink>
            <button
              type="button"
              class="btn-secondary btn-tiny"
              @click="onEdit(s)"
            >
              Правка
            </button>
            <button
              type="button"
              class="btn-dropdown-trigger btn-secondary btn-tiny"
              :aria-expanded="menuOpenId === s.id"
              aria-haspopup="menu"
              :disabled="busyServerId === s.id"
              @click.stop="onToggleMenu(s, $event)"
            >
              Действия
              <span class="btn-dropdown-chevron" aria-hidden="true">▾</span>
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.servers-topology {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.topo-empty {
  margin: 0;
  padding: 1rem;
  border-radius: 10px;
  border: 1px dashed var(--card-border);
  text-align: center;
}

.topo-section__title {
  margin: 0 0 0.35rem;
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--text-h);
}

.topo-section__hint {
  margin: 0 0 0.65rem;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.4;
}

.topo-groups {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.topo-group {
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  overflow: hidden;
}

.topo-group__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem 0.65rem;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--card-border);
  background: var(--surface);
}

.topo-group__badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
}

.topo-group__meta {
  font-size: 0.78rem;
  color: var(--muted);
}

.topo-group__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px minmax(0, 1fr);
  gap: 0.35rem 0.5rem;
  padding: 0.65rem 0.75rem;
  align-items: center;
}

.topo-group__exit {
  min-width: 0;
  display: flex;
  align-items: center;
  align-self: stretch;
}

.topo-group__entries {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.topo-group__hub {
  align-self: stretch;
  display: flex;
  align-items: center;
  min-height: 2.5rem;
}

.topo-hub-svg {
  width: 100%;
  height: 100%;
  min-height: 3rem;
  overflow: visible;
}

.topo-hub-svg__path {
  fill: none;
  stroke: color-mix(in srgb, var(--accent) 55%, transparent);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.topo-hub-svg__arrowhead {
  fill: color-mix(in srgb, var(--accent) 70%, transparent);
}

.topo-group__hub[data-count='1'] .topo-hub-svg {
  min-height: 2.5rem;
}

@media (max-width: 900px) {
  .topo-group__body {
    grid-template-columns: 1fr;
  }

  .topo-group__hub {
    display: none;
  }
}

.topo-standalone-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.topo-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem 1rem;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--surface);
  min-width: 0;
}

.topo-node--entry {
  border-left: 3px solid color-mix(in srgb, #f59e0b 65%, var(--card-border));
}

.topo-node--exit {
  width: 100%;
  flex-wrap: nowrap;
  border-color: color-mix(in srgb, var(--accent) 45%, var(--card-border));
  background: color-mix(in srgb, var(--accent) 5%, var(--surface));
  border-left: 3px solid var(--accent);
}

.topo-node--warn {
  border-left: 3px solid #b8860b;
}

.topo-node--missing {
  border-style: dashed;
  border-color: var(--danger);
}

.topo-node--hidden {
  opacity: 0.72;
}

.topo-node--inactive {
  opacity: 0.55;
}

.topo-node__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.topo-node__line1 {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem 0.45rem;
  min-width: 0;
}

.topo-node__line2 {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.4rem;
  font-size: 0.74rem;
  color: var(--muted);
  min-width: 0;
}

.topo-node__role {
  flex-shrink: 0;
  display: inline-block;
  padding: 0.06rem 0.35rem;
  border-radius: 5px;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.topo-node__role--entry {
  color: #b45309;
  background: color-mix(in srgb, #f59e0b 16%, transparent);
  border: 1px solid color-mix(in srgb, #f59e0b 30%, transparent);
}

.topo-node__role--exit {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent) 32%, transparent);
}

.topo-node__role--standalone {
  color: var(--muted);
  background: var(--card-bg);
  border: 1px solid var(--card-border);
}

.topo-node__id {
  flex-shrink: 0;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.topo-node__tag {
  flex-shrink: 0;
  padding: 0.04rem 0.3rem;
  border-radius: 5px;
  font-size: 0.58rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--muted);
  border: 1px solid var(--card-border);
}

.topo-node__name {
  font-size: 0.84rem;
  font-weight: 700;
  color: var(--text-h);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.topo-node__sep {
  opacity: 0.45;
}

.topo-node__load {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-variant-numeric: tabular-nums;
  color: var(--text-h);
}

.topo-load-bar {
  display: inline-block;
  width: 2.5rem;
  height: 3px;
  border-radius: 2px;
  background: var(--card-border);
  vertical-align: middle;
  position: relative;
  overflow: hidden;
}

.topo-load-bar::after {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: calc(var(--load, 0) * 1%);
  background: var(--accent);
  border-radius: 2px;
}

.topo-node__status {
  color: var(--muted);
}

.topo-node__status--ok {
  color: #1a7f37;
  font-weight: 600;
}

.topo-node__status--fail {
  color: var(--danger);
  font-weight: 600;
}

.topo-node__status--busy {
  color: var(--accent);
  font-weight: 600;
}

.topo-node__warn {
  color: #b8860b;
  font-style: italic;
}

.topo-node__missing {
  margin: 0;
  font-size: 0.76rem;
  color: var(--danger);
  line-height: 1.35;
}

.topo-node__actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.3rem;
}

.topo-node__actions .btn-secondary {
  text-decoration: none;
}

@media (max-width: 720px) {
  .topo-node {
    flex-direction: column;
    align-items: stretch;
  }

  .topo-node--exit {
    flex-wrap: wrap;
  }

  .topo-node__actions {
    justify-content: flex-start;
  }
}
</style>
