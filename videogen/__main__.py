"""Interfaz de línea de comandos de videogen."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guion as guion_mod  # noqa: E402
import visual  # noqa: E402
import voz  # noqa: E402
from ffmpeg_tools import FFmpegError, find_ffmpeg, find_ffprobe  # noqa: E402
from render import renderizar  # noqa: E402


def cmd_render(args: argparse.Namespace) -> int:
    g = guion_mod.cargar(args.guion)
    if args.voz:
        g.voz_backend = args.voz
    if args.sin_subtitulos:
        g.subtitulos = False
    salida = Path(args.salida or f"{g.proyecto}.mp4")
    resultado = renderizar(g, salida, crf=args.crf, preset=args.preset,
                           conservar=args.conservar_temporales)
    if resultado.srt:
        print(f"Subtítulos: {resultado.srt}")
    return 0


def cmd_guion(args: argparse.Namespace) -> int:
    datos = guion_mod.desde_texto(args.texto, args.assets)
    yaml_txt = guion_mod.volcar_yaml(datos)
    if args.salida:
        Path(args.salida).write_text(yaml_txt, encoding="utf-8")
        print(f"Guion escrito en {args.salida} ({len(datos['escenas'])} escenas). "
              "Revísalo y ajusta 'visual' y 'efecto' antes de renderizar.")
    else:
        print(yaml_txt)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print("videogen — diagnóstico del entorno\n")
    try:
        print(f"  ffmpeg   : {find_ffmpeg()}")
    except FFmpegError as exc:
        print(f"  ffmpeg   : NO ENCONTRADO\n             {exc}")
        return 1
    print(f"  ffprobe  : {find_ffprobe() or 'no instalado (se mide con ffmpeg, sin problema)'}")
    print(f"  fuente   : {visual.buscar_fuente() or 'ninguna (sin rótulos ni subtítulos incrustados)'}")
    disponibles = voz.backends_disponibles()
    print(f"  voz      : {', '.join(disponibles)}  ->  se usaría '{disponibles[0]}'")
    if disponibles[0] == "silencio":
        print("\n  Para tener voz de verdad: pip install kokoro soundfile  (Apache 2.0, CPU)")
        print("  o bien un motor del sistema: apt install espeak-ng")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="videogen",
        description="Monta vídeos de demo de software a partir de un guion y unas capturas.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_render = sub.add_parser("render", help="renderiza el vídeo a partir de un guion YAML")
    p_render.add_argument("guion", help="ruta al guion .yaml")
    p_render.add_argument("-o", "--salida", help="fichero MP4 de salida")
    p_render.add_argument("--voz", choices=["auto", "kokoro", "piper", "espeak", "silencio"],
                          help="fuerza el motor de voz")
    p_render.add_argument("--sin-subtitulos", action="store_true", help="no incrustar subtítulos")
    p_render.add_argument("--crf", type=int, default=20, help="calidad H.264 (menor = mejor, 18-24)")
    p_render.add_argument("--preset", default="medium", help="preset de x264 (ultrafast..veryslow)")
    p_render.add_argument("--conservar-temporales", action="store_true",
                          help="no borrar la carpeta de trabajo (útil para depurar)")
    p_render.set_defaults(func=cmd_render)

    p_guion = sub.add_parser("guion", help="convierte un guion en texto plano a guion YAML")
    p_guion.add_argument("texto", help="guion en .txt o .md")
    p_guion.add_argument("--assets", help="carpeta con capturas/vídeos, se reparten en orden")
    p_guion.add_argument("-o", "--salida", help="fichero YAML de salida (por defecto, stdout)")
    p_guion.set_defaults(func=cmd_guion)

    p_doctor = sub.add_parser("doctor", help="comprueba ffmpeg, fuentes y motores de voz")
    p_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (guion_mod.GuionError, voz.VozError, FFmpegError, FileNotFoundError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
