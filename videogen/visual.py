"""Construcción del clip de vídeo de una escena (imagen, vídeo o tarjeta)."""

from __future__ import annotations

from pathlib import Path

from ffmpeg_tools import run, tiene_filtro
from guion import Escena, Guion

FONDO = "0x0d1117"
RUTAS_FUENTE = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]
_avisos: set[str] = set()


def buscar_fuente() -> str | None:
    return next((r for r in RUTAS_FUENTE if Path(r).exists()), None)


def _hay_pillow() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _avisar(clave: str, mensaje: str) -> None:
    if clave not in _avisos:
        _avisos.add(clave)
        print(f"  Aviso: {mensaje}")


def _escapar(ruta: Path | str) -> str:
    """Escapa una ruta para usarla dentro de un argumento de filtro."""
    return str(ruta).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _rotulo_png(texto: str, guion: Guion, destino: Path) -> Path | None:
    """Rótulo como PNG transparente, para ffmpeg sin el filtro drawtext."""
    from PIL import Image, ImageDraw, ImageFont

    fuente_ruta = buscar_fuente()
    if not fuente_ruta:
        return None
    tamano = max(guion.alto // 22, 16)
    fuente = ImageFont.truetype(fuente_ruta, tamano)
    margen = tamano // 2
    medida = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=fuente)
    ancho = medida[2] - medida[0] + margen * 2
    alto = medida[3] - medida[1] + margen * 2
    img = Image.new("RGBA", (ancho + ancho % 2, alto + alto % 2), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(img)
    dibujo.rounded_rectangle([0, 0, img.width - 1, img.height - 1], tamano // 4, fill=(0, 0, 0, 140))
    dibujo.text((margen - medida[0], margen - medida[1]), texto, font=fuente, fill=(255, 255, 255, 255))
    img.save(destino)
    return destino


def _cadena_imagen(escena: Escena, guion: Guion, frames: int) -> str:
    """Ken Burns: escalamos al doble y recortamos con zoompan para no perder nitidez."""
    ancho2, alto2 = guion.ancho * 2, guion.alto * 2
    ultimo = max(frames - 1, 1)
    zoom_max = 0.14
    centrado = ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)")
    if escena.efecto == "zoom-in":
        z, (x, y) = f"1+{zoom_max}*on/{ultimo}", centrado
    elif escena.efecto == "zoom-out":
        z, (x, y) = f"{1 + zoom_max}-{zoom_max}*on/{ultimo}", centrado
    elif escena.efecto == "pan-derecha":
        z, x, y = "1.12", f"(iw-iw/zoom)*on/{ultimo}", centrado[1]
    elif escena.efecto == "pan-izquierda":
        z, x, y = "1.12", f"(iw-iw/zoom)*(1-on/{ultimo})", centrado[1]
    else:  # estatico
        z, (x, y) = "1", centrado

    return (
        f"[0:v]scale={ancho2}:{alto2}:force_original_aspect_ratio=decrease,"
        f"pad={ancho2}:{alto2}:(ow-iw)/2:(oh-ih)/2:color={FONDO},setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={guion.ancho}x{guion.alto}:fps={guion.fps}"
    )


def _cadena_video(guion: Guion, dur: float) -> str:
    return (
        f"[0:v]scale={guion.ancho}:{guion.alto}:force_original_aspect_ratio=decrease,"
        f"pad={guion.ancho}:{guion.alto}:(ow-iw)/2:(oh-ih)/2:color={FONDO},setsar=1,"
        f"fps={guion.fps},trim=0:{dur:.3f},setpts=PTS-STARTPTS"
    )


def construir(escena: Escena, guion: Guion, audio: Path, dur: float, salida: Path,
              *, srt: Path | None = None, primera: bool = False, ultima: bool = False,
              crf: int = 20, preset: str = "medium") -> Path:
    """Renderiza la escena a un MP4 con vídeo y narración ya mezclados."""
    visual = escena.resolver_visual(guion.base)
    frames = max(int(round(dur * guion.fps)), 2)
    entradas: list[str] = []

    if visual is None:
        entradas += ["-f", "lavfi", "-i",
                     f"color=c={FONDO}:s={guion.ancho}x{guion.alto}:r={guion.fps}:d={dur:.3f}"]
        cadena = "[0:v]setsar=1"
    elif escena.es_video:
        entradas += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(visual)]
        cadena = _cadena_video(guion, dur)
    else:
        entradas += ["-i", str(visual)]
        cadena = _cadena_imagen(escena, guion, frames)

    entradas += ["-i", str(audio)]           # el audio es siempre la entrada 1
    hasta = min(4.2, max(dur - 0.3, 1.0))
    fuente = buscar_fuente()
    segmentos: list[str] = []
    posteriores: list[str] = []

    if escena.titulo and tiene_filtro("drawtext") and fuente:
        rotulo = salida.with_suffix(".titulo.txt")
        rotulo.write_text(escena.titulo, encoding="utf-8")
        posteriores.append(
            f"drawtext=fontfile='{_escapar(fuente)}':textfile='{_escapar(rotulo)}':"
            f"fontsize={guion.alto // 22}:fontcolor=white:x={guion.ancho // 24}:y={guion.alto // 14}:"
            f"box=1:boxcolor=black@0.55:boxborderw={guion.alto // 54}:"
            f"enable='between(t,0.25,{hasta:.2f})'"
        )
    elif escena.titulo and _hay_pillow():
        png = _rotulo_png(escena.titulo, guion, salida.with_suffix(".titulo.png"))
        if png:
            entradas += ["-i", str(png)]     # entrada 2
            segmentos.append(cadena + "[vb]")
            cadena = (f"[vb][2:v]overlay=x={guion.ancho // 24}:y={guion.alto // 14}:"
                      f"enable='between(t,0.25,{hasta:.2f})'")
    elif escena.titulo:
        _avisar("titulo", "tu ffmpeg no trae 'drawtext' y no hay Pillow: omito los rótulos "
                          "(pip install pillow lo arregla).")

    if srt is not None:
        if tiene_filtro("subtitles"):
            posteriores.append(
                f"subtitles='{_escapar(srt)}':force_style='FontName=DejaVu Sans,FontSize=12,"
                f"PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,BorderStyle=3,Outline=2,"
                f"Shadow=0,Alignment=2,MarginV=28'"
            )
        else:
            _avisar("subs", "tu ffmpeg no trae el filtro 'subtitles' (libass): el .srt se genera "
                            "aparte pero no se incrusta.")

    if primera:
        posteriores.append("fade=t=in:st=0:d=0.5")
    if ultima and dur > 1.2:
        posteriores.append(f"fade=t=out:st={dur - 0.6:.3f}:d=0.6")
    posteriores.append("format=yuv420p")

    segmentos.append(",".join([cadena, *posteriores]) + "[v]")
    segmentos.append(
        f"[1:a]aresample=48000,adelay=delays=250:all=1,apad,atrim=0:{dur:.3f},"
        f"asetpts=N/SR/TB,afade=t=in:st=0:d=0.08,afade=t=out:st={max(dur - 0.18, 0):.3f}:d=0.18[a]"
    )

    run([
        *entradas,
        "-filter_complex", ";".join(segmentos),
        "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-r", str(guion.fps),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        str(salida),
    ])
    return salida
