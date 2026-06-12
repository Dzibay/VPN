/**
 * Контент SEO-страницы /vpn-dlya-telegram
 *
 * Фон hero: frontend/public/images/seo/vpn-dlya-telegram.png
 */
export const TELEGRAM_SEO_HERO_BG = '/images/seo/vpn-dlya-telegram.png'

export const vpnDlyaTelegramPage = {
  meta: {
    title: 'VPN для Telegram — звонки и мессенджер без блокировок | Подорожник VPN',
    description:
      'VPN для Telegram в России: стабильные звонки и сообщения, умный split tunneling — банки и Госуслуги работают напрямую. Пробный период 3 дня.',
  },
  hero: {
    badgeIcon: '/images/home/how/vpn/telegram.png',
    badgeText: 'VPN для Telegram',
    titleLine1: 'Пользуйтесь',
    titleHighlight: 'Telegram',
    titleLine2: 'без блокировок',
    accentColor: '#2aabee',
    lead:
      'Сообщения, звонки и каналы в Telegram — стабильно и без ограничений скорости.',
    bgImage: TELEGRAM_SEO_HERO_BG,
    features: [
      {
        icon: 'Globe',
        title: 'Доступ к Telegram',
        text: 'Обход блокировок в один клик',
      },
      {
        icon: 'Zap',
        title: 'Стабильные звонки',
        text: 'Голос и видео без обрывов',
      },
      {
        icon: 'Lock',
        title: 'Защита данных',
        text: 'Шифрование вашего соединения',
      },
    ],
  },
  article: {
    title: 'VPN для Telegram: зачем нужен и как работает Подорожник',
    sections: [
      {
        heading: 'Почему Telegram блокируют и как VPN помогает',
        paragraphs: [
          'Telegram может работать нестабильно или быть недоступен из‑за ограничений провайдера. VPN создаёт зашифрованный канал до сервера за рубежом — мессенджер, звонки и медиа снова открываются в обычном режиме.',
          'Подорожник VPN использует VLESS и умную маршрутизацию: Telegram и другие зарубежные сервисы идут через туннель, а российские банки, Госуслуги и локальные приложения — напрямую, без выключения VPN.',
        ],
      },
      {
        heading: 'Преимущества Подорожник для Telegram',
        paragraphs: [
          'Стабильное соединение без постоянного «включить/выключить VPN» — split tunneling настроен на нашей стороне.',
          'До 5 устройств на одной подписке: телефон, компьютер и планшет.',
          'Пробный период 3 дня без привязки карты — проверьте звонки и загрузку файлов.',
        ],
      },
      {
        heading: 'Как начать пользоваться Telegram через VPN',
        paragraphs: [
          'Зарегистрируйтесь на сайте, получите конфигурацию в личном кабинете и подключите её в клиенте с поддержкой VLESS (Happ, V2Ray и др.).',
          'После подключения откройте Telegram на телефоне или в десктоп-приложении. Если нужна помощь с настройкой, напишите в поддержку 24/7.',
        ],
      },
    ],
  },
}
