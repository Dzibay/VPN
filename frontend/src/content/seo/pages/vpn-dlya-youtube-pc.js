/**
 * Контент SEO-страницы /vpn-dlya-youtube/pc
 */
import { YOUTUBE_SEO_HERO_BG } from './vpn-dlya-youtube.js'

export const vpnDlyaYoutubePcPage = {
  meta: {
    title: 'VPN для YouTube на ПК — Windows и macOS | Подорожник VPN',
    description:
      'VPN для YouTube на компьютере: браузер и десктоп-клиент. Российские банки и Госуслуги — без постоянного переключения VPN. Пробный период 3 дня.',
  },
  hero: {
    badgeIcon: '/images/home/how/vpn/youtube.png',
    badgeText: 'VPN для YouTube на ПК',
    titleLine1: 'YouTube на',
    titleHighlight: 'компьютере',
    titleLine2: 'без блокировок',
    lead:
      'Смотрите YouTube в браузере и десктоп-приложении на Windows и macOS — в 4K и без ограничений скорости.',
    bgImage: YOUTUBE_SEO_HERO_BG,
    features: [
      {
        icon: 'Globe',
        title: 'Браузер и приложение',
        text: 'Chrome, Edge, YouTube Desktop',
      },
      {
        icon: 'Zap',
        title: '4K без буферизации',
        text: 'Стабильные серверы для видео',
      },
      {
        icon: 'Lock',
        title: 'Умная маршрутизация',
        text: 'Локальные сайты без VPN',
      },
    ],
  },
  article: {
    title: 'VPN для YouTube на Windows и macOS',
    sections: [
      {
        heading: 'YouTube на ПК через VPN',
        paragraphs: [
          'На компьютере YouTube часто открывают в браузере или официальном приложении. VPN создаёт зашифрованный туннель — видео загружается без региональных ограничений и просадок из‑за блокировок провайдера.',
        ],
      },
      {
        heading: 'Подключение Подорожник на компьютере',
        paragraphs: [
          'Импортируйте конфигурацию VLESS из личного кабинета в поддерживаемый клиент (Happ, V2Ray и др.). После подключения обновите страницу YouTube — контент должен открываться в обычном режиме.',
          'Split tunneling настроен на нашей стороне: банки, Госуслуги и локальные сервисы не идут через VPN, поэтому не нужно отключать защиту вручную.',
        ],
      },
    ],
  },
}
