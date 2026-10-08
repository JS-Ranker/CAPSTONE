import { useEffect, useState } from 'react'
import './App.css'

const CHEQUEOS = [
  { id: 'api', nombre: 'API Backend (FastAPI)', url: '/api/health' },
  { id: 'db', nombre: 'Base de datos (SQL Server)', url: '/api/health/db' },
]

async function consultar(url) {
  try {
    const respuesta = await fetch(url)
    const datos = await respuesta.json()
    return respuesta.ok ? { ok: true, datos } : { ok: false, error: datos.detail ?? 'Error' }
  } catch {
    return { ok: false, error: 'API no disponible' }
  }
}

function App() {
  const [estados, setEstados] = useState({})

  useEffect(() => {
    CHEQUEOS.forEach(async ({ id, url }) => {
      const resultado = await consultar(url)
      setEstados((previo) => ({ ...previo, [id]: resultado }))
    })
  }, [])

  return (
    <main className="contenedor">
      <header>
        <h1>TTDH Automation</h1>
        <p>Plataforma de procesamiento de registros de deudores TGR – Banco Genérico</p>
      </header>

      <section>
        <h2>Estado del entorno</h2>
        <ul className="chequeos">
          {CHEQUEOS.map(({ id, nombre }) => {
            const estado = estados[id]
            const clase = !estado ? 'pendiente' : estado.ok ? 'ok' : 'error'
            const detalle = !estado ? 'Verificando…' : estado.ok ? 'Conectado' : estado.error
            return (
              <li key={id} className={clase}>
                <span className="indicador" aria-hidden="true" />
                <span className="nombre">{nombre}</span>
                <span className="detalle">{detalle}</span>
              </li>
            )
          })}
        </ul>
      </section>
    </main>
  )
}

export default App
