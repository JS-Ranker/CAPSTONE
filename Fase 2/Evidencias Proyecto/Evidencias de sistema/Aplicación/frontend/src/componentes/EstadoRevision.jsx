// Estado de una excepción, con el texto siempre visible (no depende solo del color).
const TONOS = { Pendiente: 'advertencia', 'Resuelto Manual': 'exito', Descartado: 'neutro' }

export function EstadoRevision({ estado }) {
  return <span className={`etiqueta etiqueta--${TONOS[estado] ?? 'neutro'}`}>{estado}</span>
}
