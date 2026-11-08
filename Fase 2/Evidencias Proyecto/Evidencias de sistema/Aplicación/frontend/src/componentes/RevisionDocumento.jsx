import { useEffect, useRef, useState } from 'react'
import { procesarDocumento, reextraerDocumento, revisarDocumento } from '../api'
import { TIPOS } from '../excepciones'
import { formatearFecha, formatearNumero, formatearPorcentaje } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoRevision } from './EstadoRevision'
import { Historial } from './HistorialRevision'
import { Icono } from './Icono'
import { Spinner } from './Spinner'

const montoDe = (texto) => {
  const limpio = (texto ?? '').replace(/[.\s$]/g, '')
  return /^\d+$/.test(limpio) ? Number(limpio) : 0
}
const numeroODeclarado = (texto) => {
  const limpio = texto.replace(/[.\s]/g, '')
  return limpio === '' ? null : Number(limpio)
}

// Documento original: se abre en otra pestaña y, si es una foto, también se ve aquí para compararlo con la grilla.
function Original({ id, datos }) {
  const url = `/api/excepciones/documento/${id}/documento`
  const esImagen = datos.tipo_documento === 'Imagen'
  return (
    <div className="grupo">
      <div className="documento">
        <a className="boton" href={url} target="_blank" rel="noopener noreferrer">
          <Icono nombre="archivo" tamano={18} /> Ver documento
        </a>
        <span className="nota">{datos.nombre_archivo} · se abre en otra pestaña</span>
      </div>
      {esImagen && (
        <details className="vista-previa">
          <summary>Ver la foto aquí mismo</summary>
          <img src={url} alt={`Informe ${datos.nombre_archivo}`} />
        </details>
      )}
    </div>
  )
}

function Cuadre({ filas, cantidad, suma }) {
  const total = filas.reduce((acumulado, fila) => acumulado + montoDe(fila.valores.monto_solicitado), 0)
  const declarada = numeroODeclarado(suma)
  const declaradaCantidad = numeroODeclarado(cantidad)
  const diferencia = declarada === null ? null : total - declarada
  const cuadra = (diferencia === null || diferencia === 0)
    && (declaradaCantidad === null || declaradaCantidad === filas.length)
  return (
    <div className={`aviso ${cuadra ? 'aviso--exito' : 'aviso--error'}`} role="status">
      <p className="aviso__titulo">{cuadra ? 'Los totales cuadran.' : 'Los totales todavía no cuadran.'}</p>
      <ul className="aviso__lista">
        <li>{formatearNumero(filas.length)} filas{declaradaCantidad !== null && ` (el documento declara ${formatearNumero(declaradaCantidad)})`}</li>
        <li>
          Los montos suman ${formatearNumero(total)}
          {declarada !== null && ` (el documento declara $${formatearNumero(declarada)}; diferencia $${formatearNumero(diferencia)})`}
        </li>
      </ul>
    </div>
  )
}

function Grilla({ columnas, filas, originales, umbral, onCambiar, onQuitar, onAgregar, deshabilitada }) {
  const dudosa = (fila, columna) => {
    const original = originales[fila.orden]
    if (!original || !columna.critico) return false
    return (original.confianzas[columna.campo] ?? 0) < umbral
      && (fila.valores[columna.campo] ?? '').trim() === (original.valores[columna.campo] ?? '').trim()
  }
  return (
    <div className="grupo">
      <h3 className="grupo__titulo">Deudores leídos del documento</h3>
      <p className="nota">
        Las celdas con borde de aviso son datos críticos (RUT, monto o expediente) leídos con menos de {umbral} % de
        confianza: compárelos con el documento. Lo que usted corrija se considera verificado.
      </p>
      <div className="tabla-contenedor tabla-contenedor--grilla">
        <table className="tabla tabla--grilla">
          <caption className="oculto">Deudores leídos del documento</caption>
          <thead>
            <tr>
              <th scope="col">N°</th>
              {columnas.map((c) => <th scope="col" key={c.campo}>{c.etiqueta}</th>)}
              <th scope="col"><span className="oculto">Quitar</span></th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila, indice) => (
              <tr key={fila.clave}>
                <td className="numero">{indice + 1}</td>
                {columnas.map((c) => (
                  <td key={c.campo}>
                    <input
                      type="text"
                      className={`celda${dudosa(fila, c) ? ' celda--dudosa' : ''}`}
                      value={fila.valores[c.campo] ?? ''}
                      onChange={(evento) => onCambiar(fila.clave, c.campo, evento.target.value)}
                      aria-label={`${c.etiqueta}, fila ${indice + 1}${dudosa(fila, c) ? ', leída con poca confianza' : ''}`}
                      aria-invalid={dudosa(fila, c) ? 'true' : undefined}
                      disabled={deshabilitada}
                      autoComplete="off"
                    />
                  </td>
                ))}
                <td>
                  <button type="button" className="boton boton--compacto boton--fantasma" onClick={() => onQuitar(fila.clave)}
                    disabled={deshabilitada}>
                    Quitar<span className="oculto"> fila {indice + 1}</span>
                  </button>
                </td>
              </tr>
            ))}
            {filas.length === 0 && (
              <tr><td colSpan={columnas.length + 2} className="vacio">No se leyó ninguna fila: agregue las filas a mano o pida volver a extraer.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <button type="button" className="boton boton--compacto" onClick={onAgregar} disabled={deshabilitada}>Agregar fila</button>
    </div>
  )
}

function Formulario({ id, detalle, onHecho, onSalir }) {
  const { datos } = detalle
  const extraccion = datos.extraccion
  const [filas, setFilas] = useState(() => (extraccion?.filas ?? []).map((f) => ({
    clave: `o${f.orden}`, orden: f.orden, valores: { ...f.valores },
  })))
  const siguiente = useRef(1)
  const [cantidad, setCantidad] = useState(String(extraccion?.cantidad_declarada ?? ''))
  const [suma, setSuma] = useState(String(extraccion?.suma_declarada ?? ''))
  const [observacion, setObservacion] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(null)
  const originales = Object.fromEntries((extraccion?.filas ?? []).map((f) => [f.orden, f]))
  const descartado = detalle.estado === 'Descartado'

  const cambiar = (clave, campo, valor) => setFilas((previo) => previo.map(
    (fila) => (fila.clave === clave ? { ...fila, valores: { ...fila.valores, [campo]: valor } } : fila)))
  const quitar = (clave) => setFilas((previo) => previo.filter((fila) => fila.clave !== clave))
  const agregar = () => setFilas((previo) => [...previo, { clave: `n${siguiente.current++}`, orden: null, valores: {} }])

  async function enviar(accion) {
    if (enviando) return
    setError('')
    if (!observacion.trim()) {
      setError('Escriba una observación: queda en el historial.')
      document.getElementById('doc-observacion')?.focus()
      return
    }
    setEnviando(accion)
    try {
      if (accion === 'procesar') {
        const respuesta = await procesarDocumento(id, {
          observacion: observacion.trim(),
          filas: filas.map(({ orden, valores }) => ({ orden, valores })),
          cantidad_declarada: numeroODeclarado(cantidad),
          suma_declarada: numeroODeclarado(suma),
        })
        onHecho(`Informe enviado al ETL con ${formatearNumero(respuesta.filas_enviadas)} deudores.`)
      } else if (accion === 'reextraer') {
        await reextraerDocumento(id, observacion.trim())
        onSalir('Se pidió leer el documento otra vez: vuelve a aparecer aquí si sigue con error.')
      } else {
        await revisarDocumento(id, { accion, observacion: observacion.trim() })
        onHecho(accion === 'descartar'
          ? 'Informe descartado. Si fue un error, puede reabrirlo.' : 'Quedó pendiente, con su observación.')
      }
    } catch (falla) {
      setError(falla.message)
      setEnviando(null)
    }
  }

  const boton = (accion, texto, clases = '') => (
    <button type="button" className={`boton ${clases}`} onClick={() => enviar(accion)} aria-disabled={Boolean(enviando) || undefined}>
      {enviando === accion ? <><Spinner /> Guardando…</> : texto}
    </button>
  )

  return (
    <form className="formulario-revision" noValidate onSubmit={(evento) => evento.preventDefault()}>
      {!descartado && (
        <>
          <Grilla
            columnas={datos.columnas} filas={filas} originales={originales} umbral={datos.umbral_confianza}
            onCambiar={cambiar} onQuitar={quitar} onAgregar={agregar} deshabilitada={Boolean(enviando)}
          />
          <fieldset className="campos-grid">
            <legend>Totales que declara el documento</legend>
            <div className="campo">
              <label htmlFor="doc-cantidad">Cantidad de registros</label>
              <input id="doc-cantidad" type="text" inputMode="numeric" value={cantidad}
                onChange={(evento) => setCantidad(evento.target.value)} autoComplete="off" />
              <p className="campo__ayuda">Vacío si el documento no la declara.</p>
            </div>
            <div className="campo">
              <label htmlFor="doc-suma">Monto total</label>
              <input id="doc-suma" type="text" inputMode="numeric" value={suma}
                onChange={(evento) => setSuma(evento.target.value)} autoComplete="off" />
              <p className="campo__ayuda">Sin puntos. Corríjalo solo si el total también se leyó mal.</p>
            </div>
          </fieldset>
          <Cuadre filas={filas} cantidad={cantidad} suma={suma} />
        </>
      )}

      <div className="campo">
        <label htmlFor="doc-observacion">Observación <span className="campo__opcional">(obligatoria)</span></label>
        <textarea id="doc-observacion" rows={3} maxLength={1000} value={observacion}
          onChange={(evento) => setObservacion(evento.target.value)} />
        <p className="campo__ayuda">Qué revisó y por qué tomó la decisión.</p>
      </div>

      {error && <p className="aviso aviso--error" role="alert">{error}</p>}

      <div className="acciones">
        {descartado ? boton('pendiente', 'Reabrir', 'boton--primario') : (
          <>
            {boton('procesar', 'Corregir y enviar al ETL', 'boton--primario')}
            {boton('reextraer', 'Volver a extraer')}
            {boton('pendiente', 'Dejar pendiente')}
            {boton('descartar', 'Descartar', 'boton--peligro')}
          </>
        )}
      </div>
    </form>
  )
}

// Revisión de un informe con 'Error de Extracción' (CU05, CU12 5b), en el diálogo de la Bandeja de Excepciones.
export function ContenidoDocumento({ id, onRevisado, onCerrar }) {
  const [version, setVersion] = useState(0)
  const [aviso, setAviso] = useState('')
  const [releyendo, setReleyendo] = useState(false)
  const titulo = useRef(null)
  const { datos: detalle, error, recargar } = usePeticion(`/api/excepciones/documento/${id}`, version)

  useEffect(() => {
    if (version > 0) titulo.current?.focus()
  }, [version])

  const hecho = (mensaje) => { setAviso(mensaje); setVersion((n) => n + 1); onRevisado() }
  // Al pedir otra lectura el informe sale de la bandeja: ya no hay nada que mostrar, solo avisar.
  const salir = (mensaje) => { setAviso(mensaje); setReleyendo(true); onRevisado() }
  const d = detalle?.datos

  return (
    <>
      <div className="dialogo__cabecera">
        <h2 id="titulo-revision" ref={titulo} tabIndex={-1}>{TIPOS.documento} #{id}</h2>
        <button type="button" className="boton boton--compacto" onClick={onCerrar}>Cerrar</button>
      </div>
      <p className="aviso aviso--exito" role="status" aria-live="polite">{aviso}</p>
      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && !detalle && <p className="nota cargando"><Spinner /> Cargando…</p>}
      {detalle && !releyendo && (
        <>
          <div className="regla">
            <p className="regla__titulo">Por qué no se pudo usar el informe</p>
            {(d.extraccion?.errores?.length ? d.extraccion.errores : [detalle.motivo]).map((motivo) => (
              <p className="regla__texto" key={motivo}>{motivo}</p>
            ))}
          </div>
          <dl className="lista-datos">
            <div><dt>Estado</dt><dd><EstadoRevision estado={detalle.estado} /></dd></div>
            <div><dt>Archivo</dt><dd className="nombre">{d.nombre_archivo}</dd></div>
            <div><dt>Tipo</dt><dd>{d.tipo_documento}</dd></div>
            <div><dt>Recibido</dt><dd>{formatearFecha(d.fecha_recepcion)}</dd></div>
            <div><dt>Confianza promedio</dt><dd>{formatearPorcentaje(d.confianza_extraccion)}</dd></div>
          </dl>
          <Original id={id} datos={d} />
          {detalle.estado === 'Resuelto Manual' ? (
            <p className="nota">Este informe ya se corrigió y pasó al ETL. Abajo está el detalle de lo que se hizo.</p>
          ) : (
            <Formulario key={detalle.historial.length} id={id} detalle={detalle} onHecho={hecho} onSalir={salir} />
          )}
          <div className="grupo">
            <h3 className="grupo__titulo">Historial</h3>
            <Historial historial={detalle.historial} />
          </div>
        </>
      )}
    </>
  )
}
