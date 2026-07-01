/**
 * Контент SEO-страницы /vpn-dlya-youtube/android
 */
import { YOUTUBE_SEO_HERO_BG } from './vpn-dlya-youtube.js'

export const vpnDlyaYoutubeAndroidPage = {
  meta: {
    title: 'VPN для YouTube на Android — смотреть без блокировок | Подорожник VPN',
    description:
      'VPN для YouTube на Android за пару минут через Happ. Российские банки и Госуслуги работают без постоянного переключения. Пробный период 3 дня.',
  },
  hero: {
    badgeIcon: '/images/home/how/vpn/youtube.png',
    badgeText: 'VPN для YouTube на Android',
    titleLine1: 'YouTube на',
    titleHighlight: 'Android',
    titleLine2: 'без блокировок',
    lead:
      'Смотрите YouTube в приложении и браузере на телефоне — стабильно, быстро и без постоянного выключения VPN.',
    bgImage: YOUTUBE_SEO_HERO_BG,
    features: [
      {
        icon: 'Globe',
        title: 'Приложение и браузер',
        text: 'Работает в YouTube и Chrome',
      },
      {
        icon: 'Zap',
        title: 'Быстрое подключение',
        text: 'Импорт конфига в Happ за минуту',
      },
      {
        icon: 'Lock',
        title: 'Умная маршрутизация',
        text: 'Банки и Госуслуги — напрямую',
      },
    ],
  },
  article: {
    title: 'Как смотреть YouTube на Android через VPN',
    sections: [
      {
        heading: 'Почему на Android YouTube может не открываться',
        paragraphs: [
          'На мобильном интернете блокировки и throttling встречаются так же часто, как на ПК. VPN на Android направляет трафик к YouTube через защищённый канал — приложение и сайт снова открываются стабильно.',
        ],
      },
      {
        heading: 'Настройка Подорожник на Android',
        paragraphs: [
          'После регистрации скопируйте ссылку подписки из личного кабинета и добавьте её в клиент Happ (или другой с поддержкой VLESS). Подключитесь — YouTube начнёт работать через VPN, а российские сервисы останутся на прямом соединении.',
          'На одной подписке до 5 устройств: можно подключить и телефон, и планшет.',
        ],
      },
    ],
  },
}
