"""Síntesis de voz con varios motores intercambiables y caché en disco.

Orden de preferencia en modo 'auto': kokoro > piper > espeak > silencio.
'silencio' genera una pista muda de la duración estimada, para poder montar
y revisar el vídeo entero sin tener ningún motor de voz instalado.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from ffmpeg_tools import duracion, run

PALABRAS_POR_SEGUNDO = 2.6  # ritmo de locución en castellano


class VozError(RuntimeError):
    pass


def _hay_kokoro() -> bool:
    try:
        import kokoro  # type: ignore  # noqa: F401
    except Exception:
        return False
    return True


def backends_disponibles() -> list[str]:
    disponibles = []
    if _hay_kokoro():
        disponibles.append("kokoro")
    if shutil.which("piper"):
        disponibles.append("piper")
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        disponibles.append("espeak")
    disponibles.append("silencio")
    return disponibles


def resolver_backend(pedido: str) -> str:
    disponibles = backends_disponibles()
    if pedido in ("auto", ""):
        return disponibles[0]
    if pedido not in disponibles:
        raise VozError(
            f"El motor de voz '{pedido}' no está disponible. Instalados: {', '.join(disponibles)}."
        )
    return pedido


def duracion_estimada(texto: str) -> float:
    return max(1.5, len(texto.split()) / PALABRAS_POR_SEGUNDO + 0.6)


def sintetizar(texto: str, destino: Path, *, backend: str, idioma: str = "es",
               velocidad: float = 1.0, nombre_voz: str = "", cache: Path | None = None) -> Path:
    """Genera un WAV con la narración. Devuelve la ruta (posiblemente cacheada)."""
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        clave = hashlib.sha256(
            "|".join([backend, idioma, nombre_voz, f"{velocidad:.3f}", texto]).encode("utf-8")
        ).hexdigest()[:16]
        cacheado = cache / f"{backend}-{clave}.wav"
        if cacheado.exists():
            shutil.copyfile(cacheado, destino)
            return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    generador = {
        "kokoro": _kokoro,
        "piper": _piper,
        "espeak": _espeak,
        "silencio": _silencio,
    }[backend]
    generador(texto, destino, idioma=idioma, velocidad=velocidad, nombre_voz=nombre_voz)

    if not destino.exists() or destino.stat().st_size < 1024:
        raise VozError(f"El motor '{backend}' no produjo audio para: {texto[:60]}...")
    if cache:
        shutil.copyfile(destino, cacheado)
    return destino


def _kokoro(texto: str, destino: Path, *, idioma: str, velocidad: float, nombre_voz: str) -> None:
    """Kokoro-82M (Apache 2.0). Corre en CPU; 'e' es el código de español."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende del entorno del usuario
        raise VozError(
            "Falta alguna dependencia de kokoro. Instala: pip install kokoro soundfile numpy"
        ) from exc

    codigos = {"es": "e", "en": "a", "pt": "p", "fr": "f", "it": "i"}
    pipeline = KPipeline(lang_code=codigos.get(idioma, "e"))
    voz = nombre_voz or ("ef_dora" if idioma == "es" else "af_heart")
    trozos = [audio for _, _, audio in pipeline(texto, voice=voz, speed=velocidad)]
    if not trozos:
        raise VozError("Kokoro no devolvió audio")
    sf.write(str(destino), np.concatenate(trozos), 24000)


def _piper(texto: str, destino: Path, *, idioma: str, velocidad: float, nombre_voz: str) -> None:
    """Piper necesita un modelo .onnx descargado; se indica en voz.nombre."""
    modelo = nombre_voz or os.environ.get("PIPER_VOICE", "")
    if not modelo:
        raise VozError(
            "Piper necesita la ruta al modelo de voz: pon 'nombre: /ruta/voz.onnx' "
            "en la sección 'voz' del guion, o exporta PIPER_VOICE."
        )
    proc = subprocess.run(
        ["piper", "--model", modelo, "--length_scale", f"{1 / max(velocidad, 0.1):.3f}",
         "--output_file", str(destino)],
        input=texto, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        raise VozError(f"piper falló: {proc.stderr.strip()[:300]}")


def _espeak(texto: str, destino: Path, *, idioma: str, velocidad: float, nombre_voz: str) -> None:
    """Voz robótica, pero offline y sin GPU: sirve para validar tiempos y montaje."""
    binario = shutil.which("espeak-ng") or shutil.which("espeak")
    proc = subprocess.run(
        [binario, "-v", nombre_voz or idioma, "-s", str(int(160 * velocidad)),
         "-w", str(destino), "--stdin"],
        input=texto, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        raise VozError(f"espeak falló: {proc.stderr.strip()[:300]}")


def _silencio(texto: str, destino: Path, *, idioma: str, velocidad: float, nombre_voz: str) -> None:
    segundos = duracion_estimada(texto) / max(velocidad, 0.1)
    run(["-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
         "-t", f"{segundos:.3f}", "-c:a", "pcm_s16le", str(destino)])


def medir(ruta: Path) -> float:
    return duracion(ruta)
