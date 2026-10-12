// Textos compartidos de la Bandeja de Excepciones (CU05).

export const TIPOS = { caso: 'Revisión de extracción', rechazo: 'Rechazo del ETL' }

// RUT tal como llegó en el CSV (puede venir incompleto o con el DV equivocado).
export const rutOriginal = (fila) => (fila.rut || fila.dv ? `${fila.rut || '?'}-${fila.dv || '?'}` : '—')
