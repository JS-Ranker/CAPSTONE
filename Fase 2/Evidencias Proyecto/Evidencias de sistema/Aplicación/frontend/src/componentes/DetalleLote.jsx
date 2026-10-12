import { useEffect, useRef, useState } from 'react'
import { procesarArchivo } from '../api'
import { formatearFecha, formatearNumero, formatearPorcentaje } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoArchivo } from './EstadoArchivo'
import { Icono } from './Icono'

// Resultado del ETL de un CSV. Los que llegan por correo o SFTP se procesan desde aquí con "Procesar".
function ResultadoEtl({ archivo, onProcesado, onVerCasos }) {
  const { datos, error, recargar } = usePeticion(`/api/etl/archivos/${archivo.id_archivo}`)
  const [accion, setAccion] = useState({ tipo: 'inactivo', mensaje: '' })
  const procesando = accion.tipo === 'procesando'
  const sinProcesar = error?.estado === 404

  async function procesar() {
    if (procesando) return
    setAccion({ tipo: 'procesando', mensaje: 'Procesando…' })
    try {
      const resumen = await procesarArchivo(archivo.id_archivo)
      setAccion({ tipo: 'exito', mensaje: `Listo: ${formatearNumero(resumen.cargadas)} casos cargados.` })
      onProcesado(resumen)
      recargar()
    } catch (falla) {
      setAccion({ tipo: 'error', mensaje: falla.message })
    }
  }

  return (
    <div className="grupo">
      <h3 className="grupo__titulo">Resultado del ETL</h3>
      {datos && (
        <>
          <dl className="lista-datos">
            <div><dt>Casos cargados</dt><dd>{formatearNumero(datos.cargadas)}</dd></div>
            <div><dt>Rechazados</dt><dd>{formatearNumero(datos.rechazadas)}</dd></div>
            <div><dt>Duplicados</dt><dd>{formatearNumero(datos.duplicadas)}</dd></div>
            <div><dt>Por revisar</dt><dd>{formatearNumero(archivo.por_revisar ?? 0)}</dd></div>
          </dl>
          <p className="enlaces">
            <a href={`#/casos?informe=${archivo.id_archivo}`} onClick={onVerCasos}>Ver los deudores de este informe</a>
            {archivo.por_revisar > 0 && (
              <a href={`#/excepciones?informe=${archivo.id_archivo}`} onClick={onVerCasos}>
                Revisar {archivo.por_revisar === 1 ? 'el pendiente' : `los ${formatearNumero(archivo.por_revisar)} pendientes`}
              </a>
            )}
          </p>
        </>
      )}
      {sinProcesar && archivo.estado_archivo === 'Error' && (
        <p className="aviso aviso--error">El CSV tiene errores de formato y no se cargó ningún caso.</p>
      )}
      {sinProcesar && archivo.estado_archivo !== 'Error' && (
        <div className="acciones acciones--centradas">
          <p className="nota">Este CSV aún no pasa por el ETL.</p>
          <button type="button" className="boton" onClick={procesar} aria-disabled={procesando || undefined}>
            {procesando ? 'Procesando…' : 'Procesar'}
          </button>
        </div>
      )}
      {error && !sinProcesar && (
        <p className="aviso aviso--error">
          No se pudo cargar. <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      <p className={`aviso aviso--${accion.tipo}`} role="status" aria-live="polite">{accion.mensaje}</p>
    </div>
  )
}


// Texto de cada acción de la bitácora, para leerla sin conocer su formato.
function describir({ accion, detalle: d }) {
  switch (accion) {
    case 'Recepción de documento':
      return [`Llegó por ${String(d.canal ?? '').toLowerCase()}${d.remitente ? ` desde ${d.remitente}` : ''}`
        + `${d.asunto ? `, asunto «${d.asunto}»` : ''}.`]
    case 'Extracción de documento': {
      const resumen = [`Resultado: ${d.estado}`, `${formatearNumero(d.registros)} registros leídos`]
      if (d.registros_en_revision) resumen.push(`${formatearNumero(d.registros_en_revision)} bajo el 90 % de confianza`)
      if (d.confianza_promedio !== null && d.confianza_promedio !== undefined) {
        resumen.push(`confianza promedio ${formatearPorcentaje(d.confianza_promedio)}`)
      }
      return [`${resumen.join(' · ')}.`, ...(d.errores ?? []), ...(d.observaciones ?? [])]
    }
    case 'Ejecución ETL':
      return [`${formatearNumero(d.cargadas)} casos cargados, ${formatearNumero(d.rechazadas)} rechazados y `
        + `${formatearNumero(d.duplicadas)} duplicados.`]
    case 'Ejecución ETL rechazada':
      return [`No se cargó: ${d.motivo}`]
    default:
      return []
  }
}

function HistorialLote({ historial, error, onReintentar }) {
  if (error) {
    return (
      <p className="aviso aviso--error">
        No se pudo cargar el historial. <button type="button" className="enlace" onClick={onReintentar}>Reintentar</button>
      </p>
    )
  }
  if (!historial) return <p className="nota">Cargando…</p>
  if (historial.length === 0) return <p className="nota">Sin registros en la bitácora.</p>
  return (
    <ol className="historial">
      {historial.map((registro) => {
        const [principal, ...detalles] = describir(registro)
        return (
          <li key={registro.id_bitacora} className="historial__item">
            <div className="historial__cabecera">
              <strong className="historial__accion">{registro.accion}</strong>
              <span className="nota">{formatearFecha(registro.fecha)} · {registro.usuario}</span>
            </div>
            {principal && <p className="historial__texto">{principal}</p>}
            {detalles.length > 0 && (
              <ul className="historial__cambios">
                {detalles.map((texto) => <li key={texto}>{texto}</li>)}
              </ul>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function ContenidoLote({ archivo, onProcesado, onCerrar }) {
  // Se vuelve a pedir cuando cambia el estado (por ejemplo, al procesar el CSV desde este mismo diálogo).
  const { datos: historial, error, recargar } = usePeticion(
    `/api/recepcion/archivos/${archivo.id_archivo}/historial`, archivo.estado_archivo,
  )
  const extracciones = (historial ?? []).filter((registro) => registro.accion === 'Extracción de documento')
  const motivos = extracciones.at(-1)?.detalle.errores ?? []
  const visible = ['PDF con texto', 'PDF escaneado', 'Imagen'].includes(archivo.tipo_documento)

  return (
    <>
      <div className="dialogo__cabecera">
        <h2 id="titulo-detalle">Informe #{archivo.id_archivo}</h2>
        <button type="button" className="boton boton--compacto" onClick={onCerrar}>Cerrar</button>
      </div>
      {archivo.estado_archivo === 'Error de Extracción' && (
        <div className="aviso aviso--error">
          <p className="aviso__titulo">No se pudo leer bien: debe revisarse a mano.</p>
          {motivos.length > 0 && <ul className="aviso__lista">{motivos.map((m) => <li key={m}>{m}</li>)}</ul>}
        </div>
      )}
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
        {archivo.tipo_documento !== 'CSV' && (
          <div><dt>Confianza OCR</dt><dd>{formatearPorcentaje(archivo.confianza_extraccion)}</dd></div>
        )}
      </dl>
      <div className="documento">
        <a
          className="boton"
          href={`/api/recepcion/archivos/${archivo.id_archivo}/documento`}
          target={visible ? '_blank' : undefined}
          rel={visible ? 'noopener noreferrer' : undefined}
        >
          <Icono nombre="archivo" tamano={18} /> {visible ? 'Ver documento' : 'Descargar archivo'}
        </a>
        <span className="nota">{visible ? 'Se abre en otra pestaña, para compararlo con lo extraído.' : 'Tal como llegó.'}</span>
      </div>
      {(archivo.tipo_documento === 'CSV' || archivo.estado_archivo === 'Procesado') && (
        <ResultadoEtl archivo={archivo} onProcesado={onProcesado} onVerCasos={onCerrar} />
      )}
      <div className="grupo">
        <h3 className="grupo__titulo">Historial</h3>
        <HistorialLote historial={historial} error={error} onReintentar={recargar} />
      </div>
    </>
  )
}

// Detalle de un lote en un diálogo nativo (atrapa el foco, se cierra con Escape y devuelve el foco al botón).
export function DetalleLote({ archivo, onCerrar, onProcesado }) {
  const dialogo = useRef(null)

  useEffect(() => {
    const elemento = dialogo.current
    if (archivo && !elemento.open) elemento.showModal()
    if (!archivo && elemento.open) elemento.close()
  }, [archivo])

  return (
    <dialog ref={dialogo} className="dialogo" aria-labelledby="titulo-detalle" onClose={onCerrar}>
      {archivo && (
        <ContenidoLote
          key={archivo.id_archivo}
          archivo={archivo}
          onProcesado={onProcesado}
          onCerrar={() => dialogo.current.close()}
        />
      )}
    </dialog>
  )
}
