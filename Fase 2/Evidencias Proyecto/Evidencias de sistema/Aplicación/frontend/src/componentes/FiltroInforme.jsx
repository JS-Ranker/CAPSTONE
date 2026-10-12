import { useState } from 'react'
import { usePeticion } from '../usePeticion'
import { EstadoArchivo } from './EstadoArchivo'

// Nombre y estado del informe filtrado, para que se sepa de qué documento son los deudores.
function InformeActual({ informe, modulo, otro }) {
  const { datos, error } = usePeticion(`/api/recepcion/archivos/${informe}`)
  return (
    <p className="filtro-informe__actual">
      <strong>Informe #{informe}</strong>
      {datos && <> · <span className="nombre">{datos.nombre_archivo}</span> · <EstadoArchivo estado={datos.estado_archivo} /></>}
      {error && <span className="nota"> · {error.estado === 404 ? 'no existe' : 'no se pudo cargar'}</span>}
      {' · '}<a href={`#/${modulo}`}>Ver todos</a>
      {' · '}<a href={`#/${otro.modulo}?informe=${informe}`}>{otro.texto}</a>
    </p>
  )
}

// Filtro por informe recibido. Vive en la dirección (#/casos?informe=808): así funcionan los enlaces desde
// Ingesta, el botón Atrás y compartir la vista. `otro` enlaza a la misma vista en la otra pantalla.
export function FiltroInforme({ modulo, informe, otro }) {
  const [numero, setNumero] = useState(informe ? String(informe) : '')

  function aplicar(evento) {
    evento.preventDefault()
    const valor = Number.parseInt(numero, 10)
    window.location.hash = valor > 0 ? `#/${modulo}?informe=${valor}` : `#/${modulo}`
  }

  return (
    <section className="tarjeta filtro-informe" aria-label="Filtrar por informe">
      <form className="filtros" onSubmit={aplicar}>
        <div className="campo">
          <label htmlFor="filtro-informe">N° de informe</label>
          <div className="filtros__busqueda">
            <input
              id="filtro-informe"
              type="number"
              inputMode="numeric"
              min="1"
              value={numero}
              onChange={(evento) => setNumero(evento.target.value)}
              placeholder="Ej.: 808"
            />
            <button type="submit" className="boton">{informe ? 'Cambiar' : 'Ver informe'}</button>
          </div>
        </div>
        <p className="nota filtro-informe__ayuda">
          El número aparece en Ingesta, en la lista de informes recibidos.
        </p>
      </form>
      {informe && <InformeActual informe={informe} modulo={modulo} otro={otro} />}
    </section>
  )
}
