Иконки для секции «Умная маршрутизация» (#how) на главной.

Названия сервисов заданы в коде (HomeView.vue → howVpnApps / howDirectApps).
Сюда кладите только PNG-логотипы (~64×64 px, @2x, прозрачный фон):

  vpn/          — международные сервисы (карточка «Через VPN»)
    youtube.png
    instagram.png
    google-gemini.png
    claude.png
    chatgpt.png
    telegram.png

  direct/       — российские сервисы (карточка «Напрямую (РФ)»)
    sberbank.png
    tbank.png
    gosuslugi.png
    kinopoisk.png
    yandex-eda.png
    wildberries.png

Имена файлов должны совпадать — пути заданы в HomeView.vue (howVpnApps / howDirectApps).
