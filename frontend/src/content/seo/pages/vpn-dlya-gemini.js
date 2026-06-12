/**
 * Контент SEO-страницы /vpn-dlya-gemini
 *
 * Фон hero: frontend/public/images/seo/vpn-dlya-gemini.png
 */
export const GEMINI_SEO_HERO_BG = '/images/seo/vpn-dlya-gemini.png'

export const vpnDlyaGeminiPage = {
  meta: {
    title: 'VPN для Gemini — доступ к Google AI без блокировок | Подорожник VPN',
    description:
      'VPN для Google Gemini: стабильный доступ к чату и API, умный split tunneling — банки и Госуслуги работают напрямую. Пробный период 3 дня.',
  },
  hero: {
    badgeIcon: '/images/home/how/vpn/google-gemini.png',
    badgeText: 'VPN для Gemini',
    titleLine1: 'Работайте с',
    titleHighlight: 'Gemini',
    titleLine2: 'без блокировок',
    accentColor: '#4285f4',
    lead:
      'Доступ к Google Gemini в браузере и приложении — быстрые ответы, без ограничений региона.',
    bgImage: GEMINI_SEO_HERO_BG,
    features: [
      {
        icon: 'Globe',
        title: 'Доступ к Gemini',
        text: 'Обход блокировок в один клик',
      },
      {
        icon: 'Zap',
        title: 'Быстрые ответы',
        text: 'Стабильное соединение без задержек',
      },
      {
        icon: 'Lock',
        title: 'Защита данных',
        text: 'Шифрование вашего соединения',
      },
    ],
  },
  article: {
    title: 'VPN для Google Gemini: зачем нужен и как работает Подорожник',
    sections: [
      {
        heading: 'Почему Gemini может быть недоступен',
        paragraphs: [
          'Google Gemini ограничивают по региону или блокируют на уровне провайдера. VPN направляет трафик к сервису через зарубежный сервер — чат и веб-интерфейс открываются как обычно.',
          'Подорожник VPN использует VLESS и умную маршрутизацию: Gemini, YouTube, ChatGPT и другие зарубежные сервисы идут через туннель, а банки, Госуслуги и локальные приложения — напрямую.',
        ],
      },
      {
        heading: 'Преимущества Подорожник для Gemini',
        paragraphs: [
          'Не нужно постоянно включать и выключать VPN — split tunneling настроен на нашей стороне.',
          'До 5 устройств на одной подписке: телефон, компьютер и планшет.',
          'Пробный период 3 дня — проверьте скорость и стабильность на своих запросах.',
        ],
      },
      {
        heading: 'Как начать пользоваться Gemini через VPN',
        paragraphs: [
          'Зарегистрируйтесь, получите конфигурацию в личном кабинете и подключите её в клиенте с поддержкой VLESS (Happ, V2Ray и др.).',
          'Откройте gemini.google.com или приложение Gemini — сервис должен работать без ограничений. Поддержка 24/7 поможет с настройкой.',
        ],
      },
    ],
  },
}
