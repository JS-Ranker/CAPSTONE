import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { CargaDocumento } from './componentes/CargaDocumento'
import { DetalleLote } from './componentes/DetalleLote'
import { RecepcionAutomatica } from './componentes/RecepcionAutomatica'
import { TablaLotes } from './componentes/TablaLotes'

const CHEQUEOS = [
  { id: 'api', nombre: 'API', url: '/api/health' },
  { id: 'db', nombre: 'Base de datos', url: '/api/health/db' },
]

// Módulos del sistema (mockups v1 a v4). Solo la ingesta está construida; el resto se muestra como próximo.
const MODULOS = [
  { nombre: 'Ingesta de Archivos', activo: true },
  { nombre: 'Dashboard' },
  { nombre: 'Bandeja de Excepciones' },
  { nombre: 'Reportes e IA' },
]
const ADMINISTRACION = [{ nombre: 'Bitácora de Auditoría' }, { nombre: 'Usuarios y Roles' }]

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
            <span className="indicador" aria-hidden="true" /> {nombre}: {texto}
          </li>
        )
      })}
    </ul>
  )
}

function Navegacion({ elementos }) {
  return (
    <ul className="menu">
      {elementos.map(({ nombre, activo }) => (
        <li key={nombre}>
          {activo ? (
            <span className="menu__item menu__item--activo" aria-current="page">{nombre}</span>
          ) : (
            <span className="menu__item menu__item--proximo">
              {nombre} <span className="menu__proximo">Próximamente</span>
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
          <p className="marca__nombre">TTDH Automation</p>
          <p className="marca__organizacion">Banco Genérico</p>
        </div>
        <nav aria-label="Módulos">
          <Navegacion elementos={MODULOS} />
          <p className="menu__grupo">Administración</p>
          <Navegacion elementos={ADMINISTRACION} />
        </nav>
        <EstadoEntorno />
      </aside>

      <div className="principal">
        <header className="encabezado">
          <p className="migas">Inicio / Ingesta</p>
          <h1>Gestión de Ingesta de Documentos TGR</h1>
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
