// Anterior / Siguiente para las tablas paginadas. No se muestra si todo cabe en una página.
export function Paginacion({ pagina, total, porPagina, onCambiar, etiqueta }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina))
  if (paginas <= 1) return null
  return (
    <nav className="paginacion" aria-label={etiqueta}>
      <button type="button" className="boton boton--compacto" disabled={pagina === 0} onClick={() => onCambiar(pagina - 1)}>
        Anterior
      </button>
      <span>Página {pagina + 1} de {paginas}</span>
      <button
        type="button"
        className="boton boton--compacto"
        disabled={pagina + 1 >= paginas}
        onClick={() => onCambiar(pagina + 1)}
      >
        Siguiente
      </button>
    </nav>
  )
}
