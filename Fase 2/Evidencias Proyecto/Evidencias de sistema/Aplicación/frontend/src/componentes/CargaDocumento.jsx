import { useRef, useState } from 'react'
import { subirDocumento } from '../api'
import { Icono } from './Icono'

const EXTENSIONES = ['.xlsx', '.xls', '.csv', '.txt', '.pdf', '.jpg', '.jpeg', '.png']
const TAMANO_MAXIMO_MB = 20 // el backend es quien decide (TAMANO_MAXIMO_MB); esto solo evita subir algo que rechazará

function revisarArchivo(archivo) {
  const extension = archivo.name.includes('.') ? archivo.name.slice(archivo.name.lastIndexOf('.')).toLowerCase() : ''
  if (!EXTENSIONES.includes(extension)) return 'Formato no permitido. Use Excel, CSV, TXT, PDF o foto (JPG, PNG).'
  if (archivo.size === 0) return 'El archivo está vacío.'
  if (archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024) return `El archivo supera los ${TAMANO_MAXIMO_MB} MB.`
  return null
}

export function CargaDocumento({ onCargado }) {
  const entrada = useRef(null)
  const [arrastrando, setArrastrando] = useState(false)
  const [estado, setEstado] = useState({ tipo: 'inactivo', mensaje: '' })
  const subiendo = estado.tipo === 'subiendo'

  async function cargar(archivo) {
    if (!archivo || subiendo) return
    const problema = revisarArchivo(archivo)
    if (problema) {
      setEstado({ tipo: 'error', mensaje: `${archivo.name}: ${problema}` })
      return
    }
    setEstado({ tipo: 'subiendo', mensaje: `Cargando ${archivo.name}…` })
    try {
      const documento = await subirDocumento(archivo)
      const siguiente = documento.estado_archivo === 'Pendiente de Extracción' ? ' Leyéndolo con OCR…' : ''
      setEstado({ tipo: 'exito', mensaje: `${documento.nombre_archivo}: lote #${documento.id_archivo} creado.${siguiente}` })
      onCargado()
    } catch (error) {
      setEstado({ tipo: 'error', mensaje: `${archivo.name}: ${error.message}` })
    } finally {
      if (entrada.current) entrada.current.value = '' // permite volver a elegir el mismo archivo
    }
  }

  function soltar(evento) {
    evento.preventDefault()
    setArrastrando(false)
    cargar(evento.dataTransfer.files[0])
  }

  return (
    <section className="tarjeta tarjeta--carga" aria-labelledby="titulo-carga">
      <h2 id="titulo-carga">Cargar documento</h2>
      <div
        className={`zona-carga${arrastrando ? ' zona-carga--activa' : ''}`}
        onDragOver={(evento) => { evento.preventDefault(); setArrastrando(true) }}
        onDragLeave={(evento) => {
          // Pasar sobre el texto o el botón interno también dispara dragleave: solo cuenta salir de la zona.
          if (!evento.currentTarget.contains(evento.relatedTarget)) setArrastrando(false)
        }}
        onDrop={soltar}
      >
        <span className="zona-carga__icono"><Icono nombre="subir" tamano={22} /></span>
        <p className="zona-carga__texto">Arrastre el archivo aquí</p>
        <p className="zona-carga__ayuda">Excel, CSV, TXT, PDF o foto · hasta {TAMANO_MAXIMO_MB} MB</p>
        <button
          type="button"
          className="boton boton--primario zona-carga__boton"
          onClick={() => { if (!subiendo) entrada.current?.click() }}
          aria-disabled={subiendo || undefined}
        >
          <Icono nombre="archivo" tamano={18} /> {subiendo ? 'Cargando…' : 'Seleccionar archivo'}
        </button>
        <input
          ref={entrada}
          type="file"
          className="oculto"
          accept={EXTENSIONES.join(',')}
          aria-label="Documento TGR"
          tabIndex={-1}
          onChange={(evento) => cargar(evento.target.files[0])}
        />
      </div>
      <p className={`aviso aviso--${estado.tipo}`} role="status" aria-live="polite">
        {estado.mensaje}
      </p>
    </section>
  )
}
