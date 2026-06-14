/**
 * Точечная регистрация только тех частей Chart.js, которые действительно используются,
 * вместо `chart.js/auto` (тянет все контроллеры/плагины).
 *
 * Используемые типы графиков: line, bar, doughnut (структура расходов в бухгалтерии).
 * Плагины: Filler (заливка под линией), Tooltip, Legend, Title.
 * Шкалы: CategoryScale (ось X), LinearScale (ось Y).
 *
 * Импортируйте `Chart` отсюда; `registerCharts()` вызывается один раз при импорте.
 */
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js'

import { staffChartMarkersPlugin } from './chartStaffMarkersPlugin.js'
import { barStackTopLabelsPlugin } from './chartBarStackTopLabelsPlugin.js'

let registered = false

function registerCharts() {
  if (registered) return
  Chart.register(
    LineController,
    LineElement,
    PointElement,
    BarController,
    BarElement,
    DoughnutController,
    ArcElement,
    CategoryScale,
    LinearScale,
    Filler,
    Tooltip,
    Legend,
    Title,
    staffChartMarkersPlugin,
    barStackTopLabelsPlugin,
  )
  registered = true
}

registerCharts()

export { Chart }
export default Chart
