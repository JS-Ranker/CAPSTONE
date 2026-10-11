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
    <section className="tarjeta" aria-labelledby="titulo-lotes">
      <div className="tarjeta__cabecera">
        <h2 id="titulo-lotes">Lotes recientes</h2>
        <div className="actualizacion">
          {actualizadoEn && (
            <span className="nota" role="status" aria-live="polite">
              Actualizado a las {hora.format(actualizadoEn)}
            </span>
          )}
          {/* Actualiza toda la pantalla: esta tabla y el panel de recepción automática */}
          <button type="button" className="boton boton--secundario" onClick={onActualizar} disabled={cargando}>
            {cargando ? 'Actualizando…' : 'Actualizar'}
          </button>
        </div>
      </div>

      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && datos && archivos.length === 0 && (
        <p className="vacio">Aún no se ha recibido ningún documento. Cargue uno arriba o lea la casilla de correo.</p>
      )}

      {archivos.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla">
            <thead>
              <tr>
                <th scope="col">ID Lote</th>
                <th scope="col">Nombre de archivo</th>
                <th scope="col">Origen</th>
                <th scope="col">Fecha de recepción</th>
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
                    <button type="button" className="boton boton--secundario" onClick={() => onVerDetalle(archivo)}>
                      Ver detalle<span className="oculto"> de {archivo.nombre_archivo}</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {paginas > 1 && (
        <nav className="paginacion" aria-label="Páginas de lotes">
          <button type="button" className="boton boton--secundario" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>
            Anterior
          </button>
          <span>Página {pagina + 1} de {paginas}</span>
          <button type="button" className="boton boton--secundario" disabled={pagina + 1 >= paginas} onClick={() => setPagina(pagina + 1)}>
            Siguiente
          </button>
        </nav>
      )}
      {hayPendientes && <p className="nota">Hay documentos convirtiéndose con OCR: la tabla se actualiza sola.</p>}
    </section>
  )
}
