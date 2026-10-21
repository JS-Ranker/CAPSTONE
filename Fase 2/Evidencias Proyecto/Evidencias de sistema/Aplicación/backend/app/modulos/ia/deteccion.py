"""Detección de deudores anómalos en un informe (RF08), sin base de datos.

Dos detectores que se complementan:
1. Reglas explicables, con umbrales que salen del historial (no fijos): monto muy sobre lo habitual de su
   tesorería, oficio muy antiguo o posterior a la recepción, expediente muy antiguo, RUT repetido varias veces
   en el mismo informe. Cada una dice por qué el caso es raro.
2. Un IsolationForest (scikit-learn) entrenado con el historial de casos, que encuentra combinaciones raras que
   ninguna regla mira por separado. Da además el puntaje de anomalía de cada caso.

Una alerta siempre trae al menos un motivo legible: si solo la marca el modelo, se explican los rasgos que más
se alejan de lo habitual.
"""
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from statistics import median

import numpy as np
from sklearn.ensemble import IsolationForest

ALTO, MEDIO, BAJO = "Alto", "Medio", "Bajo"
_ORDEN = {BAJO: 1, MEDIO: 2, ALTO: 3}
MINIMO_HISTORIAL = 40          # bajo esto el modelo no es confiable: solo reglas
# El modelo solo alerta lo que es más raro que todo el historial: un percentil (p. ej. el 1% más raro) siempre
# marcaría algo, aunque el informe sea normal.
MINIMO_POR_TESORERIA = 5       # casos para usar la mediana de una tesorería; si no, la global
MODELO = "IsolationForest (scikit-learn)"

RASGOS = ("monto", "monto_vs_tesoreria", "dias_oficio", "antiguedad_expediente", "repeticiones_rut")
NOMBRES = {
    "monto": "monto", "monto_vs_tesoreria": "monto comparado con su tesorería",
    "dias_oficio": "días entre el oficio y su recepción", "antiguedad_expediente": "antigüedad del expediente",
    "repeticiones_rut": "veces que aparece el RUT en el informe",
}


@dataclass(frozen=True)
class Motivo:
    rasgo: str
    texto: str
    nivel: str
    titulo: str = ""  # corto, para el título del insight; el detalle va en `texto`


@dataclass
class Anomalia:
    id_caso: int
    nivel: str
    puntaje: float | None
    motivos: list[Motivo] = field(default_factory=list)
    regla_sugerida: dict | None = None


def pesos(valor: float) -> str:
    return "$" + f"{valor:,.0f}".replace(",", ".")


def redondear_arriba(valor: float) -> float:
    """Dos cifras significativas hacia arriba: 2.734.512 -> 2.800.000 (umbral fácil de leer)."""
    if valor <= 0:
        return 0.0
    escala = 10 ** (int(math.floor(math.log10(valor))) - 1)
    return math.ceil(valor / escala) * escala


def _percentil(valores: list[float], p: float) -> float:
    return float(np.percentile(valores, p)) if valores else 0.0


class Referencia:
    """Lo habitual según el historial: medianas por tesorería y límites de cada rasgo."""

    def __init__(self, historial: list[dict]):
        montos = [float(c["monto"]) for c in historial if c.get("monto")]
        self.mediana_global = median(montos) if montos else 1.0
        por_tesoreria: dict[str, list[float]] = {}
        for caso in historial:
            if caso.get("monto") and caso.get("tesoreria"):
                por_tesoreria.setdefault(caso["tesoreria"], []).append(float(caso["monto"]))
        self.mediana_tesoreria = {t: median(v) for t, v in por_tesoreria.items() if len(v) >= MINIMO_POR_TESORERIA}
        self.limite_monto = redondear_arriba(_percentil(montos, 99)) if montos else 0.0
        dias = [d for c in historial if (d := dias_oficio(c)) is not None and d >= 0]
        self.mediana_dias = median(dias) if dias else 0.0
        self.limite_dias = max(_percentil(dias, 99) * 1.5, self.mediana_dias * 3, 90.0)
        antiguedades = [a for c in historial if (a := antiguedad_expediente(c)) is not None]
        self.mediana_antiguedad = median(antiguedades) if antiguedades else 0.0
        self.limite_antiguedad = max(_percentil(antiguedades, 99) + 3, 15.0)

    def mediana_de(self, tesoreria: str | None) -> float:
        return self.mediana_tesoreria.get(tesoreria or "", self.mediana_global) or 1.0


def dias_oficio(caso: dict) -> int | None:
    if not caso.get("fecha_oficio") or not caso.get("fec_ing"):
        return None
    return (caso["fec_ing"] - caso["fecha_oficio"]).days


def antiguedad_expediente(caso: dict) -> int | None:
    if not caso.get("rol_anio") or not caso.get("fec_ing"):
        return None
    return caso["fec_ing"].year - int(caso["rol_anio"])


def _repeticiones(casos: list[dict]) -> Counter:
    """Cuántas veces aparece cada (informe, RUT)."""
    return Counter((c.get("id_informe"), c.get("rut")) for c in casos)


def matriz(casos: list[dict], ref: Referencia, repeticiones: Counter) -> np.ndarray:
    filas = []
    for c in casos:
        monto = float(c.get("monto") or ref.mediana_global)
        dias = dias_oficio(c)
        antig = antiguedad_expediente(c)
        filas.append([
            math.log10(max(monto, 1.0)),
            math.log10(max(monto, 1.0) / ref.mediana_de(c.get("tesoreria"))),
            ref.mediana_dias if dias is None else dias,
            ref.mediana_antiguedad if antig is None else antig,
            repeticiones[(c.get("id_informe"), c.get("rut"))],
        ])
    return np.array(filas, dtype=float)


def motivos_por_reglas(caso: dict, ref: Referencia) -> list[Motivo]:
    motivos = []
    if caso.get("monto"):
        mediana = ref.mediana_de(caso.get("tesoreria"))
        veces = float(caso["monto"]) / mediana
        if veces >= 10:
            motivos.append(Motivo(
                "monto", titulo="Monto muy sobre lo habitual",
                texto=f"Monto de {pesos(caso['monto'])}: {veces:.0f} veces el monto habitual de su tesorería "
                      f"({pesos(mediana)}).",
                nivel=ALTO if veces >= 50 else MEDIO if veces >= 20 else BAJO,
            ))
    dias = dias_oficio(caso)
    if dias is not None and dias < 0:
        motivos.append(Motivo(
            "fecha_oficio", titulo="Fecha del oficio posterior a la recepción",
            texto=f"La fecha del oficio ({caso['fecha_oficio']:%d-%m-%Y}) es posterior a su recepción "
                  f"({caso['fec_ing']:%d-%m-%Y}): posible error de digitación o de lectura.",
            nivel=MEDIO,
        ))
    elif dias is not None and dias > ref.limite_dias:
        motivos.append(Motivo(
            "fecha_oficio", titulo="Oficio muy antiguo",
            texto=f"El oficio es de hace {dias} días; lo habitual es hasta {ref.limite_dias:.0f}.",
            nivel=MEDIO if dias > 365 else BAJO,
        ))
    antig = antiguedad_expediente(caso)
    if antig is not None and antig > ref.limite_antiguedad:
        motivos.append(Motivo(
            "expediente", titulo="Expediente muy antiguo",
            texto=f"El expediente es del año {caso['rol_anio']} ({antig} años de antigüedad).",
            nivel=BAJO,
        ))
    return motivos


def motivo_rut_repetido(casos_del_rut: list[dict]) -> Motivo:
    """Una sola alerta por RUT repetido, que nombra todos sus casos (en vez de una alerta igual por cada uno)."""
    veces = len(casos_del_rut)
    ids = ", ".join(f"#{c['id_caso']}" for c in casos_del_rut)
    return Motivo(
        "rut", titulo="RUT repetido en el informe",
        texto=f"El RUT {casos_del_rut[0]['rut']} aparece {veces} veces en este informe (casos {ids}): "
              "varias deudas del mismo deudor.",
        nivel=ALTO if veces >= 5 else MEDIO,
    )


def _motivo_del_modelo(fila: np.ndarray, base: np.ndarray) -> Motivo:
    """Explica una alerta que solo marcó el modelo: los rasgos que más se alejan de la mediana del historial."""
    mediana = np.median(base, axis=0)
    escala = np.median(np.abs(base - mediana), axis=0) * 1.4826
    escala = np.where(escala > 0, escala, np.maximum(base.std(axis=0), 1e-9))
    desvio = np.abs(fila - mediana) / escala
    principales = [RASGOS[i] for i in np.argsort(desvio)[::-1][:2] if desvio[i] >= 2]
    nombres = " y ".join(NOMBRES[r] for r in principales) or "varios rasgos a la vez"
    return Motivo(
        "modelo", titulo="Combinación de datos poco habitual",
        texto=f"Combinación poco habitual de datos ({nombres}), según el modelo entrenado con el historial de casos.",
        nivel=BAJO,
    )


def detectar(historial: list[dict], objetivo: list[dict], *, semilla: int = 0) -> tuple[list[Anomalia], dict]:
    """Busca anomalías en `objetivo` (los casos de un informe) comparándolos con `historial` (casos anteriores).

    Devuelve las anomalías ordenadas de más a menos grave, y datos del análisis para el resumen.
    """
    suficiente = len(historial) >= MINIMO_HISTORIAL
    base = historial if suficiente else historial + objetivo   # sin historial, el informe se compara consigo mismo
    ref = Referencia(base)
    repeticiones = _repeticiones(historial + objetivo)

    puntajes: np.ndarray | None = None
    umbral = None
    if len(base) >= MINIMO_HISTORIAL and objetivo:
        x_base = matriz(base, ref, repeticiones)
        modelo = IsolationForest(n_estimators=200, random_state=semilla).fit(x_base)
        base_puntajes = -modelo.score_samples(x_base)              # mayor = más anómalo
        umbral = float(base_puntajes.max())
        x_objetivo = matriz(objetivo, ref, repeticiones)
        puntajes = -modelo.score_samples(x_objetivo)

    # RUT repetidos 3 o más veces en el informe: el motivo va solo en el primero de sus casos.
    por_rut: dict[str, list[dict]] = {}
    for caso in objetivo:
        por_rut.setdefault(caso.get("rut"), []).append(caso)
    primero_del_rut = {grupo[0]["id_caso"]: grupo for grupo in por_rut.values() if len(grupo) >= 3}
    resto_del_rut = {c["id_caso"] for grupo in primero_del_rut.values() for c in grupo[1:]}

    anomalias = []
    for i, caso in enumerate(objetivo):
        motivos = motivos_por_reglas(caso, ref)
        if caso["id_caso"] in primero_del_rut:
            motivos.append(motivo_rut_repetido(primero_del_rut[caso["id_caso"]]))
        puntaje = float(puntajes[i]) if puntajes is not None else None
        if not motivos and puntaje is not None and puntaje > umbral and caso["id_caso"] not in resto_del_rut:
            motivos = [_motivo_del_modelo(matriz([caso], ref, repeticiones)[0], matriz(base, ref, repeticiones))]
        if not motivos:
            continue
        nivel = max((m.nivel for m in motivos), key=_ORDEN.get)
        regla = None
        if any(m.rasgo == "monto" for m in motivos) and ref.limite_monto:
            regla = {"tipo": "monto_maximo", "valor": ref.limite_monto}
        anomalias.append(Anomalia(caso["id_caso"], nivel, puntaje, motivos, regla))

    anomalias.sort(key=lambda a: (_ORDEN[a.nivel], a.puntaje or 0), reverse=True)
    info = {"modelo": MODELO if puntajes is not None else "Solo reglas (historial insuficiente)",
            "casos_historial": len(historial), "limite_monto": ref.limite_monto}
    return anomalias, info
