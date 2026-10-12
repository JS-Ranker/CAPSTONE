import { useState } from 'react'
import { formatearDia, formatearFecha, formatearMonto, formatearNumero, formatearRut } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoRevision } from './EstadoRevision'
import { FiltroInforme } from './FiltroInforme'
import { Paginacion } from './Paginacion'

const POR_PAGINA = 20

// Pantalla "Casos TGR": los casos que el ETL cargó en core.casos_tgr y las filas que rechazó.
// Con `informe` (desde la dirección #/casos?informe=808) muestra solo los deudores de ese informe.
export function CasosTgr({ informe }) {
  return (
    <>
      <FiltroInforme modulo="casos" informe={informe} otro={{ modulo: 'excepciones', texto: 'Revisar en Excepciones' }} />
      <TablaCasos informe={informe} />
      <TablaRechazados informe={informe} />
    </>
  )
}

function Revision({ caso }) {
  if (!caso.rev_manual_bit) return <span className="nota">No necesita</span>
  return (
    <span className="revision">
      <span className="etiqueta etiqueta--advertencia">Revisar</span>
      {caso.camp_falt && <span className="nota">Falta: {caso.camp_falt.toLowerCase()}</span>}
    </span>
  )
}

const enlaceInforme = (id) => (id ? <a href={`#/casos?informe=${id}`}>#{id}</a> : '—')

function TablaCasos({ informe }) {
  const [texto, setTexto] = useState('')
  const [filtro, setFiltro] = useState({ buscar: '', revision: false })
  const [pagina, setPagina] = useState(0)

  const parametros = new URLSearchParams({ limite: POR_PAGINA, desplazamiento: pagina * POR_PAGINA })
  if (filtro.buscar) parametros.set('buscar', filtro.buscar)
  if (filtro.revision) parametros.set('revision', 'true')
  if (informe) parametros.set('informe', informe)
  const { datos, error, recargar } = usePeticion(`/api/casos?${parametros}`)
  const casos = datos?.casos ?? []
  const filtrando = Boolean(filtro.buscar || filtro.revision)

  function filtrar(cambios) {
    setFiltro((previo) => ({ ...previo, ...cambios }))
    setPagina(0)
  }

  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-casos">
      <div className="tarjeta__cabecera">
        <div>
          <h2 id="titulo-casos">Casos cargados</h2>
          {/* Anuncia el resultado de cada búsqueda o filtro (no cambia mientras se escribe) */}
          <p className="nota" role="status">
            {datos && `${formatearNumero(datos.total)} ${datos.total === 1 ? 'caso' : 'casos'}`}
            {datos?.en_revision > 0 && ` · ${formatearNumero(datos.en_revision)} para revisión manual`}
          </p>
        </div>
        <form
          className="filtros"
          role="search"
          onSubmit={(evento) => { evento.preventDefault(); filtrar({ buscar: texto.trim() }) }}
        >
          <div className="campo">
            <label htmlFor="buscar-casos">Buscar</label>
            <div className="filtros__busqueda">
              <input
                id="buscar-casos"
                type="search"
                value={texto}
                onChange={(evento) => setTexto(evento.target.value)}
                placeholder="RUT, nombre o rol"
                maxLength={100}
              />
              <button type="submit" className="boton">Buscar</button>
            </div>
          </div>
          <label className="casilla">
            <input
              type="checkbox"
              checked={filtro.revision}
              onChange={(evento) => filtrar({ revision: evento.target.checked })}
            />
            Solo para revisión manual
          </label>
        </form>
      </div>

      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && !datos && <p className="nota">Cargando…</p>}
      {!error && datos && casos.length === 0 && (
        <p className="vacio">
          {filtrando ? 'Ningún caso coincide con la búsqueda.' : <>Aún no hay casos. Suba un CSV TGR en <a href="#/ingesta">Ingesta</a>.</>}
        </p>
      )}

      {casos.length > 0 && (
        <>
          <div className="tabla-contenedor">
            <table className="tabla" aria-labelledby="titulo-casos">
              <thead>
                <tr>
                  <th scope="col">RUT</th>
                  <th scope="col">Cliente</th>
                  <th scope="col">Rol</th>
                  <th scope="col">Tesorería</th>
                  <th scope="col" className="numero">Monto</th>
                  <th scope="col">Ingreso</th>
                  <th scope="col">Revisión manual</th>
                  <th scope="col">Informe</th>
                </tr>
              </thead>
              <tbody>
                {casos.map((caso) => (
                  <tr key={caso.id_caso}>
                    <td className="sin-salto">{formatearRut(caso.rut_limpio, caso.dv_limpio)}</td>
                    <td className="nombre">{caso.nom_cli ?? '—'}</td>
                    <td className="nombre">{caso.rol}</td>
                    <td className="nombre">{caso.tesoreria ?? '—'}</td>
                    <td className="numero">{formatearMonto(caso.monto_solicitado)}</td>
                    <td className="sin-salto">{formatearDia(caso.fec_ing)}</td>
                    <td><Revision caso={caso} /></td>
                    <td className="sin-salto">{enlaceInforme(caso.id_informe)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="lista-apilada" aria-label="Casos cargados">
            {casos.map((caso) => (
              <li key={caso.id_caso} className="lista-apilada__item">
                <div className="lista-apilada__cabecera">
                  <span className="nombre lista-apilada__nombre">{caso.nom_cli ?? 'Sin nombre'}</span>
                  {caso.rev_manual_bit && <span className="etiqueta etiqueta--advertencia">Revisar</span>}
                </div>
                <p className="nota">
                  {formatearRut(caso.rut_limpio, caso.dv_limpio)} · Rol {caso.rol} · Ingreso {formatearDia(caso.fec_ing)}
                  {caso.id_informe && <> · Informe {enlaceInforme(caso.id_informe)}</>}
                </p>
                <dl className="lista-apilada__datos">
                  <div><dt>Monto</dt><dd>{formatearMonto(caso.monto_solicitado)}</dd></div>
                  <div><dt>Tesorería</dt><dd>{caso.tesoreria ?? '—'}</dd></div>
                </dl>
                {caso.rev_manual_bit && caso.camp_falt && <p className="nota">Falta: {caso.camp_falt.toLowerCase()}</p>}
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
        etiqueta="Páginas de casos"
      />
    </section>
  )
}

// Pendiente: nadie la ha revisado. Resuelto Manual: se corrigió y se cargó como caso. Descartado: no corresponde.
function EstadoRechazo({ fila }) {
  return (
    <span className="revision">
      <EstadoRevision estado={fila.estado_revision} />
      {fila.id_caso_nuevo && <span className="nota">Cargado como caso #{fila.id_caso_nuevo}</span>}
    </span>
  )
}

function TablaRechazados({ informe }) {
  const [pagina, setPagina] = useState(0)
  const delInforme = informe ? `&informe=${informe}` : ''
  const { datos, error, recargar } = usePeticion(
    `/api/etl/rechazados?limite=${POR_PAGINA}&desplazamiento=${pagina * POR_PAGINA}${delInforme}`,
  )
  const rechazados = datos?.rechazados ?? []
  const rutOriginal = (fila) => (fila.rut || fila.dv ? `${fila.rut || '?'}-${fila.dv || '?'}` : '—')

  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-rechazados">
      <div>
        <h2 id="titulo-rechazados">Rechazados por el ETL</h2>
        <p className="nota">
          Filas del informe que no cumplieron una regla, tal como llegaron.
          {datos?.total > 0 && ` ${formatearNumero(datos.total)} en total, ${formatearNumero(datos.pendientes)} `
            + 'pendientes de revisión.'}
          {' '}Se corrigen o descartan en la <a href="#/excepciones">Bandeja de Excepciones</a>.
        </p>
      </div>

      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && datos && rechazados.length === 0 && <p className="vacio">No hay filas rechazadas.</p>}

      {rechazados.length > 0 && (
        <>
          <div className="tabla-contenedor">
            <table className="tabla" aria-labelledby="titulo-rechazados">
              <thead>
                <tr>
                  <th scope="col">Motivo</th>
                  <th scope="col">RUT</th>
                  <th scope="col">Cliente</th>
                  <th scope="col">Expediente</th>
                  <th scope="col">Informe</th>
                  <th scope="col">Revisión</th>
                </tr>
              </thead>
              <tbody>
                {rechazados.map((fila) => (
                  <tr key={fila.id_resultado}>
                    <td className="nombre motivo">{fila.motivo}</td>
                    <td className="sin-salto">{rutOriginal(fila)}</td>
                    <td className="nombre">{fila.nom_cli || '—'}</td>
                    <td className="nombre">{fila.rol || '—'}</td>
                    <td className="nombre">
                      {enlaceInforme(fila.id_archivo)} {fila.archivo_origen}
                      <span className="nota bloque">{formatearFecha(fila.fecha_inicio)}</span>
                    </td>
                    <td><EstadoRechazo fila={fila} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="lista-apilada" aria-label="Rechazados por el ETL">
            {rechazados.map((fila) => (
              <li key={fila.id_resultado} className="lista-apilada__item">
                <div className="lista-apilada__cabecera">
                  <span className="nombre lista-apilada__nombre motivo">{fila.motivo}</span>
                  <EstadoRechazo fila={fila} />
                </div>
                <p className="nota">{rutOriginal(fila)} · {fila.nom_cli || 'Sin nombre'} · Expediente {fila.rol || '—'}</p>
                <p className="nota">
                  Informe {enlaceInforme(fila.id_archivo)} · {fila.archivo_origen} · {formatearFecha(fila.fecha_inicio)}
                </p>
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
        etiqueta="Páginas de rechazados"
      />
    </section>
  )
}
