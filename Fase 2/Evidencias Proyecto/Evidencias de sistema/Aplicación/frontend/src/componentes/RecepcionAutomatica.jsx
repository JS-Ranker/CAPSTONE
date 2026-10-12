import { useState } from 'react'
import { revisarCorreo, revisarSftp } from '../api'
import { formatearFecha, formatearNumero } from '../formato'
import { usePeticion } from '../usePeticion'
import { Icono } from './Icono'
import { RemitentesAutorizados } from './RemitentesAutorizados'

function resumir(resumen) {
  const partes = [`${resumen.registrados} registrados`, `${resumen.rechazados} rechazados`]
  if (resumen.omitidos) partes.push(`${resumen.omitidos} omitidos`)
  if (resumen.fallidos) partes.push(`${resumen.fallidos} con falla (se reintentan)`)
  return partes.join(', ')
}

function Conexion({ activo, si, no }) {
  return <span className={`etiqueta etiqueta--${activo ? 'exito' : 'advertencia'}`}>{activo ? si : no}</span>
}

export function RecepcionAutomatica({ version, onRevisado }) {
  const { datos, error, recargar } = usePeticion('/api/recepcion/estado', version)
  const [accion, setAccion] = useState({ canal: null, tipo: 'inactivo', mensaje: '' })
  const [remitentesAbierto, setRemitentesAbierto] = useState(false)
  const ocupado = accion.tipo === 'revisando'
  const sinRemitentes = datos?.correo.remitentes_autorizados === 0

  async function revisar(canal, nombre, ejecutar) {
    if (ocupado) return
    setAccion({ canal, tipo: 'revisando', mensaje: `Revisando ${nombre}…` })
    try {
      const resumen = await ejecutar()
      setAccion({ canal, tipo: 'exito', mensaje: `${nombre}: ${resumir(resumen)}.` })
      onRevisado()
    } catch (falla) {
      setAccion({ canal, tipo: 'error', mensaje: `${nombre}: ${falla.message}` })
    }
  }

  return (
    <section className="tarjeta" aria-labelledby="titulo-automatica">
      <h2 id="titulo-automatica">Recepción automática</h2>
      {error && (
        <p className="aviso aviso--error">
          No se pudo cargar. <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {!datos && !error && <p className="nota">Cargando…</p>}
      {datos && (
        <>
          <div className="grupo">
            <div className="grupo__cabecera">
              <h3 className="grupo__titulo"><Icono nombre="correo" tamano={18} /> Correo</h3>
              <Conexion activo={datos.correo.configurado} si="Activo" no="Sin configurar" />
            </div>
            <dl className="lista-datos">
              <div>
                <dt>Remitentes</dt>
                <dd className="lista-datos__accion">
                  {formatearNumero(datos.correo.remitentes_autorizados)}
                  <button type="button" className="boton boton--compacto" onClick={() => setRemitentesAbierto(true)}>
                    Editar<span className="oculto"> remitentes</span>
                  </button>
                </dd>
              </div>
              <div><dt>Última lectura</dt><dd>{formatearFecha(datos.correo.ultima_revision)}</dd></div>
              <div><dt>Recibidos hoy</dt><dd>{formatearNumero(datos.correo.recibidos_hoy)}</dd></div>
            </dl>
            {!datos.correo.configurado && <p className="nota">Falta configurar la casilla (IMAP_* en backend/.env).</p>}
            {datos.correo.configurado && sinRemitentes && <p className="nota">Agregue un remitente para leer el correo.</p>}
          </div>

          <div className="grupo">
            <div className="grupo__cabecera">
              <h3 className="grupo__titulo"><Icono nombre="servidor" tamano={18} /> SFTP</h3>
              <Conexion activo={datos.sftp.configurado} si="Activo" no="No encontrado" />
            </div>
            <dl className="lista-datos">
              <div><dt>Última lectura</dt><dd>{formatearFecha(datos.sftp.ultima_revision)}</dd></div>
              <div><dt>Recibidos hoy</dt><dd>{formatearNumero(datos.sftp.recibidos_hoy)}</dd></div>
            </dl>
          </div>

          {/* Solo se muestra cuando hay algo pendiente: un "0" fijo es ruido */}
          {datos.pendientes_extraccion > 0 && (
            <p className="nota">{formatearNumero(datos.pendientes_extraccion)} en lectura OCR</p>
          )}
        </>
      )}
      {/* Mientras se lee un canal los botones quedan aria-disabled (no disabled) para que el pulsado conserve el foco. */}
      <div className="acciones">
        <button
          type="button"
          className="boton"
          disabled={!datos?.correo.configurado || sinRemitentes}
          aria-disabled={ocupado || undefined}
          onClick={() => revisar('correo', 'Correo', revisarCorreo)}
        >
          {ocupado && accion.canal === 'correo' ? 'Leyendo…' : 'Leer correo'}
        </button>
        <button
          type="button"
          className="boton"
          disabled={!datos?.sftp.configurado}
          aria-disabled={ocupado || undefined}
          onClick={() => revisar('sftp', 'SFTP', revisarSftp)}
        >
          {ocupado && accion.canal === 'sftp' ? 'Leyendo…' : 'Leer SFTP'}
        </button>
      </div>
      <p className={`aviso aviso--${accion.tipo}`} role="status" aria-live="polite">{accion.mensaje}</p>
      <RemitentesAutorizados
        abierto={remitentesAbierto}
        onCerrar={() => setRemitentesAbierto(false)}
        onCambio={recargar}
      />
    </section>
  )
}
