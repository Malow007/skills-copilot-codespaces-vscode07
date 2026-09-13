# videogen

Monta vídeos de demo de software a partir de **un guion y unas capturas**. Le pasas el
texto y las imágenes; el resto (locución, movimiento de cámara, rótulos, subtítulos y
montaje) lo hace la herramienta.

Pensado para el caso concreto de enseñar un producto: **la interfaz va grabada de la app
real**, no generada. Ningún modelo de vídeo dibuja una UI legible, así que aquí las
capturas son la entrada y la IA se ocupa de la voz y del montaje.

## Qué hace

- Sintetiza la narración de cada escena y ajusta la duración del plano a lo que dura la voz.
- Da movimiento a las capturas estáticas (Ken Burns: zoom y paneo) para que no parezcan diapositivas.
- Acepta también vídeo (tu grabación de pantalla): lo recorta o lo repite hasta cubrir la narración.
- Incrusta rótulos y subtítulos, y deja además un `.srt` aparte para YouTube.
- Mezcla música de fondo opcional, con el volumen ya bajado bajo la voz.
- Cachea la voz: si solo cambias una escena, las demás no se vuelven a sintetizar.

## Qué no hace

No genera la interfaz de tu software, ni avatares, ni B-roll. Eso es un paso aparte
(ver *Extender con IA generativa* al final).

## Instalación

```bash
pip install -r videogen/requirements.txt
python3 -m videogen doctor        # comprueba ffmpeg, fuentes y motores de voz
```

`doctor` te dice exactamente qué falta. Si no tienes ffmpeg en el sistema, `imageio-ffmpeg`
trae un binario estático y la herramienta lo encuentra sola. `ffprobe` es opcional.

## Uso

```bash
# 1. (opcional) convierte un guion en texto plano a la estructura YAML
python3 -m videogen guion mi-guion.md --assets capturas/ -o guion.yaml

# 2. renderiza
python3 -m videogen render guion.yaml -o demo.mp4
```

El comando `guion` parte el texto en escenas (por títulos `#` o por párrafos), reparte
las capturas de la carpeta en orden y alterna los efectos de cámara. Es un punto de
partida: revisa el YAML y ajusta qué visual va en cada escena.

Opciones útiles de `render`:

| Opción | Para qué |
|---|---|
| `--voz kokoro\|piper\|espeak\|silencio` | fuerza el motor de voz |
| `--sin-subtitulos` | no incrusta subtítulos (el `.srt` se sigue generando) |
| `--crf 18` | más calidad, más peso (por defecto 20) |
| `--preset veryfast` | render rápido para revisar; `medium` o `slow` para la versión final |
| `--conservar-temporales` | deja los clips sueltos y los WAV para depurar |

## El guion

```yaml
proyecto: acme-demo

video:
  resolucion: 1920x1080     # 1080x1920 para vertical
  fps: 30

voz:
  backend: auto             # auto | kokoro | piper | espeak | silencio
  idioma: es
  velocidad: 1.0
  # nombre: ef_dora         # voz concreta (kokoro) o ruta al .onnx (piper)

subtitulos: true
# musica: assets/fondo.mp3

escenas:
  - titulo: El problema           # rótulo, se muestra los primeros segundos (opcional)
    narracion: El texto que se locuta y se subtitula.
    visual: assets/panel.png      # imagen o vídeo; si falta, sale una tarjeta de color
    efecto: zoom-in               # zoom-in | zoom-out | pan-derecha | pan-izquierda | estatico
    duracion_min: 6               # alarga el plano aunque la frase sea corta (opcional)
```

Una escena puede ser también una cadena suelta: se toma como la narración.

## Motores de voz

| Motor | Licencia | Notas |
|---|---|---|
| `kokoro` | Apache 2.0 | 82M, corre en CPU, buena calidad. No clona voz. `pip install kokoro soundfile` |
| `piper` | MIT | **la opción recomendada**: neuronal, offline, sin GPU, arranca en milisegundos |
| `espeak` | GPL | robótico, pero sirve para validar tiempos y montaje. `apt install espeak-ng` |
| `silencio` | — | pista muda con la duración estimada; para revisar el montaje sin instalar nada |

En modo `auto` se coge el primero disponible en ese orden.

### Instalar Piper (voz neuronal, 2 minutos)

```bash
# binario
curl -L -o piper.tgz https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz
sudo tar xzf piper.tgz -C /opt && sudo ln -sf /opt/piper/piper /usr/local/bin/piper

# voz en castellano
sudo mkdir -p /opt/piper-voices && cd /opt/piper-voices
sudo curl -L https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-es-carlfm-x-low.tar.gz | sudo tar xz
```

Y en el guion:

```yaml
voz:
  backend: piper
  nombre: /opt/piper-voices/es-carlfm-x-low.onnx
```

(o `export PIPER_VOICE=/opt/piper-voices/es-carlfm-x-low.onnx` y no tocas el guion).

Hay más voces en castellano en las
[releases de piper](https://github.com/rhasspy/piper/releases/tag/v0.0.2)
(`es-mls_10246-low`, `es-mls_9972-low`) y de mejor calidad en Hugging Face
(`es_ES-davefx-medium`, `es_ES-sharvard-medium`), si tu red llega hasta allí.

La narración se normaliza a -16 LUFS antes de mezclarla, así que todas las escenas
salen al mismo volumen aunque cambies de motor a mitad de proyecto.

## De dónde salen las capturas

- **OBS Studio** para grabar a mano.
- **Playwright** si quieres que las grabaciones se regeneren solas en cada release:
  un script que recorra los flujos clave y guarde un `.webm` por caso de uso, que entra
  aquí como `visual`.

## Extender con IA generativa

Los puntos donde encaja un modelo de vídeo, si más adelante quieres presentador o B-roll:

- **Presentador hablando**: el WAV que genera `voz.sintetizar()` es justo la entrada que
  piden SkyReels-V3-A2V o MuseTalk. El vídeo resultante se mete como `visual` de la escena.
- **B-roll del contexto real**: Wan 2.2 (Apache 2.0) o LTX generan el plano de 5 segundos
  que ilustra la situación; se guarda en `assets/` y se referencia igual que una captura.

Ninguno de los dos está integrado aquí a propósito: necesitan GPU o una API de pago, y
el pipeline funciona entero sin ellos.

## Limitaciones conocidas

- Las transiciones son cortes secos (con fundido al entrar y al salir del vídeo). No hay
  crossfade entre escenas.
- Si tu build de ffmpeg no trae `drawtext`, los rótulos se generan con Pillow como imagen
  superpuesta; si tampoco hay Pillow, se omiten y te avisa.
- Si falta `libass`, los subtítulos no se incrustan, pero el `.srt` se genera igual.
- Verificado de punta a punta con `piper`, `espeak` y `silencio`. `kokoro` sigue su API
  documentada pero no se ha podido probar (requiere descargar pesos de Hugging Face).
- Las voces `-low` de piper suenan a 16 kHz: correctas para una demo, algo planas para
  una pieza de marketing. Para eso, sube a una voz `medium` o graba tu propia locución
  y pásala como WAV.
