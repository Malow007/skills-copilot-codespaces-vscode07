"""Orquestación: guion -> narración -> clips -> vídeo final."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import subtitulos
import visual
import voz
from ffmpeg_tools import run
from guion import Guion

COLA = 0.5      # silencio al final de cada escena
CABEZA = 0.25   # respiro antes de que empiece a hablar (coincide con el adelay)
MINIMO = 2.0    # ninguna escena baja de aquí aunque la frase sea muy corta


@dataclass
class Resultado:
    video: Path
    srt: Path | None
    duracion: float
    escenas: int
    backend_voz: str


def renderizar(g: Guion, salida: Path, *, trabajo: Path | None = None, crf: int = 20,
               preset: str = "medium", conservar: bool = False, log=print) -> Resultado:
    backend = voz.resolver_backend(g.voz_backend)
    salida = Path(salida).resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    trabajo = Path(trabajo).resolve() if trabajo else salida.parent / f".videogen-{salida.stem}"
    trabajo.mkdir(parents=True, exist_ok=True)
    cache = trabajo / "cache-voz"

    log(f"Motor de voz: {backend}  |  {len(g.escenas)} escenas  |  {g.resolucion} @ {g.fps}fps")
    if backend == "silencio":
        log("  Aviso: sin motor de voz instalado, el vídeo saldrá mudo con los tiempos estimados.")

    clips: list[Path] = []
    lineas_globales: list[subtitulos.Linea] = []
    reloj = 0.0
    arranque = time.time()

    for escena in g.escenas:
        n = escena.indice + 1
        audio = trabajo / f"voz-{n:03d}.wav"
        voz.sintetizar(escena.narracion, audio, backend=backend, idioma=g.voz_idioma,
                       velocidad=g.voz_velocidad, nombre_voz=g.voz_nombre, cache=cache)
        dur_voz = voz.medir(audio)
        dur = max(CABEZA + dur_voz + COLA, escena.duracion_min, MINIMO)

        srt_local = None
        lineas = subtitulos.lineas_escena(escena.narracion, dur_voz, CABEZA)
        if g.subtitulos:
            srt_local = trabajo / f"sub-{n:03d}.srt"
            srt_local.write_text(subtitulos.a_srt(lineas), encoding="utf-8")
        lineas_globales += [
            subtitulos.Linea(l.inicio + reloj, l.fin + reloj, l.texto) for l in lineas
        ]

        clip = trabajo / f"escena-{n:03d}.mp4"
        etiqueta = escena.titulo or escena.narracion[:42]
        log(f"  [{n}/{len(g.escenas)}] {dur:5.1f}s  {etiqueta}")
        visual.construir(escena, g, audio, dur, clip, srt=srt_local,
                         primera=(n == 1), ultima=(n == len(g.escenas)), crf=crf, preset=preset)
        clips.append(clip)
        reloj += dur

    lista = trabajo / "clips.txt"
    lista.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    montado = trabajo / "montado.mp4"
    log("  Uniendo escenas...")
    run(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(montado)])

    if g.musica:
        pista = Path(g.musica)
        pista = pista if pista.is_absolute() else g.base / pista
        if not pista.exists():
            raise FileNotFoundError(f"No encuentro la música de fondo: {pista}")
        log("  Mezclando música de fondo...")
        mezcla = (
            f"[1:a]volume=0.10,afade=t=out:st={max(reloj - 2.5, 0):.2f}:d=2.5[m];"
            f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0,"
            f"alimiter=limit=0.95[a]"
        )
        run(["-i", str(montado), "-stream_loop", "-1", "-i", str(pista),
             "-filter_complex", mezcla, "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             str(salida)])
    else:
        run(["-i", str(montado), "-c", "copy", "-movflags", "+faststart", str(salida)])

    srt_final = None
    if g.subtitulos:
        srt_final = salida.with_suffix(".srt")
        srt_final.write_text(subtitulos.a_srt(lineas_globales), encoding="utf-8")

    if not conservar:
        shutil.rmtree(trabajo, ignore_errors=True)

    log(f"Listo en {time.time() - arranque:.0f}s: {salida} ({reloj:.1f}s)")
    return Resultado(salida, srt_final, reloj, len(g.escenas), backend)
