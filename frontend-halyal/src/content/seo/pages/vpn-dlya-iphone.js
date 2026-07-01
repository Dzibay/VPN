/**
 * Контент SEO-страницы /vpn-dlya-iphone
 *
 * Фон hero: frontend/public/images/seo/vpn-dlya-iphone.png
 */
export const IPHONE_SEO_HERO_BG = '/images/seo/vpn-dlya-iphone.png'

export const vpnDlyaIphonePage = {
  meta: {
    title: 'VPN для iPhone — установка и настройка на iOS | Подорожник VPN',
    description:
      'VPN для iPhone и iPad: установка через Happ за пару минут. YouTube, Telegram и зарубежные сервисы — через VPN, российские сервисы без постоянного переключения. Пробный период 3 дня.',
  },
  hero: {
    badgeIcon: '/icons/apple-touch-icon.png',
    badgeText: 'VPN для iPhone',
    titleLine1: 'Надёжный VPN',
    titleHighlight: 'для iPhone',
    titleLine2: 'без блокировок',
    accentColor: '#007aff',
    lead:
      'YouTube, Telegram, Gemini и другие сервисы на iPhone — в один клик, без постоянного включения и выключения VPN.',
    bgImage: IPHONE_SEO_HERO_BG,
    features: [
      {
        icon: 'Globe',
        title: 'Доступ к сервисам',
        text: 'Обход блокировок на iOS',
      },
      {
        icon: 'Zap',
        title: 'Быстрое подключение',
        text: 'Настройка через Happ за пару минут',
      },
      {
        icon: 'Lock',
        title: 'Защита данных',
        text: 'Шифрование трафика на iPhone',
      },
    ],
  },
  article: {
    title: 'VPN для iPhone: как установить и настроить Подорожник на iOS',
    sections: [
      {
        heading: 'Зачем нужен VPN на iPhone',
        paragraphs: [
          'На iPhone многие зарубежные сервисы — YouTube, Telegram, ChatGPT, Gemini — могут работать нестабильно или быть недоступны из‑за ограничений провайдера. VPN создаёт зашифрованный канал до сервера за рубежом, и приложения снова открываются в обычном режиме.',
          'Подорожник VPN использует протокол VLESS и умную маршрутизацию: только нужные сервисы идут через туннель, а российские банки, Госуслуги и локальные приложения — напрямую, без выключения VPN на iPhone.',
        ],
      },
      {
        heading: 'Преимущества Подорожник для iPhone и iPad',
        paragraphs: [
          'Одна подписка — до 5 устройств: iPhone, iPad, Mac и другие.',
          'Не нужно постоянно включать и выключать VPN — split tunneling настроен на нашей стороне.',
          'Пробный период 3 дня без привязки карты — проверьте скорость и стабильность на своих приложениях.',
        ],
      },
      {
        heading: 'Как установить VPN на iPhone',
        paragraphs: [
          'Зарегистрируйтесь на сайте, получите конфигурацию в личном кабинете и откройте ссылку подписки в клиенте Happ (или другом приложении с поддержкой VLESS).',
          'После подключения откройте нужное приложение на iPhone — сервис должен работать без ограничений. Если нужна помощь с настройкой, напишите в поддержку 24/7.',
        ],
      },
    ],
  },
}
