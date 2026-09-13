"""Localización del binario de ffmpeg y utilidades de ejecución."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def _from_imageio(name: str) -> str | None:
    """imageio-ffmpeg trae un ffmpeg estático; ffprobe no viene incluido."""
    if name != "ffmpeg":
        return None
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        return None
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    return path if path and os.path.exists(path) else None


def find_ffmpeg() -> str:
    return os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or _from_imageio("ffmpeg") or _fail("ffmpeg")


def find_ffprobe() -> str | None:
    """ffprobe es opcional: sin él medimos duraciones con ffmpeg."""
    return os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe")


def _fail(name: str) -> str:
    raise FFmpegError(
        f"No encuentro '{name}'. Instala ffmpeg del sistema o ejecuta "
        "`pip install imageio-ffmpeg`, o define FFMPEG_BIN con la ruta al binario."
    )


def run(args: list[str], *, quiet: bool = True) -> None:
    """Ejecuta ffmpeg y levanta FFmpegError con el final del log si falla."""
    cmd = [find_ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg falló ({proc.returncode}):\n{tail}\n\ncomando: {' '.join(cmd)}")
    if not quiet and proc.stderr.strip():
        print(proc.stderr.strip())


def duracion(path: str | Path) -> float:
    """Duración en segundos de un audio o vídeo."""
    path = str(path)
    probe = find_ffprobe()
    if probe:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-print_format", "json", path],
            capture_output=True, text=True,
        )
        if out.returncode == 0:
            try:
                return float(json.loads(out.stdout)["format"]["duration"])
            except (KeyError, ValueError, json.JSONDecodeError):
                pass

    # Sin ffprobe: decodificamos a null y leemos el tiempo final del log.
    out = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-nostdin", "-i", path, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    marca = 0.0
    for linea in out.stderr.splitlines():
        if "time=" in linea:
            crudo = linea.split("time=")[-1].split(" ")[0]
            try:
                h, m, s = crudo.split(":")
                marca = max(marca, int(h) * 3600 + int(m) * 60 + float(s))
            except ValueError:
                continue
    if marca <= 0:
        raise FFmpegError(f"No consigo medir la duración de {path}")
    return marca


@lru_cache(maxsize=None)
def tiene_filtro(nombre: str) -> bool:
    out = subprocess.run([find_ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True)
    return any(linea.split()[1:2] == [nombre] for linea in out.stdout.splitlines() if linea.strip())
