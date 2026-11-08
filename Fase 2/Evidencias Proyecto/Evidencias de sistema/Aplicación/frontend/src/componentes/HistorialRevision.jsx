import { formatearDia, formatearFecha } from '../formato'
import { EstadoRevision } from './EstadoRevision'

const mostrar = (valor) => {
  if (valor === null || valor === undefined || valor === '') return 'vacío'
  return /^\d{4}-\d{2}-\d{2}$/.test(String(valor)) ? formatearDia(valor) : String(valor)
}

// `etiquetas` traduce el nombre de un campo corregido; si no está, se muestra tal cual.
export function Historial({ historial, etiquetas = {} }) {
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
                <li key={campo}>{etiquetas[campo] ?? campo}: {mostrar(antes)} → {mostrar(despues)}</li>
              ))}
            </ul>
          )}
          {revision.id_caso_nuevo && <p className="nota">Se creó el caso #{revision.id_caso_nuevo}.</p>}
        </li>
      ))}
    </ol>
  )
}

