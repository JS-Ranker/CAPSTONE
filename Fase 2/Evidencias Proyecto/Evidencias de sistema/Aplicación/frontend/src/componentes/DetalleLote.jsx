import { useEffect, useRef } from 'react'
import { formatearFecha, formatearNumero, formatearPorcentaje } from '../formato'
import { EstadoArchivo } from './EstadoArchivo'

// Detalle de un lote en un diálogo nativo (atrapa el foco, se cierra con Escape y devuelve el foco al botón).
export function DetalleLote({ archivo, onCerrar }) {
  const dialogo = useRef(null)

  useEffect(() => {
    const elemento = dialogo.current
    if (archivo && !elemento.open) elemento.showModal()
    if (!archivo && elemento.open) elemento.close()
  }, [archivo])

  return (
    <dialog ref={dialogo} className="dialogo" aria-labelledby="titulo-detalle" onClose={onCerrar}>
      {archivo && (
        <>
          <div className="dialogo__cabecera">
            <h2 id="titulo-detalle">Lote #{archivo.id_archivo}</h2>
            <button type="button" className="boton boton--compacto" onClick={() => dialogo.current.close()}>
              Cerrar
            </button>
          </div>
          <dl className="lista-datos">
            <div><dt>Archivo</dt><dd className="nombre">{archivo.nombre_archivo}</dd></div>
            <div><dt>Estado</dt><dd><EstadoArchivo estado={archivo.estado_archivo} /></dd></div>
            <div><dt>Tipo</dt><dd>{archivo.tipo_documento}</dd></div>
            <div><dt>Canal</dt><dd>{archivo.canal_origen}</dd></div>
            <div><dt>Recibido</dt><dd>{formatearFecha(archivo.fecha_recepcion)}</dd></div>
            {archivo.canal_origen === 'Correo' && (
              <>
                <div><dt>Remitente</dt><dd className="nombre">{archivo.remitente}</dd></div>
                <div><dt>Asunto</dt><dd className="nombre">{archivo.asunto_correo ?? '—'}</dd></div>
                <div><dt>Fecha del correo</dt><dd>{formatearFecha(archivo.fecha_correo)}</dd></div>
              </>
            )}
            <div><dt>Registros</dt><dd>{formatearNumero(archivo.total_registros)}</dd></div>
            <div><dt>Confianza OCR</dt><dd>{formatearPorcentaje(archivo.confianza_extraccion)}</dd></div>
          </dl>
          {archivo.estado_archivo === 'Error de Extracción' && (
            <p className="aviso aviso--error">
              No se pudo leer bien o los totales no cuadran. Revíselo a mano.
            </p>
          )}
        </>
      )}
    </dialog>
  )
}
