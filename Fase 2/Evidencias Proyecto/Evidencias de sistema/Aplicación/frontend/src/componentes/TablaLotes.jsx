import { useEffect, useState } from 'react'
import { formatearFecha, formatearNumero, formatearPorcentaje } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoArchivo } from './EstadoArchivo'
import { Paginacion } from './Paginacion'

const POR_PAGINA = 10
const INTERVALO_ACTUALIZACION = 4000 // ms, solo mientras haya informes leyéndose

const hora = new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })

// Solo los escaneos y las fotos se leen con OCR: en Excel, Word o PDF con texto la confianza no aporta.
const usaOcr = (archivo) => ['PDF escaneado', 'Imagen'].includes(archivo.tipo_documento)

// Deudores del informe que esperan revisión manual, con enlace a la Bandeja filtrada por ese informe.
function PorRevisar({ archivo }) {
  if (!archivo.por_revisar) return <span className="nota">—</span>
  return (
    <a href={`#/excepciones?informe=${archivo.id_archivo}`}>
      {formatearNumero(archivo.por_revisar)}<span className="oculto"> por revisar del informe #{archivo.id_archivo}</span>
    </a>
  )
}

export function TablaLotes({ version, onVerDetalle, onActualizar }) {
  const [pagina, setPagina] = useState(0)
  const { datos, error, cargando, actualizadoEn, recargar } = usePeticion(
    `/api/recepcion/archivos?limite=${POR_PAGINA}&desplazamiento=${pagina * POR_PAGINA}`, version,
  )
  const archivos = datos?.archivos ?? []
  const hayPendientes = archivos.some((archivo) => archivo.estado_archivo === 'Pendiente de Extracción')

  useEffect(() => {
    if (!hayPendientes) return undefined
    const temporizador = setInterval(recargar, INTERVALO_ACTUALIZACION)
    return () => clearInterval(temporizador)
  }, [hayPendientes, recargar])

  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-lotes">
      <div className="tarjeta__cabecera">
        <div>
          <h2 id="titulo-lotes">Informes recibidos</h2>
          {datos && (
            <p className="nota">
              {formatearNumero(datos.total)} {datos.total === 1 ? 'documento' : 'documentos'}
              {datos.con_error > 0 && (
                <span className="nota__error">
                  {' · '}{formatearNumero(datos.con_error)} con error
                </span>
              )}
            </p>
          )}
        </div>
        <div className="actualizacion">
          {/* Sin live region: mientras se leen informes se actualiza cada 4 s y anunciaría la hora una y otra vez */}
          {(cargando || actualizadoEn) && (
            <span className="nota">
              {cargando ? 'Actualizando…' : `Actualizado ${hora.format(actualizadoEn)}`}
            </span>
          )}
          {/* Actualiza toda la pantalla: esta tabla y el panel de recepción automática.
              No se deshabilita: un botón deshabilitado con el foco encima lo pierde. Repetirlo solo reinicia la petición. */}
          <button type="button" className="boton boton--compacto" onClick={onActualizar}>
            Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && datos && archivos.length === 0 && (
        <p className="vacio">Aún no hay documentos. Cargue uno o lea el correo.</p>
      )}

      {archivos.length > 0 && (
        <div className="tabla-contenedor">
          {/* 6 columnas: canal va bajo la fecha y la confianza OCR bajo los deudores. El nombre del archivo abre el
              detalle. Así la tabla cabe sin scroll lateral desde ~700 px; más angosto se muestra la lista apilada. */}
          <table className="tabla tabla--informes">
            <thead>
              <tr>
                <th scope="col">N°</th>
                <th scope="col">Archivo</th>
                <th scope="col">Recibido</th>
                <th scope="col" className="numero">Deudores</th>
                <th scope="col">Estado</th>
                <th scope="col" className="numero">Por revisar</th>
              </tr>
            </thead>
            <tbody>
              {archivos.map((archivo) => (
                <tr key={archivo.id_archivo}>
                  <td className="id">#{archivo.id_archivo}</td>
                  <td className="nombre">
                    <button type="button" className="enlace enlace--archivo" onClick={() => onVerDetalle(archivo)}>
                      <span className="oculto">Ver detalle de </span>{archivo.nombre_archivo}
                    </button>
                  </td>
                  <td>
                    {formatearFecha(archivo.fecha_recepcion)}
                    <span className="nota bloque">{archivo.canal_origen}</span>
                  </td>
                  <td className="numero">
                    {formatearNumero(archivo.total_registros)}
                    {usaOcr(archivo) && (
                      <span className="nota bloque">OCR {formatearPorcentaje(archivo.confianza_extraccion)}</span>
                    )}
                  </td>
                  <td><EstadoArchivo estado={archivo.estado_archivo} /></td>
                  <td className="numero"><PorRevisar archivo={archivo} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* En una tarjeta angosta la tabla escondería Estado y Ver detalle tras un scroll horizontal:
          se muestra esta lista en su lugar (el CSS deja visible solo una de las dos). */}
      {archivos.length > 0 && (
        <ul className="lista-apilada" aria-label="Informes recibidos">
          {archivos.map((archivo) => (
            <li key={archivo.id_archivo} className="lista-apilada__item">
              <div className="lista-apilada__cabecera">
                <span className="nombre lista-apilada__nombre">{archivo.nombre_archivo}</span>
                <EstadoArchivo estado={archivo.estado_archivo} />
              </div>
              <p className="nota">
                <span className="id">#{archivo.id_archivo}</span> · {archivo.canal_origen} · {formatearFecha(archivo.fecha_recepcion)}
              </p>
              <dl className="lista-apilada__datos">
                <div><dt>Registros</dt><dd>{formatearNumero(archivo.total_registros)}</dd></div>
                {usaOcr(archivo) && <div><dt>Confianza OCR</dt><dd>{formatearPorcentaje(archivo.confianza_extraccion)}</dd></div>}
                <div><dt>Por revisar</dt><dd><PorRevisar archivo={archivo} /></dd></div>
              </dl>
              <button type="button" className="boton boton--compacto lista-apilada__boton" onClick={() => onVerDetalle(archivo)}>
                Ver detalle<span className="oculto"> de {archivo.nombre_archivo}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Paginacion
        pagina={pagina}
        total={datos?.total ?? 0}
        porPagina={POR_PAGINA}
        onCambiar={setPagina}
        etiqueta="Páginas de informes"
      />
      {hayPendientes && <p className="nota">Leyendo informes: la tabla se actualiza sola.</p>}
    </section>
  )
}
