import { useCallback, useState } from 'react'
import { CargaDocumento } from './CargaDocumento'
import { DetalleLote } from './DetalleLote'
import { RecepcionAutomatica } from './RecepcionAutomatica'
import { TablaLotes } from './TablaLotes'

export function PantallaIngesta() {
  // Cambia cada vez que entra o se procesa un documento, para que la tabla y el panel se vuelvan a cargar.
  const [version, setVersion] = useState(0)
  const [detalle, setDetalle] = useState(null)
  const actualizar = useCallback(() => setVersion((n) => n + 1), [])

  // Al procesar un CSV desde el detalle, el diálogo muestra el estado nuevo sin esperar a la tabla.
  function procesado(resumen) {
    setDetalle((previo) => previo && { ...previo, estado_archivo: 'Procesado', total_registros: resumen.filas_leidas })
    actualizar()
  }

  return (
    <>
      <div className="fila">
        <CargaDocumento onCargado={actualizar} />
        <RecepcionAutomatica version={version} onRevisado={actualizar} />
      </div>
      <TablaLotes version={version} onVerDetalle={setDetalle} onActualizar={actualizar} />
      <DetalleLote archivo={detalle} onCerrar={() => setDetalle(null)} onProcesado={procesado} />
    </>
  )
}
