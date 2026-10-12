import { useCallback, useState } from 'react'
import { TIPOS, rutOriginal as rutDe } from '../excepciones'
import { formatearFecha, formatearNumero } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoRevision } from './EstadoRevision'
import { FiltroInforme } from './FiltroInforme'
import { Paginacion } from './Paginacion'
import { RevisionExcepcion } from './RevisionExcepcion'

const POR_PAGINA = 20

// Bandeja de Excepciones (CU05): casos marcados para revisión manual y filas que el ETL rechazó.
// Con `informe` (desde la dirección #/excepciones?informe=808) muestra solo las excepciones de ese informe.
export function PantallaExcepciones({ informe }) {
  const [texto, setTexto] = useState('')
  const [filtro, setFiltro] = useState({ tipo: '', estado: 'Pendiente', buscar: '' })
  const [pagina, setPagina] = useState(0)
  const [version, setVersion] = useState(0)
  const [abierta, setAbierta] = useState(null) // { tipo, id }
  const actualizar = useCallback(() => setVersion((n) => n + 1), [])

  const parametros = new URLSearchParams({ limite: POR_PAGINA, desplazamiento: pagina * POR_PAGINA })
  for (const [clave, valor] of Object.entries(filtro)) if (valor) parametros.set(clave, valor)
  if (informe) parametros.set('informe', informe)
  const { datos, error, recargar } = usePeticion(`/api/excepciones?${parametros}`, version)
  const excepciones = datos?.excepciones ?? []
  const pendientes = datos ? datos.pendientes.caso + datos.pendientes.rechazo : 0

  function filtrar(cambios) {
    setFiltro((previo) => ({ ...previo, ...cambios }))
    setPagina(0)
  }

  return (
    <>
      <FiltroInforme modulo="excepciones" informe={informe} otro={{ modulo: 'casos', texto: 'Ver sus casos' }} />
      <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-excepciones">
        <div className="tarjeta__cabecera">
          <div>
            <h2 id="titulo-excepciones">Excepciones</h2>
            <p className="nota" role="status">
              {datos && (pendientes === 0
                ? 'No hay excepciones pendientes.'
                : `${formatearNumero(pendientes)} pendientes: ${formatearNumero(datos.pendientes.caso)} para revisión, `
                  + `${formatearNumero(datos.pendientes.rechazo)} rechazadas`)}
            </p>
          </div>
          <form
            className="filtros"
            role="search"
            onSubmit={(evento) => { evento.preventDefault(); filtrar({ buscar: texto.trim() }) }}
          >
            <div className="campo">
              <label htmlFor="filtro-tipo">Tipo</label>
              <select id="filtro-tipo" value={filtro.tipo} onChange={(evento) => filtrar({ tipo: evento.target.value })}>
                <option value="">Todos</option>
                <option value="caso">{TIPOS.caso}</option>
                <option value="rechazo">{TIPOS.rechazo}</option>
              </select>
            </div>
            <div className="campo">
              <label htmlFor="filtro-estado">Estado</label>
              <select id="filtro-estado" value={filtro.estado} onChange={(evento) => filtrar({ estado: evento.target.value })}>
                <option value="Pendiente">Pendientes</option>
                <option value="Resuelto Manual">Resueltos</option>
                <option value="Descartado">Descartados</option>
                <option value="">Todos</option>
              </select>
            </div>
            <div className="campo">
              <label htmlFor="buscar-excepciones">Buscar</label>
              <div className="filtros__busqueda">
                <input
                  id="buscar-excepciones"
                  type="search"
                  value={texto}
                  onChange={(evento) => setTexto(evento.target.value)}
                  placeholder="RUT, nombre o rol"
                  maxLength={100}
                />
                <button type="submit" className="boton">Buscar</button>
              </div>
            </div>
          </form>
        </div>
  
        {error && (
          <p className="aviso aviso--error">
            {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
          </p>
        )}
        {!error && !datos && <p className="nota">Cargando…</p>}
        {!error && datos && excepciones.length === 0 && (
          <p className="vacio">
            {filtro.estado === 'Pendiente' && !filtro.buscar && !filtro.tipo
              ? 'Todo al día: no hay excepciones pendientes.'
              : 'Ninguna excepción coincide con los filtros.'}
          </p>
        )}
  
        {excepciones.length > 0 && (
          <>
            <div className="tabla-contenedor">
              <table className="tabla" aria-labelledby="titulo-excepciones">
                <thead>
                  <tr>
                    <th scope="col">Motivo</th>
                    <th scope="col">RUT</th>
                    <th scope="col">Cliente</th>
                    <th scope="col">Informe</th>
                    <th scope="col">Estado</th>
                    <th scope="col"><span className="oculto">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {excepciones.map((fila) => (
                    <tr key={`${fila.tipo}-${fila.id}`}>
                      <td className="nombre">
                        <span className="motivo">{fila.motivo}</span>
                        <span className="nota bloque">{TIPOS[fila.tipo]}</span>
                      </td>
                      <td className="sin-salto">{rutDe(fila)}</td>
                      <td className="nombre">{fila.nom_cli || '—'}</td>
                      <td className="nombre">
                        {fila.id_informe && <a href={`#/excepciones?informe=${fila.id_informe}`}>#{fila.id_informe}</a>}
                        {' '}{fila.archivo_origen ?? '—'}
                        <span className="nota bloque">{formatearFecha(fila.fecha)}</span>
                      </td>
                      <td><EstadoRevision estado={fila.estado} /></td>
                      <td>
                        <button
                          type="button"
                          className="boton boton--compacto boton--fantasma"
                          onClick={() => setAbierta({ tipo: fila.tipo, id: fila.id })}
                        >
                          Revisar<span className="oculto"> {fila.motivo}, RUT {rutDe(fila)}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="lista-apilada" aria-label="Excepciones">
              {excepciones.map((fila) => (
                <li key={`${fila.tipo}-${fila.id}`} className="lista-apilada__item">
                  <div className="lista-apilada__cabecera">
                    <span className="nombre lista-apilada__nombre">{fila.motivo}</span>
                    <EstadoRevision estado={fila.estado} />
                  </div>
                  <p className="nota">{TIPOS[fila.tipo]} · {rutDe(fila)} · {fila.nom_cli || 'Sin nombre'}</p>
                  <p className="nota">
                    Informe {fila.id_informe ? `#${fila.id_informe}` : '—'} · {fila.archivo_origen ?? '—'} · {formatearFecha(fila.fecha)}
                  </p>
                  <button
                    type="button"
                    className="boton boton--compacto lista-apilada__boton"
                    onClick={() => setAbierta({ tipo: fila.tipo, id: fila.id })}
                  >
                    Revisar<span className="oculto"> {fila.motivo}, RUT {rutDe(fila)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
  
        <Paginacion
          pagina={pagina}
          total={datos?.total ?? 0}
          porPagina={POR_PAGINA}
          onCambiar={setPagina}
          etiqueta="Páginas de excepciones"
        />
        <RevisionExcepcion excepcion={abierta} onCerrar={() => setAbierta(null)} onRevisado={actualizar} />
      </section>
    </>
  )
}
