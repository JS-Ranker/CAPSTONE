// Nombre de archivo que solo se parte después de un guion bajo: "22_informe_pdf_texto…" nunca queda cortado a media palabra.
export function NombreArchivo({ nombre }) {
  const partes = String(nombre ?? '').split('_')
  return partes.map((parte, i) => (
    <span key={i}>{parte}{i < partes.length - 1 && <>_<wbr /></>}</span>
  ))
}
