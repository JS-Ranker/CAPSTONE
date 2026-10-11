import { useEffect, useRef, useState } from 'react'
import { agregarRemitente, listarRemitentes, quitarRemitente } from '../api'

const FORMATO_CORREO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

// Remitentes cuyos correos se leen (CU02 2a). Los correos de cualquier otro remitente se ignoran.
// Quitar un remitente lo desactiva: si se vuelve a agregar, se reactiva.
export function RemitentesAutorizados({ abierto, onCerrar, onCambio }) {
  const dialogo = useRef(null)
  const campoCorreo = useRef(null)
  const [remitentes, setRemitentes] = useState(null)
  const [errorLista, setErrorLista] = useState(null)
  const [correo, setCorreo] = useState('')
  const [nombre, setNombre] = useState('')
  const [errorCorreo, setErrorCorreo] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [aviso, setAviso] = useState({ tipo: 'inactivo', mensaje: '' })

  async function cargar() {
    try {
      setRemitentes(await listarRemitentes())
      setErrorLista(null)
    } catch (falla) {
      setErrorLista(falla.message)
    }
  }

  useEffect(() => {
    const elemento = dialogo.current
    if (abierto && !elemento.open) {
      setAviso({ tipo: 'inactivo', mensaje: '' })
      setErrorCorreo('')
      elemento.showModal()
      cargar()
    }
    if (!abierto && elemento.open) elemento.close()
  }, [abierto])

  async function agregar(evento) {
    evento.preventDefault()
    if (!FORMATO_CORREO.test(correo.trim())) {
      setErrorCorreo('Ingrese un correo válido, por ejemplo nominas@tgr.cl.')
      campoCorreo.current.focus()
      return
    }
    setErrorCorreo('')
    setOcupado(true)
    try {
      const remitente = await agregarRemitente(correo.trim(), nombre.trim() || null)
      setCorreo('')
      setNombre('')
      setAviso({ tipo: 'exito', mensaje: `${remitente.correo} quedó autorizado.` })
      await cargar()
      onCambio()
    } catch (falla) {
      if (falla.estado === 400) setErrorCorreo(falla.message)
      else setAviso({ tipo: 'error', mensaje: falla.message })
    } finally {
      setOcupado(false)
      campoCorreo.current.focus()
    }
  }

  async function quitar(remitente) {
    setOcupado(true)
    try {
      await quitarRemitente(remitente.id_remitente)
      setAviso({ tipo: 'exito', mensaje: `${remitente.correo} ya no está autorizado.` })
      await cargar()
      onCambio()
    } catch (falla) {
      setAviso({ tipo: 'error', mensaje: falla.message })
    } finally {
      setOcupado(false)
      campoCorreo.current.focus() // el botón pulsado desaparece de la lista
    }
  }

  return (
    <dialog ref={dialogo} className="dialogo" aria-labelledby="titulo-remitentes" onClose={onCerrar}>
      <div className="dialogo__cabecera">
        <h2 id="titulo-remitentes">Remitentes autorizados</h2>
        <button type="button" className="boton boton--secundario" onClick={() => dialogo.current.close()}>
          Cerrar
        </button>
      </div>
      <p className="nota">Solo se registran los adjuntos de correos enviados desde estas direcciones.</p>

      <form className="formulario" onSubmit={agregar} noValidate>
        <div className="campo">
          <label htmlFor="remitente-correo">Correo</label>
          <input
            ref={campoCorreo}
            id="remitente-correo"
            type="email"
            autoComplete="off"
            value={correo}
            onChange={(evento) => setCorreo(evento.target.value)}
            aria-invalid={errorCorreo ? 'true' : undefined}
            aria-describedby={errorCorreo ? 'remitente-correo-error' : undefined}
            placeholder="nominas@tgr.cl"
            maxLength={255}
            required
          />
          {errorCorreo && <p id="remitente-correo-error" className="campo__error">{errorCorreo}</p>}
        </div>
        <div className="campo">
          <label htmlFor="remitente-nombre">Nombre <span className="campo__opcional">(opcional)</span></label>
          <input
            id="remitente-nombre"
            type="text"
            autoComplete="off"
            value={nombre}
            onChange={(evento) => setNombre(evento.target.value)}
            placeholder="TGR - Nóminas"
            maxLength={150}
          />
        </div>
        <button type="submit" className="boton" disabled={ocupado}>Agregar</button>
      </form>

      <p className={`aviso aviso--${aviso.tipo}`} role="status" aria-live="polite">{aviso.mensaje}</p>

      {errorLista && (
        <p className="aviso aviso--error">
          No se pudo obtener la lista: {errorLista} <button type="button" className="enlace" onClick={cargar}>Reintentar</button>
        </p>
      )}
      {remitentes && remitentes.length === 0 && (
        <p className="vacio">Aún no hay remitentes autorizados: los correos recibidos se ignoran.</p>
      )}
      {remitentes?.length > 0 && (
        <ul className="remitentes" aria-label="Remitentes autorizados">
          {remitentes.map((remitente) => (
            <li key={remitente.id_remitente} className="remitentes__item">
              <div>
                <span className="nombre remitentes__correo">{remitente.correo}</span>
                {remitente.nombre && <span className="nombre remitentes__nombre">{remitente.nombre}</span>}
              </div>
              <button
                type="button"
                className="boton boton--secundario"
                disabled={ocupado}
                onClick={() => quitar(remitente)}
                aria-label={`Quitar ${remitente.correo}`}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}
    </dialog>
  )
}
