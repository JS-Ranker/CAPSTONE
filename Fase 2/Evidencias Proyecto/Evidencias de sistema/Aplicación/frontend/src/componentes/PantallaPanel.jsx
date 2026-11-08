import { useEffect } from 'react'
import { formatearFecha, formatearMonto, formatearNumero } from '../formato'
import { usePeticion } from '../usePeticion'

const REFRESCO_MS = 30_000
const TONO_ESTADO = {
  Procesado: 'exito', Normalizado: 'exito', Recibido: 'info', 'Pendiente de Extracción': 'advertencia',
  'Error de Extracción': 'error', Error: 'error',
}
// Cada resultado del cruce lleva su nombre y su cantidad escritos: el color solo ayuda a distinguirlos.
const RESULTADOS = [
  { clave: 'descontados', nombre: 'Descontados', color: 'var(--exito)' },
  { clave: 'parciales', nombre: 'Parciales', color: 'var(--info)' },
  { clave: 'no_descontados', nombre: 'No descontados', color: 'var(--advertencia)' },
  { clave: 'en_revision', nombre: 'En revisión', color: 'var(--error)' },
]

const porcentaje = (parte, total) => (total > 0 ? Math.round((parte / total) * 100) : 0)

function Indicadores({ datos }) {
  const pendientes = Object.values(datos.excepciones_pendientes).reduce((a, b) => a + b, 0)
  return (
    <dl className="indicadores indicadores--anchos">
      <div><dt>Informes recibidos</dt><dd>{formatearNumero(datos.informes.total)}</dd></div>
      <div><dt>Casos cargados</dt><dd>{formatearNumero(datos.casos.total)}</dd></div>
      <div><dt>Casos por revisar</dt><dd>{formatearNumero(datos.casos.en_revision)}</dd></div>
      <div><dt>Filas rechazadas</dt><dd>{formatearNumero(datos.casos.rechazados_etl)}</dd></div>
      <div>
        <dt>Excepciones pendientes</dt>
        <dd><a href="#/excepciones">{formatearNumero(pendientes)}</a></dd>
      </div>
      <div><dt>Monto solicitado</dt><dd>{formatearMonto(datos.cruce.monto_solicitado)}</dd></div>
      <div><dt>Monto a descontar</dt><dd>{formatearMonto(datos.cruce.monto_descontado)}</dd></div>
    </dl>
  )
}

function ResultadoDelCruce({ cruce }) {
  const total = cruce.casos
  return (
    <section className="tarjeta" aria-labelledby="titulo-resultado-cruce">
      <h2 id="titulo-resultado-cruce">Resultado del cruce con el banco</h2>
      {total === 0
        ? <p className="vacio">Aún no se cruza ningún informe.</p>
        : (
          <>
            <div className="barra-apilada" role="img"
              aria-label={RESULTADOS.map((r) => `${r.nombre}: ${cruce[r.clave]}`).join(', ')}>
              {RESULTADOS.map((r) => cruce[r.clave] > 0 && (
                <span key={r.clave} style={{ width: `${porcentaje(cruce[r.clave], total)}%`, background: r.color }} />
              ))}
            </div>
            <ul className="leyenda">
              {RESULTADOS.map((r) => (
                <li key={r.clave}>
                  <span className="leyenda__marca" style={{ background: r.color }} aria-hidden="true" />
                  {r.nombre}: <strong>{formatearNumero(cruce[r.clave])}</strong> ({porcentaje(cruce[r.clave], total)} %)
                </li>
              ))}
            </ul>
            <p className="nota">
              {formatearNumero(cruce.clientes)} de {formatearNumero(total)} casos son clientes de Banco Genérico ·
              {' '}{formatearNumero(cruce.informes)} informes cruzados.
            </p>
          </>
        )}
    </section>
  )
}

function EstadoDeLosInformes({ informes }) {
  const estados = Object.entries(informes.por_estado)
  return (
    <section className="tarjeta" aria-labelledby="titulo-estados">
      <h2 id="titulo-estados">Informes por estado</h2>
      {estados.length === 0 && <p className="vacio">Aún no se recibe ningún informe.</p>}
      <ul className="leyenda leyenda--columna">
        {estados.map(([estado, cantidad]) => (
          <li key={estado}>
            <span className={`etiqueta etiqueta--${TONO_ESTADO[estado] ?? 'info'}`}>{estado}</span>
            <strong>{formatearNumero(cantidad)}</strong>
          </li>
        ))}
      </ul>
    </section>
  )
}

function PorMes({ meses }) {
  const mayor = Math.max(1, ...meses.map((m) => Number(m.solicitado)))
  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-meses">
      <h2 id="titulo-meses">Montos por mes de recepción</h2>
      {meses.length === 0 && <p className="vacio">Aún no hay informes cruzados.</p>}
      {meses.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla" aria-labelledby="titulo-meses">
            <thead>
              <tr>
                <th scope="col">Mes</th>
                <th scope="col" className="numero">Informes</th>
                <th scope="col" className="numero">Casos</th>
                <th scope="col" className="numero">Solicitado</th>
                <th scope="col" className="numero">A descontar</th>
                <th scope="col">Descontado sobre lo solicitado</th>
              </tr>
            </thead>
            <tbody>
              {meses.map((m) => (
                <tr key={m.periodo}>
                  <td className="sin-salto">{m.periodo}</td>
                  <td className="numero">{formatearNumero(m.informes)}</td>
                  <td className="numero">{formatearNumero(m.casos)}</td>
                  <td className="numero">{formatearMonto(m.solicitado)}</td>
                  <td className="numero">{formatearMonto(m.descontado)}</td>
                  <td>
                    <div className="barra" aria-hidden="true">
                      <span className="barra__solicitado" style={{ width: `${porcentaje(Number(m.solicitado), mayor)}%` }}>
                        <span className="barra__descontado"
                          style={{ width: `${porcentaje(Number(m.descontado), Number(m.solicitado))}%` }} />
                      </span>
                    </div>
                    <span className="nota">{porcentaje(Number(m.descontado), Number(m.solicitado))} %</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function UltimosInformes({ informes }) {
  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-recientes">
      <h2 id="titulo-recientes">Últimos informes recibidos</h2>
      {informes.length === 0 && <p className="vacio">Aún no se recibe ningún informe.</p>}
      {informes.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla" aria-labelledby="titulo-recientes">
            <thead>
              <tr>
                <th scope="col">Informe</th>
                <th scope="col">Recibido</th>
                <th scope="col">Canal</th>
                <th scope="col">Estado</th>
                <th scope="col" className="numero">Deudores</th>
                <th scope="col" className="numero">Con descuento</th>
                <th scope="col" className="numero">A descontar</th>
              </tr>
            </thead>
            <tbody>
              {informes.map((i) => (
                <tr key={i.id_archivo}>
                  <td className="nombre"><a href={`#/cruce?informe=${i.id_archivo}`}>#{i.id_archivo} · {i.nombre_archivo}</a></td>
                  <td className="sin-salto">{formatearFecha(i.fecha_recepcion)}</td>
                  <td>{i.canal_origen}</td>
                  <td><span className={`etiqueta etiqueta--${TONO_ESTADO[i.estado_archivo] ?? 'info'}`}>{i.estado_archivo}</span></td>
                  <td className="numero">{formatearNumero(i.total_registros)}</td>
                  <td className="numero">{formatearNumero(i.con_descuento)}</td>
                  <td className="numero">{formatearMonto(i.monto_descontado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// Panel de monitoreo (RF06): se actualiza solo cada 30 segundos y con el botón.
export function PantallaPanel() {
  const { datos, error, cargando, actualizadoEn, recargar } = usePeticion('/api/reportes/panel')

  useEffect(() => {
    const temporizador = setInterval(recargar, REFRESCO_MS)
    return () => clearInterval(temporizador)
  }, [recargar])

  return (
    <>
      <section className="tarjeta" aria-labelledby="titulo-panel">
        <div className="tarjeta__cabecera">
          <div>
            <h2 id="titulo-panel">Estado del proceso</h2>
            <p className="nota" role="status" aria-live="polite">
              {actualizadoEn ? `Actualizado a las ${actualizadoEn.toLocaleTimeString('es-CL')}` : 'Cargando…'}
              {' '}· se actualiza cada 30 segundos
            </p>
          </div>
          <button type="button" className="boton" onClick={recargar} aria-disabled={cargando || undefined}>
            Actualizar
          </button>
        </div>
        {error && <p className="aviso aviso--error">{error.message}</p>}
        {datos && <Indicadores datos={datos} />}
      </section>
      {datos && (
        <>
          <div className="rejilla-panel">
            <ResultadoDelCruce cruce={datos.cruce} />
            <EstadoDeLosInformes informes={datos.informes} />
          </div>
          <PorMes meses={datos.por_mes} />
          <UltimosInformes informes={datos.ultimos_informes} />
        </>
      )}
    </>
  )
}
