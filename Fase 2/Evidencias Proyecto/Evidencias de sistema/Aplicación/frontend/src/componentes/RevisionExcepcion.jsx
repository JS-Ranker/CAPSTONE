import { useEffect, useRef, useState } from 'react'
import { revisarExcepcion } from '../api'
import { TIPOS, rutOriginal } from '../excepciones'
import { formatearDia, formatearFecha, formatearRut } from '../formato'
import { usePeticion } from '../usePeticion'
import { EstadoRevision } from './EstadoRevision'
import { Icono } from './Icono'

const FECHA = { ayuda: 'dd-mm-aaaa', placeholder: 'dd-mm-aaaa' }
const SI_NO = { ayuda: 'SI o NO' }
const MONTO = { ayuda: 'Sin puntos', inputMode: 'numeric' }

// Campos que se pueden corregir. Caso: los datos del oficio (la llave RUT-rol-fecha no se edita).
// Rechazo: las columnas del CSV, que vuelven a pasar por las reglas del ETL al cargar.
const CAMPOS = {
  caso: [
    { campo: 'fecha_oficio', etiqueta: 'Fecha del oficio', ...FECHA },
    { campo: 'n_resol', etiqueta: 'N° resolución' },
    { campo: 'id_demanda', etiqueta: 'ID demanda' },
    { campo: 'monto_solicitado', etiqueta: 'Monto solicitado', ...MONTO },
    { campo: 'nom_cli', etiqueta: 'Nombre del cliente' },
    { campo: 'tesoreria', etiqueta: 'Tesorería' },
    { campo: 'ent_banco', etiqueta: 'Entidad bancaria' },
  ],
  rechazo: [
    { campo: 'rut', etiqueta: 'RUT (sin DV)', inputMode: 'numeric' },
    { campo: 'dv', etiqueta: 'DV' },
    { campo: 'rol', etiqueta: 'Expediente', ayuda: 'número-año localidad' },
    { campo: 'fec_ing', etiqueta: 'Fecha de ingreso', ...FECHA },
    { campo: 'mult_rol', etiqueta: 'Múltiples roles', ...SI_NO },
    { campo: 'rev_manual', etiqueta: 'Revisión manual', ...SI_NO },
    { campo: 'nom_cli', etiqueta: 'Nombre del cliente' },
    { campo: 'monto_solicitado', etiqueta: 'Monto solicitado', ...MONTO },
    { campo: 'fecha_oficio', etiqueta: 'Fecha del oficio', ...FECHA },
    { campo: 'n_resol', etiqueta: 'N° resolución' },
    { campo: 'id_demanda', etiqueta: 'ID demanda' },
    { campo: 'tesoreria', etiqueta: 'Tesorería' },
  ],
}
const ETIQUETAS = Object.fromEntries([...CAMPOS.caso, ...CAMPOS.rechazo].map((c) => [c.campo, c.etiqueta]))

const ACCIONES = {
  regularizar: { texto: 'Regularizar', exito: 'Caso regularizado.' },
  cargar: { texto: 'Corregir y cargar', exito: 'Fila cargada como caso nuevo.' },
  descartar: { texto: 'Descartar', exito: 'Fila descartada. Si fue un error, puede reabrirla.' },
  pendiente: { texto: 'Dejar pendiente', exito: 'Quedó pendiente, con su observación.' },
}

// Valor para el campo de texto: fechas ISO a dd-mm-aaaa y montos sin decimales.
function aTexto(campo, valor) {
  if (valor === null || valor === undefined) return ''
  if (/^\d{4}-\d{2}-\d{2}/.test(String(valor))) return formatearDia(valor)
  if (campo === 'monto_solicitado' && typeof valor === 'number') return String(Math.trunc(valor))
  return String(valor)
}

const mostrar = (valor) => {
  if (valor === null || valor === undefined || valor === '') return 'vacío'
  return /^\d{4}-\d{2}-\d{2}$/.test(String(valor)) ? formatearDia(valor) : String(valor)
}

function Historial({ historial }) {
  if (historial.length === 0) return <p className="nota">Sin revisiones todavía.</p>
  return (
    <ol className="historial">
      {historial.map((revision) => (
        <li key={revision.id_revision} className="historial__item">
          <div className="historial__cabecera">
            <EstadoRevision estado={revision.estado} />
            <span className="nota">{formatearFecha(revision.fecha)} · {revision.usuario}</span>
          </div>
          <p className="historial__texto">{revision.observacion}</p>
          {revision.cambios && (
            <ul className="historial__cambios">
              {Object.entries(revision.cambios).map(([campo, { antes, despues }]) => (
                <li key={campo}>{ETIQUETAS[campo] ?? campo}: {mostrar(antes)} → {mostrar(despues)}</li>
              ))}
            </ul>
          )}
          {revision.id_caso_nuevo && <p className="nota">Se creó el caso #{revision.id_caso_nuevo}.</p>}
        </li>
      ))}
    </ol>
  )
}

function FormularioRevision({ tipo, id, detalle, onHecho }) {
  const campos = CAMPOS[tipo]
  const [iniciales] = useState(() => Object.fromEntries(campos.map(({ campo }) => [campo, aTexto(campo, detalle.datos[campo])])))
  const [valores, setValores] = useState(iniciales)
  const [observacion, setObservacion] = useState('')
  const [errores, setErrores] = useState({})
  const [falla, setFalla] = useState('')
  const [enviando, setEnviando] = useState(null)
  const descartado = detalle.estado === 'Descartado'
  const acciones = descartado ? [] : tipo === 'caso' ? ['regularizar', 'pendiente'] : ['cargar', 'pendiente', 'descartar']
  const principal = acciones[0]

  async function enviar(accion) {
    if (enviando) return
    setFalla('')
    if (!observacion.trim()) {
      setErrores({ observacion: 'Escriba una observación: queda en el historial.' })
      document.getElementById('rev-observacion')?.focus()
      return
    }
    setErrores({})
    // Solo se envía lo que el analista cambió. Descartar o reabrir una fila no guarda datos.
    const guardaDatos = tipo === 'caso' || accion === 'cargar'
    const datos = guardaDatos
      ? Object.fromEntries(Object.entries(valores).filter(([campo, valor]) => valor !== iniciales[campo]))
      : {}
    setEnviando(accion)
    try {
      const respuesta = await revisarExcepcion(tipo, id, { accion, observacion: observacion.trim(), datos })
      const nuevo = respuesta.id_caso_nuevo ? ` (caso #${respuesta.id_caso_nuevo})` : ''
      const exito = descartado ? 'Fila reabierta: vuelve a estar pendiente.' : `${ACCIONES[accion].exito}${nuevo}`
      onHecho(exito)
    } catch (error) {
      const campo = error.detalle?.campo
      if (campo && (campo === 'observacion' || iniciales[campo] !== undefined)) {
        setErrores({ [campo]: error.message })
        document.getElementById(`rev-${campo}`)?.focus()
      } else {
        setFalla(error.message)
      }
      setEnviando(null)
    }
  }

  return (
    <form
      className="formulario-revision"
      noValidate
      onSubmit={(evento) => { evento.preventDefault(); enviar(principal ?? 'pendiente') }}
    >
      {!descartado && (
        <fieldset className="campos-grid">
          <legend>{tipo === 'caso' ? 'Complete o corrija los datos del oficio' : 'Corrija los datos de la fila'}</legend>
          {campos.map(({ campo, etiqueta, ayuda, placeholder, inputMode }) => {
            const idAyuda = ayuda ? `rev-${campo}-ayuda` : null
            const idError = errores[campo] ? `rev-${campo}-error` : null
            return (
              <div className="campo" key={campo}>
                <label htmlFor={`rev-${campo}`}>{etiqueta}</label>
                <input
                  id={`rev-${campo}`}
                  type="text"
                  value={valores[campo]}
                  onChange={(evento) => setValores((previo) => ({ ...previo, [campo]: evento.target.value }))}
                  placeholder={placeholder}
                  inputMode={inputMode}
                  autoComplete="off"
                  aria-invalid={errores[campo] ? 'true' : undefined}
                  aria-describedby={[idAyuda, idError].filter(Boolean).join(' ') || undefined}
                />
                {ayuda && <p id={idAyuda} className="campo__ayuda">{ayuda}</p>}
                {errores[campo] && <p id={idError} className="campo__error">{errores[campo]}</p>}
              </div>
            )
          })}
        </fieldset>
      )}

      <div className="campo">
        <label htmlFor="rev-observacion">Observación <span className="campo__opcional">(obligatoria)</span></label>
        <textarea
          id="rev-observacion"
          rows={3}
          maxLength={1000}
          value={observacion}
          onChange={(evento) => setObservacion(evento.target.value)}
          aria-invalid={errores.observacion ? 'true' : undefined}
          aria-describedby={errores.observacion ? 'rev-observacion-error' : 'rev-observacion-ayuda'}
        />
        {errores.observacion
          ? <p id="rev-observacion-error" className="campo__error">{errores.observacion}</p>
          : <p id="rev-observacion-ayuda" className="campo__ayuda">Qué revisó y por qué tomó la decisión.</p>}
      </div>

      {falla && <p className="aviso aviso--error" role="alert">{falla}</p>}

      <div className="acciones">
        {descartado ? (
          <button type="submit" className="boton boton--primario" aria-disabled={Boolean(enviando) || undefined}>
            {enviando ? 'Guardando…' : 'Reabrir'}
          </button>
        ) : acciones.map((accion) => (
          <button
            key={accion}
            type={accion === principal ? 'submit' : 'button'}
            className={`boton${accion === principal ? ' boton--primario' : ''}${accion === 'descartar' ? ' boton--peligro' : ''}`}
            onClick={accion === principal ? undefined : () => enviar(accion)}
            aria-disabled={Boolean(enviando) || undefined}
          >
            {enviando === accion ? 'Guardando…' : ACCIONES[accion].texto}
          </button>
        ))}
      </div>
    </form>
  )
}

// El oficio original (PDF o foto que llegó por correo) se abre en otra pestaña, para revisarlo junto al formulario.
function Documento({ tipo, id, documento }) {
  if (documento.id_archivo) {
    return (
      <div className="documento">
        <a className="boton" href={`/api/excepciones/${tipo}/${id}/documento`} target="_blank" rel="noopener noreferrer">
          <Icono nombre="archivo" tamano={18} /> Ver documento
        </a>
        <span className="nota">{documento.nombre_buscado} · se abre en otra pestaña</span>
      </div>
    )
  }
  return (
    <p className="nota">
      {documento.nombre_buscado
        ? `No se encontró ${documento.nombre_buscado} entre los documentos recibidos: revise el oficio por fuera.`
        : 'La fila no indica el documento original (RUTA DOCUMENTO vacía).'}
    </p>
  )
}

function ContenidoRevision({ tipo, id, onRevisado, onCerrar }) {
  const [version, setVersion] = useState(0)
  const [aviso, setAviso] = useState('')
  const titulo = useRef(null)
  const { datos: detalle, error, recargar } = usePeticion(`/api/excepciones/${tipo}/${id}`, version)
  const d = detalle?.datos

  // Tras guardar, el formulario se vuelve a crear y el botón pulsado desaparece: el foco va al título.
  useEffect(() => {
    if (version > 0) titulo.current?.focus()
  }, [version])

  function hecho(mensaje) {
    setAviso(mensaje)
    setVersion((n) => n + 1)
    onRevisado()
  }

  return (
    <>
      <div className="dialogo__cabecera">
        <h2 id="titulo-revision" ref={titulo} tabIndex={-1}>{TIPOS[tipo]}</h2>
        <button type="button" className="boton boton--compacto" onClick={onCerrar}>Cerrar</button>
      </div>
      <p className="aviso aviso--exito" role="status" aria-live="polite">{aviso}</p>
      {error && (
        <p className="aviso aviso--error">
          {error.message} <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!error && !detalle && <p className="nota">Cargando…</p>}
      {detalle && (
        <>
          <div className="regla">
            <p className="regla__titulo">{tipo === 'caso' ? 'Por qué está en revisión' : 'Regla que no cumplió'}</p>
            <p className="regla__texto">{detalle.motivo}</p>
          </div>
          <dl className="lista-datos">
            <div><dt>Estado</dt><dd><EstadoRevision estado={detalle.estado} /></dd></div>
            <div>
              <dt>RUT</dt>
              <dd>{tipo === 'caso' ? formatearRut(d.rut_limpio, d.dv_limpio) : rutOriginal(d)}</dd>
            </div>
            {tipo === 'caso' && <div><dt>Rol</dt><dd className="nombre">{d.rol}</dd></div>}
            {tipo === 'caso' && <div><dt>Ingreso</dt><dd>{formatearDia(d.fec_ing)}</dd></div>}
            <div><dt>Archivo</dt><dd className="nombre">{detalle.archivo_origen ?? '—'}</dd></div>
          </dl>
          <Documento tipo={tipo} id={id} documento={detalle.documento} />
          {detalle.estado === 'Resuelto Manual' ? (
            <p className="nota">Esta excepción ya se resolvió. Abajo está el detalle de lo que se hizo.</p>
          ) : (
            <FormularioRevision key={detalle.historial.length} tipo={tipo} id={id} detalle={detalle} onHecho={hecho} />
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

// "Revisar detalle" (CU05 pasos 3 a 6) en un diálogo nativo: atrapa el foco, Escape lo cierra y el foco
// vuelve al botón "Revisar".
export function RevisionExcepcion({ excepcion, onCerrar, onRevisado }) {
  const dialogo = useRef(null)

  useEffect(() => {
    const elemento = dialogo.current
    if (excepcion && !elemento.open) elemento.showModal()
    if (!excepcion && elemento.open) elemento.close()
  }, [excepcion])

  return (
    <dialog ref={dialogo} className="dialogo dialogo--ancho" aria-labelledby="titulo-revision" onClose={onCerrar}>
      {excepcion && (
        <ContenidoRevision
          key={`${excepcion.tipo}-${excepcion.id}`}
          tipo={excepcion.tipo}
          id={excepcion.id}
          onRevisado={onRevisado}
          onCerrar={() => dialogo.current.close()}
        />
      )}
    </dialog>
  )
}
