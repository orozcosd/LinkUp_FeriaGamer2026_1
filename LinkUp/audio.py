"""
========================================================================
audio.py - SISTEMA DE SONIDO del juego
========================================================================
Este modulo genera TODOS los efectos de sonido del juego de forma
PROCEDURAL (matematica pura), sin necesidad de archivos .wav o .mp3
externos. Esto significa que el juego no depende de descargar audio
de internet ni de tener una carpeta de sonidos: todo se calcula al
arrancar.

Como funciona en concreto?
  1) Inicializamos pygame.mixer (la parte de pygame que reproduce audio).
  2) Para cada sonido, generamos un buffer de muestras PCM 16-bit
     usando senos matematicos (tonos puros) o arpegios (varios tonos
     seguidos).
  3) Convertimos el buffer en un pygame.mixer.Sound que podemos
     reproducir con .play().

Si pygame.mixer NO se puede inicializar (PC sin tarjeta de sonido,
o sin permisos), la clase entra en modo "no-op": los metodos no hacen
nada pero tampoco crashean. El juego sigue funcionando perfecto en
silencio.

Por que generar sonido proceduralmente?
  - Cero dependencias de archivos externos.
  - El proyecto pesa menos (no incluyes .wav).
  - Sirve como ejemplo educativo de DSP basico.
========================================================================
"""

import math
import array
import pygame


class GestorAudio:
    """Gestor centralizado de todos los efectos de sonido del juego.

    Se crea una sola instancia en Juego.__init__. Despues, en cualquier
    parte del codigo, se llama a `audio.play("nombre_sonido")` para
    reproducir el efecto deseado.

    Los nombres disponibles estan en _generar_sonidos().
    """

    def __init__(self):
        # Bandera que indica si el audio funciona. Si pygame.mixer
        # falla al inicializar, esta queda en False y todos los
        # metodos se vuelven no-ops.
        self.activo = False
        # Diccionario nombre -> pygame.mixer.Sound
        self.sonidos = {}
        try:
            # pre_init configura el mixer ANTES de pygame.mixer.init().
            # Parametros:
            #   frequency=22050 -> 22.05 kHz (suficiente para SFX)
            #   size=-16        -> 16 bits con signo (calidad CD)
            #   channels=1      -> mono (no estereo, ahorra memoria)
            #   buffer=512      -> latencia baja (~23ms a 22050 Hz)
            pygame.mixer.pre_init(frequency=22050, size=-16,
                                  channels=1, buffer=512)
            pygame.mixer.init()
            self.activo = True
            # Una vez listo el mixer, generamos todos los sonidos.
            self._generar_sonidos()
        except pygame.error:
            # Sin audio disponible: el juego funciona en silencio.
            self.activo = False

    # ------------------------------------------------------------------
    # GENERADORES DE BUFFERS DE SONIDO
    # ------------------------------------------------------------------
    def _tono(self, frec, duracion_ms, vol=0.3, decay=True):
        """Genera un tono puro (sinusoide) a una frecuencia dada.

        Parametros:
            frec        -> frecuencia en Hz (ej. 440 = nota La)
            duracion_ms -> duracion del sonido en milisegundos
            vol         -> volumen (0.0 a 1.0)
            decay       -> si True, el sonido va bajando linealmente
                           (envelope de decay) para que no termine
                           abrupto y cause clicks.

        Retorna un pygame.mixer.Sound listo para .play(), o None
        si falla la conversion.
        """
        sr = 22050  # sample rate: 22050 muestras por segundo
        n_samples = int(sr * duracion_ms / 1000)
        # array("h") es un array de enteros con signo de 16 bits.
        # Es mas eficiente que una lista de Python para audio.
        buf = array.array("h")
        # Amplitud maxima: 32767 es el valor mas alto para int16.
        amp = int(32767 * vol)
        for i in range(n_samples):
            t = i / sr   # tiempo de esta muestra (en segundos)
            env = 1.0
            if decay:
                # Decay lineal: empieza en 1, termina en 0.
                env = max(0.0, 1.0 - i / n_samples)
            # Formula clasica de onda senoidal:
            #   sample = amplitud * envelope * sin(2*pi*f*t)
            val = int(amp * env * math.sin(2 * math.pi * frec * t))
            buf.append(val)
        try:
            # tobytes() convierte el array a la representacion binaria
            # que espera pygame.mixer.Sound.
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except pygame.error:
            return None

    def _arpegio(self, freqs, dur_ms_cada, vol=0.3):
        """Genera un arpegio: varios tonos puestos uno detras del otro.

        Sirve para fanfarrias, jingles de victoria, etc. Cada nota
        de la lista `freqs` suena `dur_ms_cada` milisegundos.

        Ejemplo: _arpegio([523, 659, 784], 90, 0.3)
                 toca DO-MI-SOL en sucesion (acorde mayor).
        """
        sr = 22050
        buf = array.array("h")
        amp = int(32767 * vol)
        for f in freqs:
            n_samples = int(sr * dur_ms_cada / 1000)
            for i in range(n_samples):
                t = i / sr
                # Decay aplicado a cada nota por separado.
                env = max(0.0, 1.0 - i / n_samples)
                val = int(amp * env * math.sin(2 * math.pi * f * t))
                buf.append(val)
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except pygame.error:
            return None

    # ------------------------------------------------------------------
    # BIBLIOTECA DE SONIDOS DEL JUEGO
    # ------------------------------------------------------------------
    def _generar_sonidos(self):
        """Pre-genera todos los efectos de sonido del juego.

        Se llama una sola vez al iniciar. Despues, .play() solo
        reproduce sonidos ya cacheados (es muy rapido).

        Las frecuencias estan elegidas para sentirse "cyber":
          - Agudos cortos para clicks (660-880 Hz)
          - Arpegios mayores para victoria/exito (DO-MI-SOL-DO)
          - Arpegios menores para fallo
          - Graves para eventos negativos (140-200 Hz)
        """
        if not self.activo:
            return
        # Click suave para botones
        self.sonidos["click"]     = self._tono(660, 80, 0.25)
        # Hover muy sutil, casi imperceptible
        self.sonidos["hover"]     = self._tono(880, 40, 0.10)
        # Fanfarria de exito: arpegio mayor ascendente DO-MI-SOL-DO
        self.sonidos["exito"]     = self._arpegio([523, 659, 784, 1046], 90, 0.30)
        # Fallo: dos notas descendentes en menor
        self.sonidos["fallo"]     = self._arpegio([330, 247], 180, 0.30)
        # Jingle de nivel completado (mas largo y triunfal)
        self.sonidos["nivel"]     = self._arpegio([523, 784, 1046, 1318], 120, 0.35)
        # Evento grave (algo malo paso): zumbido grave
        self.sonidos["evento"]    = self._tono(200, 120, 0.30)
        # Click de movimiento del jugador (medio)
        self.sonidos["mover"]     = self._tono(440, 50, 0.18)
        # Sonido de "no se puede" (muy grave y corto)
        self.sonidos["bloqueado"] = self._tono(140, 120, 0.30)
        # Activacion de poder: arpegio agudo ascendente
        self.sonidos["poder"]     = self._arpegio([784, 1046, 1318], 80, 0.30)

    def play(self, nombre):
        """Reproduce el efecto de sonido con el nombre dado.

        Si el audio esta desactivado o el nombre no existe, no hace
        nada (no lanza error). Esto permite usar play() en cualquier
        parte del codigo sin tener que verificar primero si hay audio.
        """
        if not self.activo:
            return
        s = self.sonidos.get(nombre)
        if s:
            try:
                s.play()
            except pygame.error:
                # Si la tarjeta de sonido tiene un hipo, ignoramos.
                pass
