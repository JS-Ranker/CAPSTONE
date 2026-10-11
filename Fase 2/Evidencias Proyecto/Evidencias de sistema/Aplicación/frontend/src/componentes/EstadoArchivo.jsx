// Estado de Archivos_TGR como etiqueta de color (el texto siempre está visible: no depende solo del color).
const TONOS = {
  Recibido: 'neutro',
  'Pendiente de Extracción': 'advertencia',
  Normalizado: 'info',
  Procesado: 'exito',
  'Error de Extracción': 'error',
  Error: 'error',
}

export function EstadoArchivo({ estado }) {
  return <span className={`etiqueta etiqueta--${TONOS[estado] ?? 'neutro'}`}>{estado}</span>
}
