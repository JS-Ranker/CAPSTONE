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

// Informe con error de extracción: corregir y enviar al ETL, volver a leerlo, o descartarlo / dejarlo pendiente.
const enviarJson = (url, cuerpo) => pedir(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo),
})
export const procesarDocumento = (id, cuerpo) => enviarJson(`/api/excepciones/documento/${id}/procesar`, cuerpo)
export const reextraerDocumento = (id, observacion) => enviarJson(
  `/api/excepciones/documento/${id}/reextraer`, { accion: 'reextraer', observacion })
export const revisarDocumento = (id, { accion, observacion }) => enviarJson(
  `/api/excepciones/documento/${id}/revisiones`, { accion, observacion })

// Módulo de IA (CU08): accion 'aplicar' (la validación sugerida) o 'revisar' (descartar).
export const revisarInsight = (id, { accion, observacion }) => pedir(`/api/ia/insights/${id}/revision`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accion, observacion }),
})

// Cruce con Banco Genérico (RF04): UTM del mes (periodo 'aaaa-mm') y cruce de un informe.
export const fijarUtm = (periodo, valor) => pedir(`/api/cruce/utm/${periodo}`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ valor }),
})
export const obtenerUtmOficial = (periodo) => pedir(`/api/cruce/utm/${periodo}/oficial`, { method: 'POST' })
export const cruzarInforme =(idArchivo) => pedir(`/api/cruce/informes/${idArchivo}/cruzar`, { method: 'POST' })

// Informe de respuesta a la TGR (RF07, RF11): descarga el Excel del cruce del informe.
export async function descargarRespuestaTgr(idArchivo) {
  let respuesta
  try {
    respuesta = await fetch(`/api/reportes/informes/${idArchivo}/respuesta-tgr.xlsx`)
  } catch {
    throw new ErrorApi('No se pudo conectar con la API. ¿Está ejecutándose el backend?', 0)
  }
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null)
    throw new ErrorApi(mensajeDeError(cuerpo, respuesta.status), respuesta.status, cuerpo?.detail)
  }
  const nombre = /filename\*=UTF-8''([^;]+)/.exec(respuesta.headers.get('content-disposition') ?? '')?.[1]
  const enlace = document.createElement('a')
  enlace.href = URL.createObjectURL(await respuesta.blob())
  enlace.download = nombre ? decodeURIComponent(nombre) : `respuesta_tgr_${idArchivo}.xlsx`
  enlace.click()
  URL.revokeObjectURL(enlace.href)
}
