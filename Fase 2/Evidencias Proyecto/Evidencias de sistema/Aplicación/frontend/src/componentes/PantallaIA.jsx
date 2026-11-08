import { useCallback, useEffect, useRef, useState } from 'react'
import { revisarInsight } from '../api'
import { formatearFecha, formatearNumero } from '../formato'
import { usePeticion } from '../usePeticion'
import { FiltroInforme } from './FiltroInforme'
import { Paginacion } from './Paginacion'
import { Spinner } from './Spinner'

const POR_PAGINA = 20
const TONO_NIVEL = { Alto: 'error', Medio: 'advertencia', Bajo: 'info' }
const TONO_ESTADO = { Pendiente: 'advertencia', Aplicada: 'exito', Revisada: 'neutro' }
const hoy = () => new Date().toLocaleDateString('sv-SE') // aaaa-mm-dd en hora local
const cantidad = (n, palabra) => `${formatearNumero(n)} ${palabra}${n === 1 ? '' : 's'}`

function Nivel({ nivel }) {
  return <span className={`etiqueta etiqueta--${TONO_NIVEL[nivel] ?? 'neutro'}`}>{nivel}</span>
}

// Resumen de los hallazgos operativos de un día (RF08).
function ResumenDia() {
  const [fecha, setFecha] = useState(hoy)
  const { datos, error } = usePeticion(`/api/ia/resumen?fecha=${fecha}`)
  return (
    <section className="tarjeta" aria-labelledby="titulo-resumen-ia">
      <div className="tarjeta__cabecera">
        <h2 id="titulo-resumen-ia">Resumen del día</h2>
        <div className="campo campo--en-linea">
          <label htmlFor="fecha-resumen">Fecha</label>
          <input id="fecha-resumen" type="date" value={fecha} max={hoy()} onChange={(e) => setFecha(e.target.value || hoy())} />
        </div>
      </div>
      {error && <p className="aviso aviso--error">{error.message}</p>}
      {datos && (
        <>
          <dl className="indicadores">
            <div><dt>Informes</dt><dd>{formatearNumero(datos.informes)}</dd></div>
            <div><dt>Deudores leídos</dt><dd>{formatearNumero(datos.deudores_leidos)}</dd></div>
            <div><dt>Cargados</dt><dd>{formatearNumero(datos.cargados)}</dd></div>
            <div><dt>Rechazados</dt><dd>{formatearNumero(datos.rechazados)}</dd></div>
            <div><dt>Alertas IA</dt><dd>{formatearNumero(datos.alertas.Alto + datos.alertas.Medio + datos.alertas.Bajo)}</dd></div>
          </dl>
          <ul className="puntos">
            {datos.puntos.map((punto) => <li key={punto}>{punto}</li>)}
          </ul>
        </>
      )}
    </section>
  )
}

// Confirmación de "Aplicar sugerencia" o "Marcar como revisado" (CU08 pasos 4 y 4a), con observación opcional.
function DialogoRevision({ insight, accion, onCerrar, onHecho }) {
  const dialogo = useRef(null)
  const [observacion, setObservacion] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [falla, setFalla] = useState('')

  useEffect(() => {
    const elemento = dialogo.current
    if (insight && !elemento.open) elemento.showModal()
    if (!insight && elemento.open) elemento.close()
  }, [insight])

  async function confirmar(evento) {
    evento.preventDefault()
    if (enviando) return
    setEnviando(true)
    setFalla('')
    try {
      await revisarInsight(insight.id_insight, { accion, observacion: observacion.trim() || null })
      onHecho(accion === 'aplicar' ? 'Sugerencia aplicada: rige desde el próximo informe.' : 'Insight marcado como revisado.')
      dialogo.current.close()
    } catch (error) {
      setFalla(error.message)
      setEnviando(false)
    }
  }

  const aplicar = accion === 'aplicar'
  return (
    <dialog ref={dialogo} className="dialogo" aria-labelledby="titulo-revision-ia" onClose={onCerrar}>
      {insight && (
        <form className="formulario-revision" onSubmit={confirmar}>
          <h2 id="titulo-revision-ia">{aplicar ? 'Aplicar sugerencia' : 'Marcar como revisado'}</h2>
          <p className="nombre">{insight.titulo}</p>
          {aplicar
            ? <p className="aviso aviso--advertencia">{insight.sugerencia} Desde el próximo informe que se procese, esos casos quedarán para revisión manual en Excepciones.</p>
            : <p className="nota">El insight deja de estar pendiente. Queda registrado en la bitácora.</p>}
          <div className="campo">
            <label htmlFor="obs-ia">Observación <span className="campo__opcional">(opcional)</span></label>
            <textarea id="obs-ia" rows={2} maxLength={1000} value={observacion} onChange={(e) => setObservacion(e.target.value)} />
          </div>
          {falla && <p className="aviso aviso--error" role="alert">{falla}</p>}
          <div className="acciones">
            <button type="submit" className="boton boton--primario" aria-disabled={enviando || undefined}>
              {enviando ? <><Spinner /> Guardando…</> : aplicar ? 'Aplicar' : 'Marcar como revisado'}
            </button>
            <button type="button" className="boton" onClick={() => dialogo.current.close()}>Cancelar</button>
          </div>
        </form>
      )}
    </dialog>
  )
}

function Insight({ insight, onRevisar }) {
  return (
    <li className="insight">
      <div className="insight__cabecera">
        <Nivel nivel={insight.nivel} />
        <span className="nota">{insight.tipo}</span>
        {insight.estado !== 'Pendiente' && (
          <span className={`etiqueta etiqueta--${TONO_ESTADO[insight.estado]}`}>{insight.estado}</span>
        )}
      </div>
      <h3 className="insight__titulo">{insight.titulo}</h3>
      <p className="insight__detalle">{insight.detalle}</p>
      {insight.sugerencia && <p className="insight__sugerencia"><strong>Sugerencia:</strong> {insight.sugerencia}</p>}
      {insight.observacion && <p className="nota">Observación: {insight.observacion}</p>}
      <p className="nota enlaces">
        <a href={`#/ia?informe=${insight.id_informe}`}>Informe #{insight.id_informe}</a>
        {insight.id_caso && <a href={`#/casos?informe=${insight.id_informe}`}>Ver los casos del informe</a>}
        <span>{insight.nombre_archivo} · {formatearFecha(insight.fecha)}</span>
      </p>
      {insight.estado === 'Pendiente' && (
        <div className="acciones">
          {insight.aplicable && (
            <button type="button" className="boton boton--primario" onClick={() => onRevisar(insight, 'aplicar')}>
              Aplicar sugerencia
            </button>
          )}
          <button type="button" className="boton" onClick={() => onRevisar(insight, 'revisar')}>
            Marcar como revisado
          </button>
        </div>
      )}
    </li>
  )
}

// Módulo de IA (CU08): insights ordenados por nivel, con sugerencias que se pueden aplicar o descartar.
export function PantallaIA({ informe }) {
  const [filtro, setFiltro] = useState({ nivel: '', estado: 'Pendiente' })
  const [pagina, setPagina] = useState(0)
  const [version, setVersion] = useState(0)
  const [revision, setRevision] = useState({ insight: null, accion: null })
  const [aviso, setAviso] = useState('')
  const titulo = useRef(null)
  const actualizar = useCallback(() => setVersion((n) => n + 1), [])

  // El botón pulsado desaparece cuando el insight deja de estar pendiente: el foco va al título de la lista.
  useEffect(() => {
    if (aviso) titulo.current?.focus()
  }, [aviso, version])

  const parametros = new URLSearchParams({ limite: POR_PAGINA, desplazamiento: pagina * POR_PAGINA })
  for (const [clave, valor] of Object.entries(filtro)) if (valor) parametros.set(clave, valor)
  if (informe) parametros.set('informe', informe)
  const { datos, error, recargar } = usePeticion(`/api/ia/insights?${parametros}`, version)
  const insights = datos?.insights ?? []

  function filtrar(cambios) {
    setFiltro((previo) => ({ ...previo, ...cambios }))
    setPagina(0)
  }

  return (
    <>
      <ResumenDia />
      <FiltroInforme modulo="ia" informe={informe} otro={{ modulo: 'excepciones', texto: 'Revisar en Excepciones' }} />
      <section className="tarjeta" aria-labelledby="titulo-insights">
        <div className="tarjeta__cabecera">
          <div>
            <h2 id="titulo-insights" ref={titulo} tabIndex={-1}>Alertas e insights</h2>
            <p className="nota" role="status">
              {datos && `Pendientes: ${cantidad(datos.pendientes.Alto, 'alta')}, `
                + `${cantidad(datos.pendientes.Medio, 'media')} y ${cantidad(datos.pendientes.Bajo, 'baja')}`}
            </p>
          </div>
          <div className="filtros">
            <div className="campo">
              <label htmlFor="filtro-nivel">Nivel</label>
              <select id="filtro-nivel" value={filtro.nivel} onChange={(e) => filtrar({ nivel: e.target.value })}>
                <option value="">Todos</option>
                <option value="Alto">Alto</option>
                <option value="Medio">Medio</option>
                <option value="Bajo">Bajo</option>
              </select>
            </div>
            <div className="campo">
              <label htmlFor="filtro-estado-ia">Estado</label>
              <select id="filtro-estado-ia" value={filtro.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
                <option value="Pendiente">Pendientes</option>
                <option value="Aplicada">Aplicadas</option>
                <option value="Revisada">Revisadas</option>
                <option value="">Todos</option>
              </select>
            </div>
          </div>
        </div>
        <p className="aviso aviso--exito" role="status" aria-live="polite">{aviso}</p>
        <p className="nota">
          La IA analiza cada informe al terminar el ETL: compara sus deudores con el historial (modelo IsolationForest
          y reglas explicables) y revisa si los rechazos o los datos dudosos están fuera de lo habitual.
        </p>
        {error && (
          <p className="aviso aviso--error">
            {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
          </p>
        )}
        {!error && datos && insights.length === 0 && (
          <p className="vacio">
            {filtro.estado === 'Pendiente' ? 'No hay alertas pendientes para este filtro.' : 'Ninguna alerta coincide con los filtros.'}
          </p>
        )}
        {insights.length > 0 && (
          <ul className="insights" aria-label="Alertas e insights">
            {insights.map((insight) => (
              <Insight key={insight.id_insight} insight={insight} onRevisar={(i, accion) => setRevision({ insight: i, accion })} />
            ))}
          </ul>
        )}
        <Paginacion
          pagina={pagina}
          total={datos?.total ?? 0}
          porPagina={POR_PAGINA}
          onCambiar={setPagina}
          etiqueta="Páginas de alertas"
        />
      </section>
      <DialogoRevision
        insight={revision.insight}
        accion={revision.accion}
        onCerrar={() => setRevision({ insight: null, accion: null })}
        onHecho={(mensaje) => { setAviso(mensaje); actualizar() }}
      />
    </>
  )
}
