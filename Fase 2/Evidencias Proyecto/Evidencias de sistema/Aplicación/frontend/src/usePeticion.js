import { useCallback, useEffect, useState } from 'react'
import { pedir } from './api'

// Obtiene datos de la API y los vuelve a pedir cuando cambia `url` o `version`.
// Cancela la petición anterior para que una respuesta vieja no pise a una nueva.
export function usePeticion(url, version = 0) {
  const [estado, setEstado] = useState({ datos: null, error: null, cargando: true, actualizadoEn: null })
  const [reintentos, setReintentos] = useState(0)

  useEffect(() => {
    const controlador = new AbortController()
    setEstado((previo) => ({ ...previo, cargando: true }))
    pedir(url, { signal: controlador.signal })
      .then((datos) => setEstado({ datos, error: null, cargando: false, actualizadoEn: new Date() }))
      .catch((error) => {
        if (error.name !== 'AbortError') setEstado((previo) => ({ ...previo, error, cargando: false }))
      })
    return () => controlador.abort()
  }, [url, version, reintentos])

  const recargar = useCallback(() => setReintentos((n) => n + 1), [])
  return { ...estado, recargar }
}
