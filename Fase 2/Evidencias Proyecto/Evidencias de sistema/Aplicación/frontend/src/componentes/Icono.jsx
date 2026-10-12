// Íconos de línea (24×24, trazo de 1,75). Son decorativos: el texto que los acompaña da el significado.
const TRAZOS = {
  ingesta: ['M12 3v11', 'm8 10 4 4 4-4', 'M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4'],
  casos: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.01', 'M4.5 12h.01', 'M4.5 18h.01'],
  dashboard: ['M4 4h6v7H4z', 'M14 4h6v4h-6z', 'M14 12h6v8h-6z', 'M4 15h6v5H4z'],
  excepciones: ['M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z', 'M12 9.5v4', 'M12 17h.01'],
  reportes: ['M4 4v16h16', 'M8.5 16v-4', 'M13 16V8', 'M17.5 16v-6'],
  bitacora: ['M6 3.5h12a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1Z', 'M9 8h6', 'M9 12h6', 'M9 16h4'],
  usuarios: ['M9 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M2.5 20c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5', 'M16 4.6a3.5 3.5 0 0 1 0 6.8', 'M21.5 20c0-2.6-1.5-4.5-3.8-5.2'],
  subir: ['M12 15V4', 'm7.5 8.5 4.5-4.5 4.5 4.5', 'M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4'],
  archivo: ['M14 3.5H7a1 1 0 0 0-1 1v15a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7.5Z', 'M14 3.5v4h4'],
  correo: ['M4 5.5h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1Z', 'm3.5 6.5 8.5 6.5 8.5-6.5'],
  servidor: ['M5 4h14a1 1 0 0 1 1 1v5H4V5a1 1 0 0 1 1-1Z', 'M4 14h16v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z', 'M4 10v4', 'M20 10v4', 'M8 7h.01', 'M8 17h.01'],
}

export function Icono({ nombre, tamano = 20 }) {
  return (
    <svg
      className="icono"
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {TRAZOS[nombre].map((trazo) => <path key={trazo} d={trazo} />)}
    </svg>
  )
}
