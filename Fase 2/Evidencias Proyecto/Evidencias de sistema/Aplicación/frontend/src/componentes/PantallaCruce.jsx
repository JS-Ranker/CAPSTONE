import { useState } from 'react'
import { cruzarInforme, fijarUtm } from '../api'
import { formatearDia, formatearFecha, formatearMonto, formatearNumero, formatearRut } from '../formato'
import { usePeticion } from '../usePeticion'
import { FiltroInforme } from './FiltroInforme'

const TONO_RESULTADO = {
  Descontado: 'exito', 'Descontado parcial': 'info', 'No descontado': 'advertencia', 'En revisión': 'error',
}
const mesActual = () => new Date().toLocaleDateString('sv-SE').slice(0, 7) // aaaa-mm en hora local

function Resultado({ resultado }) {
  return <span className={`etiqueta etiqueta--${TONO_RESULTADO[resultado] ?? 'info'}`}>{resultado}</span>
}

// UTM de cada mes: la ingresa el analista; el cruce usa la del mes en que se recibió el informe.
function PanelUtm({ onCambio }) {
  const [version, setVersion] = useState(0)
  const { datos, error } = usePeticion('/api/cruce/utm', version)
  const [periodo, setPeriodo] = useState(mesActual)
  const [valor, setValor] = useState('')
  const [estado, setEstado] = useState({ tipo: '', mensaje: '' })

  async function guardar(evento) {
    evento.preventDefault()
    const numero = Number(valor.replace(/\./g, '').replace(',', '.'))
    if (!periodo || !(numero > 0)) {
      setEstado({ tipo: 'error', mensaje: 'Ingrese el mes y un valor de UTM mayor que cero.' })
      return
    }
    try {
      await fijarUtm(periodo, numero)
      setEstado({ tipo: 'exito', mensaje: `UTM de ${periodo} guardada. Los informes ya cruzados conservan la UTM anterior hasta volver a cruzarlos.` })
      setValor('')
      setVersion((n) => n + 1)
      onCambio()
    } catch (falla) {
      setEstado({ tipo: 'error', mensaje: falla.message })
    }
  }

  const vigente = datos?.find((u) => u.periodo === mesActual())
  return (
    <section className="tarjeta" aria-labelledby="titulo-utm">
      <div className="tarjeta__cabecera">
        <div>
          <h2 id="titulo-utm">UTM del mes</h2>
          <p className="nota">
            {vigente ? `${mesActual()}: ${formatearMonto(vigente.valor)} (0,5 UTM = ${formatearMonto(vigente.valor / 2)})`
              : `Falta la UTM de ${mesActual()}: sin ella los informes del mes no se cruzan.`}
          </p>
        </div>
        <form className="filtros" onSubmit={guardar}>
          <div className="campo">
            <label htmlFor="utm-periodo">Mes</label>
            <input id="utm-periodo" type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} />
          </div>
          <div className="campo">
            <label htmlFor="utm-valor">Valor ($)</label>
            <div className="filtros__busqueda">
              <input id="utm-valor" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="Ej.: 69.751" />
              <button type="submit" className="boton">Guardar</button>
            </div>
          </div>
        </form>
      </div>
      <p className={`aviso aviso--${estado.tipo}`} role="status" aria-live="polite">{estado.mensaje}</p>
      {error && <p className="aviso aviso--error">{error.message}</p>}
      {datos?.length > 0 && (
        <p className="nota">
          Meses ingresados: {datos.map((u) => `${u.periodo} ${formatearMonto(u.valor)}`).join(' · ')}
        </p>
      )}
    </section>
  )
}

function Indicadores({ cruce }) {
  return (
    <dl className="indicadores">
      <div><dt>Casos</dt><dd>{formatearNumero(cruce.casos)}</dd></div>
      <div><dt>Clientes</dt><dd>{formatearNumero(cruce.clientes)}</dd></div>
      <div><dt>Descontados</dt><dd>{formatearNumero(cruce.descontados)}</dd></div>
      <div><dt>Parciales</dt><dd>{formatearNumero(cruce.parciales)}</dd></div>
      <div><dt>No descontados</dt><dd>{formatearNumero(cruce.no_descontados)}</dd></div>
      <div><dt>En revisión</dt><dd>{formatearNumero(cruce.en_revision)}</dd></div>
      <div><dt>Monto descontado</dt><dd>{formatearMonto(cruce.monto_descontado)}</dd></div>
    </dl>
  )
}

function Descuentos({ descuentos }) {
  if (descuentos.length === 0) return '—'
  return descuentos.map((d) => `${d.tipo} ${d.cuenta}: ${formatearMonto(d.monto)}`).join(' · ')
}

// Cruce vigente de un informe: resumen y resultado de cada caso con su motivo.
function CruceInforme({ informe, version, onCruzado }) {
  const { datos, error, recargar } = usePeticion(`/api/cruce/informes/${informe}`, version)
  const [filtro, setFiltro] = useState('')
  const [estado, setEstado] = useState({ tipo: '', mensaje: '', cruzando: false })

  async function cruzar() {
    if (estado.cruzando) return
    setEstado({ tipo: '', mensaje: '', cruzando: true })
    try {
      const resumen = await cruzarInforme(informe)
      setEstado({ tipo: 'exito', mensaje: `Cruce #${resumen.id_ejecucion} listo: ${formatearNumero(resumen.descontados + resumen.parciales)} casos con descuento.`, cruzando: false })
      onCruzado()
    } catch (falla) {
      setEstado({ tipo: 'error', mensaje: falla.message, cruzando: false })
    }
  }

  const sinCruce = error?.estado === 404
  const resultados = (datos?.resultados ?? []).filter((r) => !filtro || r.resultado === filtro)
  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-cruce">
      <div className="tarjeta__cabecera">
        <div>
          <h2 id="titulo-cruce">Cruce con Banco Genérico</h2>
          {datos && (
            <p className="nota">
              Cruce #{datos.id_ejecucion} · {formatearFecha(datos.fecha)} · UTM {datos.periodo}: {formatearMonto(datos.valor_utm)}
            </p>
          )}
        </div>
        <button type="button" className="boton boton--primario" onClick={cruzar} aria-disabled={estado.cruzando || undefined}>
          {estado.cruzando ? 'Cruzando…' : datos ? 'Volver a cruzar' : 'Cruzar informe'}
        </button>
      </div>
      <p className={`aviso aviso--${estado.tipo}`} role="status" aria-live="polite">{estado.mensaje}</p>
      {sinCruce && <p className="vacio">El informe aún no se ha cruzado. Si falta la UTM del mes, ingrésela arriba y luego cruce el informe.</p>}
      {error && !sinCruce && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {datos && (
        <>
          <Indicadores cruce={datos} />
          <p className="nota">
            Regla: si el saldo total de las cuentas activas del cliente es menor a 0,5 UTM no se descuenta; si no, se
            descuenta hasta cubrir la deuda, partiendo por la cuenta de mayor saldo y por la deuda más antigua. El
            sistema solo calcula: el cargo lo hace el core bancario.
          </p>
          <div className="filtros">
            <div className="campo">
              <label htmlFor="filtro-resultado">Resultado</label>
              <select id="filtro-resultado" value={filtro} onChange={(e) => setFiltro(e.target.value)}>
                <option value="">Todos</option>
                {Object.keys(TONO_RESULTADO).map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>
          <div className="tabla-contenedor">
            <table className="tabla" aria-labelledby="titulo-cruce">
              <thead>
                <tr>
                  <th scope="col">RUT</th>
                  <th scope="col">Cliente</th>
                  <th scope="col">Oficio</th>
                  <th scope="col" className="numero">Deuda</th>
                  <th scope="col" className="numero">Saldo total</th>
                  <th scope="col" className="numero">Descontado</th>
                  <th scope="col" className="numero">Pendiente</th>
                  <th scope="col">Resultado</th>
                  <th scope="col">Motivo y cuentas</th>
                </tr>
              </thead>
              <tbody>
                {resultados.map((r) => (
                  <tr key={r.id_resultado}>
                    <td className="sin-salto">{formatearRut(r.rut, r.dv)}</td>
                    <td className="nombre">{r.nombre ?? '—'}</td>
                    <td className="sin-salto">{formatearDia(r.fecha_oficio)}</td>
                    <td className="numero">{formatearMonto(r.monto_solicitado)}</td>
                    <td className="numero">{r.cliente ? formatearMonto(r.saldo_total) : '—'}</td>
                    <td className="numero">{formatearMonto(r.monto_descontado)}</td>
                    <td className="numero">{formatearMonto(r.monto_pendiente)}</td>
                    <td><Resultado resultado={r.resultado} /></td>
                    <td className="motivo">{r.motivo}<br /><span className="nota"><Descuentos descuentos={r.descuentos} /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {resultados.length === 0 && <p className="vacio">Ningún caso con ese resultado.</p>}
        </>
      )}
    </section>
  )
}

// Sin informe elegido: los últimos informes cruzados.
function UltimosCruces({ version }) {
  const { datos, error } = usePeticion('/api/cruce/informes', version)
  return (
    <section className="tarjeta tarjeta--tabla" aria-labelledby="titulo-ultimos">
      <h2 id="titulo-ultimos">Últimos informes cruzados</h2>
      {error && <p className="aviso aviso--error">{error.message}</p>}
      {datos?.length === 0 && <p className="vacio">Aún no se ha cruzado ningún informe.</p>}
      {datos?.length > 0 && (
        <div className="tabla-contenedor">
          <table className="tabla" aria-labelledby="titulo-ultimos">
            <thead>
              <tr>
                <th scope="col">Informe</th>
                <th scope="col">Cruzado</th>
                <th scope="col" className="numero">Casos</th>
                <th scope="col" className="numero">Con descuento</th>
                <th scope="col" className="numero">En revisión</th>
                <th scope="col" className="numero">Solicitado</th>
                <th scope="col" className="numero">Descontado</th>
              </tr>
            </thead>
            <tbody>
              {datos.map((c) => (
                <tr key={c.id_ejecucion}>
                  <td className="nombre"><a href={`#/cruce?informe=${c.id_archivo}`}>#{c.id_archivo} · {c.nombre_archivo}</a></td>
                  <td className="sin-salto">{formatearFecha(c.fecha)}</td>
                  <td className="numero">{formatearNumero(c.casos)}</td>
                  <td className="numero">{formatearNumero(c.descontados + c.parciales)}</td>
                  <td className="numero">{formatearNumero(c.en_revision)}</td>
                  <td className="numero">{formatearMonto(c.monto_solicitado)}</td>
                  <td className="numero">{formatearMonto(c.monto_descontado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// Cruce con Banco Genérico (RF04): UTM del mes y resultado del cruce de cada informe.
export function PantallaCruce({ informe }) {
  const [version, setVersion] = useState(0)
  const actualizar = () => setVersion((n) => n + 1)
  return (
    <>
      <PanelUtm onCambio={actualizar} />
      <FiltroInforme modulo="cruce" informe={informe} otro={{ modulo: 'casos', texto: 'Ver los casos' }} />
      {informe
        ? <CruceInforme informe={informe} version={version} onCruzado={actualizar} />
        : <UltimosCruces version={version} />}
    </>
  )
}
