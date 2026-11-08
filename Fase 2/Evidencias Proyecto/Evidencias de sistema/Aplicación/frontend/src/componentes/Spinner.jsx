// Indicador de carga en línea: hereda el color y el tamaño del texto que lo rodea. Es decorativo (aria-hidden):
// el texto que lo acompaña ("Cargando…") y las regiones aria-live son lo que lee un lector de pantalla.
export function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}
