import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import './App.css'
import { CasosTgr } from './componentes/CasosTgr'
import { Icono } from './componentes/Icono'
import { PantallaCruce } from './componentes/PantallaCruce'
import { PantallaExcepciones } from './componentes/PantallaExcepciones'
import { PantallaIA } from './componentes/PantallaIA'
import { PantallaIngesta } from './componentes/PantallaIngesta'
import { PantallaPanel } from './componentes/PantallaPanel'

const CHEQUEOS = [
  { id: 'api', nombre: 'API', url: '/api/health' },
  { id: 'db', nombre: 'Base de datos', url: '/api/health/db' },
]

// Pantallas construidas, con su dirección (#/ingesta, #/casos). El resto va agrupado bajo "Próximamente".
const MODULOS = [
  { id: 'ingesta', nombre: 'Ingesta', icono: 'ingesta', titulo: 'Ingesta de documentos TGR', Pantalla: PantallaIngesta },
  { id: 'panel', nombre: 'Dashboard', icono: 'dashboard', titulo: 'Panel de monitoreo', Pantalla: PantallaPanel },
  { id: 'casos', nombre: 'Casos TGR', icono: 'casos', titulo: 'Casos TGR', Pantalla: CasosTgr },
  {
    id: 'excepciones', nombre: 'Excepciones', icono: 'excepciones', titulo: 'Bandeja de Excepciones',
    Pantalla: PantallaExcepciones,
  },
  { id: 'ia', nombre: 'Análisis IA', icono: 'reportes', titulo: 'Análisis con IA', Pantalla: PantallaIA },
  { id: 'cruce', nombre: 'Cruce Banco', icono: 'servidor', titulo: 'Cruce con Banco Genérico', Pantalla: PantallaCruce },
]
const PROXIMOS = [
  { nombre: 'Reportes', icono: 'bitacora' },
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

// La pantalla actual sale de la dirección (#/casos o #/casos?informe=808): así funcionan el botón Atrás,
// los enlaces entre pantallas y compartir una vista filtrada.
function rutaActual() {
  return window.location.hash
}

function leerRuta(hash) {
  const [id, consulta = ''] = hash.replace(/^#\/?/, '').split('?')
  const modulo = MODULOS.find((m) => m.id === id) ?? MODULOS[0]
  const informe = Number.parseInt(new URLSearchParams(consulta).get('informe'), 10)
  return { modulo, informe: informe > 0 ? informe : null }
}

function suscribirRuta(avisar) {
  window.addEventListener('hashchange', avisar)
  return () => window.removeEventListener('hashchange', avisar)
}

function Navegacion({ actual }) {
  const contenedor = useRef(null)
  const [marca, setMarca] = useState(null) // posición de la pastilla del módulo activo: { y, alto }
  const [movil, setMovil] = useState(false) // la primera posición no se anima, solo los cambios

  // Se mide antes de pintar: la pastilla aparece ya en su lugar y, al cambiar de módulo, se desliza.
  useLayoutEffect(() => {
    const activo = contenedor.current?.querySelector('[aria-current="page"]')
    setMarca(activo ? { y: activo.offsetTop, alto: activo.offsetHeight } : null)
  }, [actual])
  useEffect(() => {
    const id = requestAnimationFrame(() => setMovil(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div className="menu-contenedor" ref={contenedor}>
      {marca && (
        <span
          className={`menu__indicador${movil ? ' menu__indicador--movil' : ''}`}
          style={{ transform: `translateY(${marca.y}px)`, height: marca.alto }}
          aria-hidden="true"
        />
      )}
      <ul className="menu">
        {MODULOS.map(({ id, nombre, icono }) => (
          <li key={id}>
            <a
              className={`menu__item${id === actual ? ' menu__item--activo' : ''}`}
              href={`#/${id}`}
              aria-current={id === actual ? 'page' : undefined}
            >
              <Icono nombre={icono} /> {nombre}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Los módulos aún no construidos no son enlaces: se muestran atenuados para no parecer funcionales.
function Proximos() {
  return (
    <>
      <p className="menu__grupo">Próximamente</p>
      <ul className="menu menu--proximos">
        {PROXIMOS.map(({ nombre, icono }) => (
          <li key={nombre}>
            <span className="menu__item menu__item--proximo">
              <Icono nombre={icono} /> {nombre}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}

function App() {
  const hash = useSyncExternalStore(suscribirRuta, rutaActual)
  const { modulo, informe } = leerRuta(hash)
  const titulo = useRef(null)
  const rutaAnterior = useRef(hash)

  // Al cambiar de pantalla, el foco va al título nuevo para que el lector de pantalla anuncie dónde se está.
  // Al abrir la aplicación no se mueve (se compara con la ruta anterior, no con "primera vez": el modo
  // estricto de React ejecuta los efectos dos veces en desarrollo).
  useEffect(() => {
    document.title = `${modulo.titulo} · TTDH Automation`
    if (rutaAnterior.current === hash) return
    rutaAnterior.current = hash
    titulo.current?.focus()
  }, [modulo, hash])

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
          <Navegacion actual={modulo.id} />
          <Proximos />
        </nav>
        <EstadoEntorno />
      </aside>

      <div className="principal">
        <header className="encabezado">
          <h1 ref={titulo} tabIndex={-1}>{modulo.titulo}</h1>
        </header>
        <main className="contenido">
          {/* key: cada pantalla (o cambio de filtro en la dirección) parte de cero: filtros, página, diálogos */}
          <modulo.Pantalla key={hash} informe={informe} />
        </main>
      </div>
    </div>
  )
}

export default App
