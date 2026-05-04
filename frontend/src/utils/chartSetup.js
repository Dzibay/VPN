/**
 * Точечная регистрация только тех частей Chart.js, которые действительно используются,
 * вместо `chart.js/auto` (тянет все контроллеры/плагины).
 *
 * Используемые типы графиков: line, bar.
 * Плагины: Filler (заливка под линией), Tooltip, Legend, Title.
 * Шкалы: CategoryScale (ось X), LinearScale (ось Y).
 *
 * Импортируйте `Chart` отсюда; `registerCharts()` вызывается один раз при импорте.
 */
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Title,
  Tooltip,
} from 'chart.js'

let registered = false

function registerCharts() {
  if (registered) return
  Chart.register(
    LineController,
    LineElement,
    PointElement,
    BarController,
    BarElement,
    CategoryScale,
    LinearScale,
    Filler,
    Tooltip,
    Legend,
    Title,
  )
  registered = true
}

registerCharts()

export { Chart }
export default Chart
