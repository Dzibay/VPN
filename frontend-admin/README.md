# frontend-admin

Отдельный Vite/Vue SPA для админ-панели персонала. Публикуется на выделенном домене
`admin.<domain>` и не смешивается с публичными фронтами проектов
(`frontend/` собирается пер-проектно).

## Стек

- Vue 3 + Vue Router + Pinia (без SSR).
- fetch-обёртка `src/api/client.js` шлёт `Authorization: Bearer <STAFF_JWT>` и
  `X-Admin-Project: <slug|__all__>`.
- Логин через `POST /api/staff/auth/login` → staff-JWT (`aud=staff`),
  профиль хранится в `localStorage` (`STAFF_JWT`, `STAFF_PROFILE`, `STAFF_CURRENT_PROJECT`).

## Скрипты

```
npm install
npm run dev       # http://127.0.0.1:5174 (proxy /api → 127.0.0.1:5000)
npm run build     # сборка в dist/
```

## Роутинг

| Path                          | Кто видит                          |
|-------------------------------|------------------------------------|
| `/login`                      | публично                           |
| `/dashboard`                  | любой staff                        |
| `/projects`, `/projects/:id`  | любой staff (write — super_admin)  |
| `/projects/:id/tariffs`       | любой staff (write — super_admin)  |
| `/staff-users`                | super_admin                        |

Полный набор существующих admin-view (пейменты, финансы, воронка, аналитика и т. д.)
пока живёт в `../frontend/` и подключается через alias `@legacy-views/*` — миграция
этих страниц в `frontend-admin` идёт постепенно (см. план multi-project).

## Селектор проекта

`components/ProjectSelector.vue` в topbar сохраняет slug в `localStorage`.
После смены slug — всплывает событие `staff:project-changed` (view-компоненты
подписываются и перезагружают данные под новый проект).
