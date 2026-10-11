import { useState } from 'react'
import { revisarCorreo, revisarSftp } from '../api'
import { formatearFecha, formatearNumero } from '../formato'
import { usePeticion } from '../usePeticion'
import { RemitentesAutorizados } from './RemitentesAutorizados'

function resumir(resumen) {
  const partes = [`${resumen.registrados} registrados`, `${resumen.rechazados} rechazados`]
  if (resumen.omitidos) partes.push(`${resumen.omitidos} omitidos`)
  if (resumen.fallidos) partes.push(`${resumen.fallidos} con falla (se reintentan)`)
  return partes.join(', ')
}

function Conexion({ activo, si, no }) {
  return <span className={`etiqueta etiqueta--${activo ? 'exito' : 'neutro'}`}>{activo ? si : no}</span>
}

export function RecepcionAutomatica({ version, onRevisado }) {
  const { datos, error, recargar } = usePeticion('/api/recepcion/estado', version)
  const [accion, setAccion] = useState({ canal: null, tipo: 'inactivo', mensaje: '' })
  const [remitentesAbierto, setRemitentesAbierto] = useState(false)
  const ocupado = accion.tipo === 'revisando'
  const sinRemitentes = datos?.correo.remitentes_autorizados === 0

  async function revisar(canal, nombre, ejecutar) {
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
          No se pudo obtener el estado. <button type="button" className="enlace" onClick={recargar}>Reintentar</button>
        </p>
      )}
      {datos && (
        <dl className="lista-datos">
          <div><dt>Casilla de correo</dt><dd><Conexion activo={datos.correo.configurado} si="Configurada" no="Sin configurar" /></dd></div>
          <div><dt>Remitentes autorizados</dt><dd>{formatearNumero(datos.correo.remitentes_autorizados)}</dd></div>
          <div><dt>Última lectura correo</dt><dd>{formatearFecha(datos.correo.ultima_revision)}</dd></div>
          <div><dt>Recibidos hoy por correo</dt><dd>{formatearNumero(datos.correo.recibidos_hoy)}</dd></div>
          <div><dt>Directorio SFTP</dt><dd><Conexion activo={datos.sftp.configurado} si="Disponible" no="No encontrado" /></dd></div>
          <div><dt>Última lectura SFTP</dt><dd>{formatearFecha(datos.sftp.ultima_revision)}</dd></div>
          <div><dt>Pendientes de OCR</dt><dd>{formatearNumero(datos.pendientes_extraccion)}</dd></div>
        </dl>
      )}
      <div className="acciones">
        <button
          type="button"
          className="boton"
          disabled={ocupado || !datos?.correo.configurado || sinRemitentes}
          onClick={() => revisar('correo', 'Correo', revisarCorreo)}
        >
          {ocupado && accion.canal === 'correo' ? 'Leyendo…' : 'Leer correo ahora'}
        </button>
        <button
          type="button"
          className="boton"
          disabled={ocupado || !datos?.sftp.configurado}
          onClick={() => revisar('sftp', 'SFTP', revisarSftp)}
        >
          {ocupado && accion.canal === 'sftp' ? 'Leyendo…' : 'Forzar lectura SFTP'}
        </button>
        <button type="button" className="boton" onClick={() => setRemitentesAbierto(true)}>
          Remitentes autorizados
        </button>
      </div>
      {datos && !datos.correo.configurado && (
        <p className="nota">Para leer el correo, configure la casilla (IMAP_*) en backend/.env.</p>
      )}
      {datos?.correo.configurado && sinRemitentes && (
        <p className="nota">Agregue al menos un remitente autorizado para leer el correo.</p>
      )}
      <p className={`aviso aviso--${accion.tipo}`} role="status" aria-live="polite">{accion.mensaje}</p>
      <RemitentesAutorizados
        abierto={remitentesAbierto}
        onCerrar={() => setRemitentesAbierto(false)}
        onCambio={recargar}
      />
    </section>
  )
}
