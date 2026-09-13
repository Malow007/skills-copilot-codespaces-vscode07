"""Generación de subtítulos SRT a partir de la narración de cada escena."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CARACTERES = 84  # dos líneas de ~42, que es lo legible a 1080p


@dataclass
class Linea:
    inicio: float
    fin: float
    texto: str


def trocear(texto: str, maximo: int = MAX_CARACTERES) -> list[str]:
    """Parte la narración en bloques de subtítulo respetando las palabras."""
    trozos: list[str] = []
    actual: list[str] = []
    largo = 0
    for palabra in texto.split():
        extra = len(palabra) + (1 if actual else 0)
        if actual and largo + extra > maximo:
            trozos.append(" ".join(actual))
            actual, largo = [palabra], len(palabra)
        else:
            actual.append(palabra)
            largo += extra
    if actual:
        trozos.append(" ".join(actual))
    return trozos or [texto]


def partir_en_dos(trozo: str) -> str:
    """Reparte un bloque largo en dos líneas equilibradas."""
    if len(trozo) <= 46:
        return trozo
    palabras = trozo.split()
    mitad = len(trozo) / 2
    corte, mejor, recorrido = 1, float("inf"), 0
    for i, palabra in enumerate(palabras[:-1], start=1):
        recorrido += len(palabra) + 1
        if abs(recorrido - mitad) < mejor:
            mejor, corte = abs(recorrido - mitad), i
    return " ".join(palabras[:corte]) + "\n" + " ".join(palabras[corte:])


def lineas_escena(texto: str, duracion: float, desplazamiento: float = 0.0) -> list[Linea]:
    """Reparte el tiempo de la escena entre sus bloques, proporcional al texto."""
    trozos = trocear(texto)
    total = sum(len(t) for t in trozos) or 1
    lineas: list[Linea] = []
    reloj = desplazamiento
    for i, trozo in enumerate(trozos):
        porcion = duracion * len(trozo) / total
        fin = desplazamiento + duracion if i == len(trozos) - 1 else reloj + porcion
        lineas.append(Linea(reloj, max(fin, reloj + 0.4), partir_en_dos(trozo)))
        reloj = fin
    return lineas


def _marca(segundos: float) -> str:
    segundos = max(0.0, segundos)
    horas, resto = divmod(int(segundos), 3600)
    minutos, seg = divmod(resto, 60)
    milis = int(round((segundos - int(segundos)) * 1000))
    return f"{horas:02d}:{minutos:02d}:{seg:02d},{milis:03d}"


def a_srt(lineas: list[Linea]) -> str:
    bloques = [
        f"{i}\n{_marca(linea.inicio)} --> {_marca(linea.fin)}\n{linea.texto}\n"
        for i, linea in enumerate(lineas, start=1)
    ]
    return "\n".join(bloques)
