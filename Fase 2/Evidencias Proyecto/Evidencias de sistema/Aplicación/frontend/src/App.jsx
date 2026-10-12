import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { CargaDocumento } from './componentes/CargaDocumento'
import { DetalleLote } from './componentes/DetalleLote'
import { Icono } from './componentes/Icono'
import { RecepcionAutomatica } from './componentes/RecepcionAutomatica'
import { TablaLotes } from './componentes/TablaLotes'

const CHEQUEOS = [
  { id: 'api', nombre: 'API', url: '/api/health' },
  { id: 'db', nombre: 'Base de datos', url: '/api/health/db' },
]

// Módulos del sistema. Solo la ingesta está construida; el resto va agrupado bajo "Próximamente".
const MODULOS = [{ nombre: 'Ingesta', icono: 'ingesta', activo: true }]
const PROXIMOS = [
  { nombre: 'Dashboard', icono: 'dashboard' },
  { nombre: 'Excepciones', icono: 'excepciones' },
  { nombre: 'Reportes e IA', icono: 'reportes' },
  { nombre: 'Auditoría', icono: 'bitacora' },
  { nombre: 'Usuarios y roles', icono: 'usuarios' },
]

async function consultar(url) {
  try {
    const respuesta = await fetch(url)
    return respuesta.ok
  } catch {
    return false
  }
}

function EstadoEntorno() {
  const [estados, setEstados] = useState({})

  useEffect(() => {
    let vigente = true
    CHEQUEOS.forEach(async ({ id, url }) => {
      const ok = await consultar(url)
      if (vigente) setEstados((previo) => ({ ...previo, [id]: ok }))
    })
    return () => { vigente = false }
  }, [])

  return (
    <ul className="entorno" aria-label="Estado del entorno">
      {CHEQUEOS.map(({ id, nombre }) => {
        const ok = estados[id]
        const texto = ok === undefined ? 'verificando…' : ok ? 'conectada' : 'sin conexión'
        return (
          <li key={id} className={ok === undefined ? 'pendiente' : ok ? 'ok' : 'error'}>
            <span className="indicador" aria-hidden="true" />
            <span>{nombre}</span>
            <span className="entorno__estado">{texto}</span>
          </li>
        )
      })}
    </ul>
  )
}

// Los módulos aún no construidos no son enlaces: se muestran atenuados para no parecer funcionales.
function Navegacion({ elementos }) {
  return (
    <ul className="menu">
      {elementos.map(({ nombre, icono, activo }) => (
        <li key={nombre}>
          {activo ? (
            <span className="menu__item menu__item--activo" aria-current="page">
              <Icono nombre={icono} /> {nombre}
            </span>
          ) : (
            <span className="menu__item menu__item--proximo">
              <Icono nombre={icono} /> {nombre}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function App() {
  // Cambia cada vez que entra un documento nuevo, para que la tabla y el panel se vuelvan a cargar.
  const [version, setVersion] = useState(0)
  const [detalle, setDetalle] = useState(null)
  const actualizar = useCallback(() => setVersion((n) => n + 1), [])

  return (
    <div className="aplicacion">
      <aside className="barra-lateral">
        <div className="marca">
          <span className="marca__simbolo" aria-hidden="true">TT</span>
          <div>
            <p className="marca__nombre">TTDH Automation</p>
            <p className="marca__organizacion">Banco Genérico</p>
          </div>
        </div>
        <nav aria-label="Módulos">
          <Navegacion elementos={MODULOS} />
          <p className="menu__grupo">Próximamente</p>
          <Navegacion elementos={PROXIMOS} />
        </nav>
        <EstadoEntorno />
      </aside>

      <div className="principal">
        <header className="encabezado">
          <h1>Ingesta de documentos TGR</h1>
        </header>
        <main className="contenido">
          <div className="fila">
            <CargaDocumento onCargado={actualizar} />
            <RecepcionAutomatica version={version} onRevisado={actualizar} />
          </div>
          <TablaLotes version={version} onVerDetalle={setDetalle} onActualizar={actualizar} />
        </main>
      </div>

      <DetalleLote archivo={detalle} onCerrar={() => setDetalle(null)} />
    </div>
  )
}

export default App
