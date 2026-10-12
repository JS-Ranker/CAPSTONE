// Formatos de presentación (Chile).

const fechaHora = new Intl.DateTimeFormat('es-CL', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const numero = new Intl.NumberFormat('es-CL')

// La API entrega fechas sin zona horaria en hora local del servidor ("2026-10-10T19:40:12").
export function formatearFecha(texto) {
  if (!texto) return '—'
  const fecha = new Date(texto)
  return Number.isNaN(fecha.getTime()) ? '—' : fechaHora.format(fecha).replace(',', '')
}

export const formatearNumero = (valor) => (valor === null || valor === undefined ? '—' : numero.format(valor))

export const formatearPorcentaje = (valor) =>
  valor === null || valor === undefined ? '—' : `${numero.format(Math.round(Number(valor)))} %`

const pesos = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' })
export const formatearMonto = (valor) => (valor === null || valor === undefined ? '—' : pesos.format(Number(valor)))

// Fechas sin hora ("2026-10-12"): se arman a mano, porque new Date() las lee en UTC y en Chile mostraría el día anterior.
export function formatearDia(texto) {
  const [anio, mes, dia] = String(texto ?? '').slice(0, 10).split('-')
  return anio && mes && dia ? `${dia}-${mes}-${anio}` : '—'
}

// RUT con puntos y guion: 46822128 + "4" -> 46.822.128-4
export const formatearRut = (rut, dv) => (rut ? `${numero.format(Number(rut))}-${dv}` : '—')
