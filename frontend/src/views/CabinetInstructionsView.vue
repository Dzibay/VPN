<script setup>
import { ref } from 'vue'
import CabinetBackLink from '../components/CabinetBackLink.vue'
import SitePageLayout from '../components/SitePageLayout.vue'

const PLATFORM_OPTIONS = [
  { value: 'pc', label: 'ПК' },
  { value: 'android', label: 'Android' },
  { value: 'ios', label: 'iOS' },
]

const autoPlatform = ref('pc')

const INSTRUCTION_IMAGES = {
  cabinetApps: '/images/instructions/auto-cabinet-apps.png',
  openPage: '/images/instructions/auto-open-page.png',
  downloadPc: '/images/instructions/auto-download-pc.png',
  manualCopyLink: '/images/instructions/manual-copy-link.png',
  manualImportApp: '/images/instructions/manual-import-app.png',
}

function setAutoPlatform(value) {
  autoPlatform.value = value
}
</script>

<template>
  <SitePageLayout class="instructions-page">
    <template #header>
      <header class="head">
        <h1>Инструкции</h1>
        <p class="sub">Как подключить VPN и пользоваться сервисом</p>
      </header>
    </template>

    <CabinetBackLink to="/cabinet" label="Личный кабинет" />

    <div class="instructions-stack">
      <details class="instr-widget" open>
        <summary class="instr-widget__summary">
          <span class="instr-widget__title">Автоматическое подключение</span>
          <span class="instr-widget__chevron" aria-hidden="true" />
        </summary>

        <div class="instr-widget__body">
          <p class="instr-lead">
            Рекомендуемый способ: приложение само получит конфигурацию по ссылке.
            Если приложения ещё нет — советуем
            <strong>HAPP</strong>.
          </p>

          <div class="platform-block">
            <div
              class="platform-chips"
              role="radiogroup"
              aria-label="Платформа для инструкции автоматического подключения"
            >
              <button
                v-for="p in PLATFORM_OPTIONS"
                :key="p.value"
                type="button"
                class="platform-chip"
                :class="{ 'platform-chip--active': autoPlatform === p.value }"
                role="radio"
                :aria-checked="autoPlatform === p.value"
                @click="setAutoPlatform(p.value)"
              >
                <span class="platform-chip__icon" aria-hidden="true">
                  <!-- ПК -->
                  <svg
                    v-if="p.value === 'pc'"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.75"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M2 18h20" /></svg>
                  <!-- Android -->
                  <svg
                    v-else-if="p.value === 'android'"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  ><path d="M17.6 9.48l1.84-3.18c.16-.31.04-.69-.26-.85a.657.657 0 0 0-.83.22l-1.88 3.24a11.437 11.437 0 0 0-8.45 0L5.1 5.67a.648.648 0 0 0-.83-.22c-.3.16-.42.54-.26.85l1.84 3.18C3.25 10.82 2 13.37 2 16.19h20c0-2.82-1.25-5.37-3.4-7.71zM7 14.75c0 .55.45 1 1 1s1-.45 1-1-.45-1-1-1-1 .45-1 1zm8 0c0 .55.45 1 1 1s1-.45 1-1-.45-1-1-1-1 .45-1 1z" /></svg>
                  <!-- iOS -->
                  <svg
                    v-else-if="p.value === 'ios'"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                  ><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" /></svg>
                </span>
                <span class="platform-chip__label">{{ p.label }}</span>
              </button>
            </div>
          </div>

          <ol class="instr-steps">
            <li class="instr-step">
              <p class="instr-step__text">
                В личном кабинете на вкладке «Подписка» в блоке
                «Подключить в приложении» нажмите плитку нужного приложения.
              </p>
              <figure class="instr-screenshot">
                <img
                  :src="INSTRUCTION_IMAGES.cabinetApps"
                  alt="Выбор приложения в личном кабинете"
                  class="instr-screenshot__img"
                  loading="lazy"
                  decoding="async"
                />
              </figure>
            </li>

            <li class="instr-step">
              <p class="instr-step__text">
                Откроется страница автоматического подключения. Если приложение
                уже установлено, конфигурация подставится в него автоматически.
              </p>
              <figure class="instr-screenshot">
                <img
                  :src="INSTRUCTION_IMAGES.openPage"
                  alt="Страница автоматического подключения"
                  class="instr-screenshot__img"
                  loading="lazy"
                  decoding="async"
                />
              </figure>
            </li>

            <li v-if="autoPlatform === 'pc'" class="instr-step">
              <p class="instr-step__text">
                Если приложения ещё нет: на странице подключения нажмите кнопку
                скачивания или перейдите на официальный сайт приложения.
                Скачайте и установите программу, затем снова откройте страницу
                подключения из личного кабинета и нажмите кнопку автоматической
                вставки конфигурации.
              </p>
              <figure class="instr-screenshot">
                <img
                  :src="INSTRUCTION_IMAGES.downloadPc"
                  alt="Скачивание приложения на ПК"
                  class="instr-screenshot__img"
                  loading="lazy"
                  decoding="async"
                />
              </figure>
            </li>

            <li v-else-if="autoPlatform === 'android'" class="instr-step">
              <p class="instr-step__text">
                Если приложения ещё нет: скачайте его из Google Play или нажмите
                кнопку скачивания на странице подключения. После установки
                вернитесь на страницу подключения из личного кабинета и нажмите
                кнопку автоматической вставки конфигурации.
              </p>
            </li>

            <li v-else class="instr-step">
              <p class="instr-step__text">
                Если приложения ещё нет: скачайте приложение из App Store.
                После установки вернитесь на страницу подключения из личного
                кабинета и нажмите кнопку автоматической вставки конфигурации.
              </p>
            </li>
          </ol>
        </div>
      </details>

      <details class="instr-widget">
        <summary class="instr-widget__summary">
          <span class="instr-widget__title">Ручное подключение</span>
          <span class="instr-widget__chevron" aria-hidden="true" />
        </summary>

        <div class="instr-widget__body">
          <p class="instr-lead">
            Если автоматическая настройка недоступна, скопируйте ссылку подписки
            в личном кабинете и добавьте её в приложение вручную через пункт
            «Импорт по ссылке» или «Добавить подписку».
          </p>

          <ol class="instr-steps">
            <li class="instr-step">
              <p class="instr-step__text">
                В личном кабинете нажмите «Скопировать ссылку подписки».
              </p>
              <figure class="instr-screenshot">
                <img
                  :src="INSTRUCTION_IMAGES.manualCopyLink"
                  alt="Копирование ссылки подписки"
                  class="instr-screenshot__img"
                  loading="lazy"
                  decoding="async"
                />
              </figure>
            </li>

            <li class="instr-step">
              <p class="instr-step__text">
                Откройте VPN-приложение, найдите импорт по URL или ссылке и
                вставьте скопированную ссылку.
              </p>
              <figure class="instr-screenshot">
                <img
                  :src="INSTRUCTION_IMAGES.manualImportApp"
                  alt="Ручной импорт ссылки в приложении"
                  class="instr-screenshot__img"
                  loading="lazy"
                  decoding="async"
                />
              </figure>
            </li>
          </ol>
        </div>
      </details>

      <details class="instr-widget">
        <summary class="instr-widget__summary">
          <span class="instr-widget__title">Подключение нового устройства</span>
          <span class="instr-widget__chevron" aria-hidden="true" />
        </summary>

        <div class="instr-widget__body">
          <p class="instr-lead">
            Чтобы добавить ещё одно устройство к подписке, выберите один из двух
            способов ниже.
          </p>

          <div class="instr-methods">
            <section class="instr-method" aria-label="Автоматическая настройка на новом устройстве">
              <h3 class="instr-method__title">Способ 1 — на новом устройстве через сайт</h3>
              <ol class="instr-steps instr-steps--nested">
                <li class="instr-step">
                  <p class="instr-step__text">
                    На новом устройстве откройте сайт и войдите в личный кабинет
                    под своей учётной записью.
                  </p>
                </li>
                <li class="instr-step">
                  <p class="instr-step__text">
                    На вкладке «Подписка» выберите приложение и выполните
                    автоматическое подключение — так же, как описано в блоке
                    «Автоматическое подключение» выше.
                  </p>
                </li>
              </ol>
            </section>

            <section class="instr-method" aria-label="Перенос ссылки подписки на новое устройство">
              <h3 class="instr-method__title">Способ 2 — перенести ссылку подписки</h3>
              <ol class="instr-steps instr-steps--nested">
                <li class="instr-step">
                  <p class="instr-step__text">
                    На любом уже настроенном устройстве откройте личный кабинет
                    и нажмите «Скопировать ссылку подписки».
                  </p>
                  <figure class="instr-screenshot">
                    <img
                      :src="INSTRUCTION_IMAGES.manualCopyLink"
                      alt="Копирование ссылки подписки в личном кабинете"
                      class="instr-screenshot__img"
                      loading="lazy"
                      decoding="async"
                    />
                  </figure>
                </li>
                <li class="instr-step">
                  <p class="instr-step__text">
                    Передайте ссылку на новое устройство — через мессенджер,
                    почту или любой удобный способ.
                  </p>
                </li>
                <li class="instr-step">
                  <p class="instr-step__text">
                    На новом устройстве откройте VPN-приложение, выберите
                    импорт по ссылке и вставьте скопированный адрес — как в
                    блоке «Ручное подключение» выше.
                  </p>
                  <figure class="instr-screenshot">
                    <img
                      :src="INSTRUCTION_IMAGES.manualImportApp"
                      alt="Вставка ссылки подписки в приложении на новом устройстве"
                      class="instr-screenshot__img"
                      loading="lazy"
                      decoding="async"
                    />
                  </figure>
                </li>
              </ol>
            </section>
          </div>
        </div>
      </details>
    </div>
  </SitePageLayout>
</template>

<style scoped>
.instructions-page :deep(.site-page-layout__body) {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.head {
  margin-bottom: 1.35rem;
  text-align: center;
}

h1 {
  font-size: 1.6rem;
  margin: 0 0 0.4rem;
}

.sub {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
  line-height: 1.45;
}

.instructions-stack {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.instr-widget {
  min-width: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
  overflow: hidden;
}

.instr-widget__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1.05rem 1.25rem;
  cursor: pointer;
  list-style: none;
  user-select: none;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-h);
  transition: background 0.2s ease;
}

.instr-widget__summary::-webkit-details-marker {
  display: none;
}

.instr-widget__summary:hover {
  background: color-mix(in srgb, var(--accent-soft) 35%, var(--card-bg));
}

.instr-widget__summary:focus-visible {
  outline: none;
  box-shadow: inset var(--focus-ring);
}

.instr-widget__title {
  flex: 1;
  min-width: 0;
  line-height: 1.35;
}

.instr-widget__chevron {
  flex-shrink: 0;
  width: 0.55rem;
  height: 0.55rem;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  transform: rotate(-45deg);
  transition: transform 0.2s ease;
}

.instr-widget[open] .instr-widget__chevron {
  transform: rotate(45deg);
  margin-top: -0.2rem;
}

.instr-widget__body {
  padding: 0 1.25rem 1.25rem;
  border-top: 1px solid var(--nav-border);
}

.instr-lead {
  margin: 1rem 0 0;
  font-size: 0.92rem;
  line-height: 1.55;
  color: var(--muted);
}

.instr-lead strong {
  color: var(--accent);
  font-weight: 700;
}

.platform-block {
  margin-top: 1rem;
}

.platform-chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.35rem;
  justify-content: center;
  width: 100%;
  min-width: 0;
}

.platform-chip {
  appearance: none;
  margin: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 0;
  min-width: 0;
  gap: 0.35rem;
  padding: 0.45rem 0.55rem;
  border-radius: var(--radius-pill);
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--card-border);
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease;
}

.platform-chip__label {
  white-space: nowrap;
}

.platform-chip__icon {
  display: flex;
  width: 0.95rem;
  height: 0.95rem;
  flex-shrink: 0;
  color: var(--muted);
}

.platform-chip__icon svg {
  width: 100%;
  height: 100%;
}

.platform-chip--active .platform-chip__icon {
  color: var(--accent);
}

.platform-chip:hover {
  border-color: var(--accent-border);
  color: var(--text-h);
}

.platform-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.platform-chip--active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
  color: var(--accent);
}

.instr-steps {
  margin: 1.15rem 0 0;
  padding: 0 0 0 1.15rem;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.instr-step {
  padding-left: 0.15rem;
}

.instr-step__text {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.55;
  color: var(--text-h);
}

.instr-screenshot {
  margin: 0.75rem 0 0;
  padding: 0;
}

.instr-screenshot__img {
  width: 100%;
  height: auto;
  display: block;
  border-radius: 10px;
  border: 1px solid var(--card-border);
}

.instr-methods {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.instr-method {
  padding: 1rem;
  border-radius: 12px;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--surface) 55%, var(--card-bg));
}

.instr-method__title {
  margin: 0 0 0.65rem;
  font-size: 0.94rem;
  font-weight: 700;
  line-height: 1.35;
  color: var(--text-h);
}

.instr-steps--nested {
  margin-top: 0;
  padding-left: 1rem;
}

@media (max-width: 420px) {
  .instr-widget__summary {
    padding: 0.95rem 1rem;
    font-size: 0.94rem;
  }

  .instr-widget__body {
    padding: 0 1rem 1rem;
  }

  .platform-chip {
    font-size: 0.75rem;
    padding: 0.4rem 0.35rem;
  }
}
</style>
