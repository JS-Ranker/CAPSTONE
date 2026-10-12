// Llamadas a la API (en desarrollo, Vite redirige /api al backend: ver vite.config.js).

export class ErrorApi extends Error {
  constructor(mensaje, estado, detalle) {
    super(mensaje)
    this.estado = estado
    this.detalle = detalle
  }
}

// Mensaje entendible para el usuario a partir de la respuesta de FastAPI ({ detail: ... }).
function mensajeDeError(cuerpo, estado) {
  const detalle = cuerpo?.detail
  if (typeof detalle === 'string') return detalle
  if (detalle?.mensaje) return detalle.mensaje
  if (estado === 422) return 'La solicitud no es válida.'
  return 'Ocurrió un error en el servidor. Intente nuevamente.'
}

export async function pedir(url, opciones = {}) {
  let respuesta
  try {
    respuesta = await fetch(url, opciones)
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ErrorApi('No se pudo conectar con la API. ¿Está ejecutándose el backend?', 0)
  }
  const cuerpo = await respuesta.json().catch(() => null)
  if (!respuesta.ok) {
    throw new ErrorApi(mensajeDeError(cuerpo, respuesta.status), respuesta.status, cuerpo?.detail)
  }
  return cuerpo
}

export function subirDocumento(archivo) {
  const datos = new FormData()
  datos.append('archivo', archivo)
  return pedir('/api/recepcion/archivos', { method: 'POST', body: datos })
}

export const revisarCorreo = () => pedir('/api/recepcion/revisar/correo', { method: 'POST' })
export const revisarSftp = () => pedir('/api/recepcion/revisar/sftp', { method: 'POST' })

export const listarRemitentes = () => pedir('/api/recepcion/remitentes')
export const agregarRemitente = (correo, nombre) => pedir('/api/recepcion/remitentes', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ correo, nombre }),
})
export const quitarRemitente = (id) => pedir(`/api/recepcion/remitentes/${id}`, { method: 'DELETE' })

export const procesarArchivo = (idArchivo) => pedir(`/api/etl/archivos/${idArchivo}`, { method: 'POST' })

// Bandeja de Excepciones (CU05). tipo: 'caso' | 'rechazo'.
export const revisarExcepcion = (tipo, id, { accion, observacion, datos }) => pedir(
  `/api/excepciones/${tipo}/${id}/revisiones`,
  { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accion, observacion, datos }) },
)
