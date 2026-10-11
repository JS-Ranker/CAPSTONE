import { useRef, useState } from 'react'
import { subirDocumento } from '../api'

const EXTENSIONES = ['.xlsx', '.xls', '.csv', '.txt', '.pdf', '.jpg', '.jpeg', '.png']
const TAMANO_MAXIMO_MB = 20 // el backend es quien decide (TAMANO_MAXIMO_MB); esto solo evita subir algo que rechazará

function revisarArchivo(archivo) {
  const extension = archivo.name.includes('.') ? archivo.name.slice(archivo.name.lastIndexOf('.')).toLowerCase() : ''
  if (!EXTENSIONES.includes(extension)) return `Formato no permitido. Se aceptan: ${EXTENSIONES.join(', ')}.`
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
      const siguiente = documento.estado_archivo === 'Pendiente de Extracción'
        ? 'Se está convirtiendo con OCR en segundo plano.'
        : 'Quedó listo para el proceso ETL.'
      setEstado({ tipo: 'exito', mensaje: `${documento.nombre_archivo} se registró como lote #${documento.id_archivo}. ${siguiente}` })
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
    <section className="tarjeta" aria-labelledby="titulo-carga">
      <h2 id="titulo-carga">Cargar nuevo documento</h2>
      <div
        className={`zona-carga${arrastrando ? ' zona-carga--activa' : ''}`}
        onDragOver={(evento) => { evento.preventDefault(); setArrastrando(true) }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={soltar}
      >
        <span className="zona-carga__icono" aria-hidden="true">↑</span>
        <p className="zona-carga__texto">
          Arrastre y suelte su documento TGR aquí, o{' '}
          <button type="button" className="enlace" onClick={() => entrada.current?.click()} disabled={subiendo}>
            haga clic para examinar
          </button>
        </p>
        <p className="zona-carga__ayuda">Formatos permitidos: {EXTENSIONES.join(', ')} · máximo {TAMANO_MAXIMO_MB} MB</p>
        <p className="zona-carga__ayuda">Los PDF escaneados y las fotografías se convierten automáticamente con OCR.</p>
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
