"""Modelo del guion: carga desde YAML y conversión desde un guion en texto plano."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EFECTOS = {"zoom-in", "zoom-out", "pan-derecha", "pan-izquierda", "estatico"}
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
EXT_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".avi"}


class GuionError(ValueError):
    pass


@dataclass
class Escena:
    narracion: str
    titulo: str = ""
    visual: str | None = None
    efecto: str = "zoom-in"
    duracion_min: float = 0.0
    indice: int = 0

    @property
    def es_video(self) -> bool:
        return self.visual is not None and Path(self.visual).suffix.lower() in EXT_VIDEO

    def resolver_visual(self, base: Path) -> Path | None:
        if not self.visual:
            return None
        ruta = Path(self.visual)
        ruta = ruta if ruta.is_absolute() else base / ruta
        if not ruta.exists():
            raise GuionError(f"Escena {self.indice + 1}: no encuentro el visual '{self.visual}' ({ruta})")
        if ruta.suffix.lower() not in EXT_IMAGEN | EXT_VIDEO:
            raise GuionError(f"Escena {self.indice + 1}: formato no soportado '{ruta.suffix}'")
        return ruta


@dataclass
class Guion:
    proyecto: str = "video"
    escenas: list[Escena] = field(default_factory=list)
    ancho: int = 1920
    alto: int = 1080
    fps: int = 30
    voz_backend: str = "auto"
    voz_idioma: str = "es"
    voz_velocidad: float = 1.0
    voz_nombre: str = ""
    subtitulos: bool = True
    musica: str | None = None
    base: Path = Path(".")

    @property
    def resolucion(self) -> str:
        return f"{self.ancho}x{self.alto}"


def cargar(ruta: str | Path) -> Guion:
    ruta = Path(ruta)
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    if not isinstance(datos, dict):
        raise GuionError(f"{ruta}: el guion debe ser un mapa YAML")

    video = datos.get("video") or {}
    voz = datos.get("voz") or {}
    resolucion = str(video.get("resolucion", "1920x1080")).lower()
    if not re.fullmatch(r"\d+x\d+", resolucion):
        raise GuionError(f"resolucion inválida: '{resolucion}' (formato esperado: 1920x1080)")
    ancho, alto = (int(v) for v in resolucion.split("x"))
    if ancho % 2 or alto % 2:
        raise GuionError("El ancho y el alto deben ser pares (requisito de H.264)")

    crudas = datos.get("escenas")
    if not crudas:
        raise GuionError(f"{ruta}: no hay ninguna escena en 'escenas'")

    escenas: list[Escena] = []
    for i, cruda in enumerate(crudas):
        if isinstance(cruda, str):
            cruda = {"narracion": cruda}
        if not isinstance(cruda, dict):
            raise GuionError(f"Escena {i + 1}: se esperaba texto o un mapa, llegó {type(cruda).__name__}")
        narracion = str(cruda.get("narracion", "")).strip()
        if not narracion:
            raise GuionError(f"Escena {i + 1}: falta 'narracion'")
        efecto = str(cruda.get("efecto", "zoom-in")).strip().lower()
        if efecto not in EFECTOS:
            raise GuionError(f"Escena {i + 1}: efecto '{efecto}' desconocido. Válidos: {sorted(EFECTOS)}")
        escenas.append(Escena(
            narracion=narracion,
            titulo=str(cruda.get("titulo", "")).strip(),
            visual=cruda.get("visual"),
            efecto=efecto,
            duracion_min=float(cruda.get("duracion_min", 0) or 0),
            indice=i,
        ))

    guion = Guion(
        proyecto=str(datos.get("proyecto", ruta.stem)),
        escenas=escenas,
        ancho=ancho,
        alto=alto,
        fps=int(video.get("fps", 30)),
        voz_backend=str(voz.get("backend", "auto")).lower(),
        voz_idioma=str(voz.get("idioma", "es")),
        voz_velocidad=float(voz.get("velocidad", 1.0)),
        voz_nombre=str(voz.get("nombre", "")),
        subtitulos=bool(datos.get("subtitulos", True)),
        musica=datos.get("musica"),
        base=ruta.parent,
    )
    for escena in guion.escenas:  # valida rutas antes de gastar un minuto de render
        escena.resolver_visual(guion.base)
    return guion


def desde_texto(ruta_texto: str | Path, carpeta_assets: str | Path | None = None) -> dict:
    """Convierte un guion en texto plano en la estructura YAML del pipeline.

    Formato admitido: títulos con '#' y párrafos debajo, o simplemente
    párrafos separados por una línea en blanco (una escena por párrafo).
    Los visuales de la carpeta de assets se reparten en orden.
    """
    texto = Path(ruta_texto).read_text(encoding="utf-8")
    bloques: list[tuple[str, list[str]]] = []
    titulo, parrafos, acumulado = "", [], []

    def cerrar() -> None:
        if acumulado:
            parrafos.append(" ".join(acumulado).strip())
            acumulado.clear()

    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.startswith("#"):
            cerrar()
            if parrafos:
                bloques.append((titulo, parrafos[:]))
                parrafos.clear()
            titulo = limpia.lstrip("#").strip()
        elif not limpia:
            cerrar()
        else:
            acumulado.append(limpia)
    cerrar()
    if parrafos:
        bloques.append((titulo, parrafos[:]))

    escenas: list[dict] = []
    for titulo_bloque, textos in bloques:
        for j, parrafo in enumerate(textos):
            escenas.append({"titulo": titulo_bloque if j == 0 else "", "narracion": parrafo})
    if not escenas:
        raise GuionError(f"{ruta_texto}: no he encontrado texto para narrar")

    visuales: list[str] = []
    if carpeta_assets:
        carpeta = Path(carpeta_assets)
        visuales = [
            str(p.relative_to(carpeta.parent)) if carpeta.parent != Path(".") else str(p)
            for p in sorted(carpeta.iterdir())
            if p.suffix.lower() in EXT_IMAGEN | EXT_VIDEO
        ]

    efectos = ["zoom-in", "pan-derecha", "zoom-out", "pan-izquierda"]
    for i, escena in enumerate(escenas):
        if visuales:
            escena["visual"] = visuales[i % len(visuales)]
        escena["efecto"] = efectos[i % len(efectos)]

    return {
        "proyecto": Path(ruta_texto).stem,
        "video": {"resolucion": "1920x1080", "fps": 30},
        "voz": {"backend": "auto", "idioma": "es", "velocidad": 1.0},
        "subtitulos": True,
        "escenas": escenas,
    }


def volcar_yaml(datos: dict) -> str:
    return yaml.safe_dump(datos, allow_unicode=True, sort_keys=False, width=100)
