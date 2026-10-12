import { useEffect, useState } from 'react'
import { formatearFecha, formatearNumero, formatearPorcentaje } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoArchivo } from './EstadoArchivo'

const POR_PAGINA = 10
const INTERVALO_ACTUALIZACION = 4000 // ms, solo mientras haya documentos convirtiéndose con OCR

const hora = new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })

export function TablaLotes({ version, onVerDetalle, onActualizar }) {
  const [pagina, setPagina] = useState(0)
  const { datos, error, cargando, actualizadoEn, recargar } = usePeticion(
    `/api/recepcion/archivos?limite=${POR_PAGINA}&desplazamiento=${pagina * POR_PAGINA}`, version,
  )
  const archivos = datos?.archivos ?? []
  const hayPendientes = archivos.some((archivo) => archivo.estado_archivo === 'Pendiente de Extracción')
  const paginas = Math.max(1, Math.ceil((datos?.total ?? 0) / POR_PAGINA))

  useEffect(() => {
    if (!hayPendientes) return undefined
    const temporizador = setInterval(recargar, INTERVALO_ACTUALIZACION)
    return () => clearInterval(temporizador)
  }, [hayPendientes, recargar])

  return (
    <section className="tarjeta tarjeta--lotes" aria-labelledby="titulo-lotes">
      <div className="tarjeta__cabecera">
        <div>
          <h2 id="titulo-lotes">Lotes recientes</h2>
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
          {/* Sin live region: mientras hay OCR en curso se actualiza cada 4 s y anunciaría la hora una y otra vez */}
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
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">Lote</th>
                <th scope="col">Archivo</th>
                <th scope="col">Canal</th>
                <th scope="col">Recibido</th>
                <th scope="col" className="numero">Registros</th>
                <th scope="col" className="numero">Confianza OCR</th>
                <th scope="col">Estado</th>
                <th scope="col"><span className="oculto">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {archivos.map((archivo) => (
                <tr key={archivo.id_archivo}>
                  <td className="id">#{archivo.id_archivo}</td>
                  <td className="nombre">{archivo.nombre_archivo}</td>
                  <td>{archivo.canal_origen}</td>
                  <td>{formatearFecha(archivo.fecha_recepcion)}</td>
                  <td className="numero">{formatearNumero(archivo.total_registros)}</td>
                  <td className="numero">{formatearPorcentaje(archivo.confianza_extraccion)}</td>
                  <td><EstadoArchivo estado={archivo.estado_archivo} /></td>
                  <td>
                    <button type="button" className="boton boton--compacto boton--fantasma" onClick={() => onVerDetalle(archivo)}>
                      Ver detalle<span className="oculto"> de {archivo.nombre_archivo}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* En una tarjeta angosta la tabla escondería Estado y Ver detalle tras un scroll horizontal:
          se muestra esta lista en su lugar (el CSS deja visible solo una de las dos). */}
      {archivos.length > 0 && (
        <ul className="lotes-lista" aria-label="Lotes recientes">
          {archivos.map((archivo) => (
            <li key={archivo.id_archivo} className="lotes-lista__item">
              <div className="lotes-lista__cabecera">
                <span className="nombre lotes-lista__nombre">{archivo.nombre_archivo}</span>
                <EstadoArchivo estado={archivo.estado_archivo} />
              </div>
              <p className="nota">
                <span className="id">#{archivo.id_archivo}</span> · {archivo.canal_origen} · {formatearFecha(archivo.fecha_recepcion)}
              </p>
              <dl className="lotes-lista__datos">
                <div><dt>Registros</dt><dd>{formatearNumero(archivo.total_registros)}</dd></div>
                <div><dt>Confianza OCR</dt><dd>{formatearPorcentaje(archivo.confianza_extraccion)}</dd></div>
              </dl>
              <button type="button" className="boton boton--compacto lotes-lista__boton" onClick={() => onVerDetalle(archivo)}>
                Ver detalle<span className="oculto"> de {archivo.nombre_archivo}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {paginas > 1 && (
        <nav className="paginacion" aria-label="Páginas de lotes">
          <button type="button" className="boton boton--compacto" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>
            Anterior
          </button>
          <span>Página {pagina + 1} de {paginas}</span>
          <button type="button" className="boton boton--compacto" disabled={pagina + 1 >= paginas} onClick={() => setPagina(pagina + 1)}>
            Siguiente
          </button>
        </nav>
      )}
      {hayPendientes && <p className="nota">Lectura OCR en curso: la tabla se actualiza sola.</p>}
    </section>
  )
}
