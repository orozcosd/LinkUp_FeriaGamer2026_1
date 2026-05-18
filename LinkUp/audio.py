"""
Audio del juego: genera efectos de sonido proceduralmente (no requiere
archivos externos). Si pygame.mixer no se puede inicializar, las
funciones se vuelven no-ops para mantener el juego funcionando.
"""

import math
import array
import pygame


class GestorAudio:
    def __init__(self):
        self.activo = False
        self.sonidos = {}
        try:
            pygame.mixer.pre_init(frequency=22050, size=-16,
                                  channels=1, buffer=512)
            pygame.mixer.init()
            self.activo = True
            self._generar_sonidos()
        except pygame.error:
            self.activo = False

    # -----------------------------------------------------------------
    def _tono(self, frec, duracion_ms, vol=0.3, decay=True):
        """Genera un Sound desde un buffer PCM 16-bit mono."""
        sr = 22050
        n_samples = int(sr * duracion_ms / 1000)
        buf = array.array("h")
        amp = int(32767 * vol)
        for i in range(n_samples):
            t = i / sr
            env = 1.0
            if decay:
                env = max(0.0, 1.0 - i / n_samples)
            val = int(amp * env * math.sin(2 * math.pi * frec * t))
            buf.append(val)
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except pygame.error:
            return None

    def _arpegio(self, freqs, dur_ms_cada, vol=0.3):
        sr = 22050
        buf = array.array("h")
        amp = int(32767 * vol)
        for f in freqs:
            n_samples = int(sr * dur_ms_cada / 1000)
            for i in range(n_samples):
                t = i / sr
                env = max(0.0, 1.0 - i / n_samples)
                val = int(amp * env * math.sin(2 * math.pi * f * t))
                buf.append(val)
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except pygame.error:
            return None

    def _generar_sonidos(self):
        if not self.activo:
            return
        self.sonidos["click"]     = self._tono(660, 80, 0.25)
        self.sonidos["hover"]     = self._tono(880, 40, 0.10)
        self.sonidos["exito"]     = self._arpegio([523, 659, 784, 1046], 90, 0.30)
        self.sonidos["fallo"]     = self._arpegio([330, 247], 180, 0.30)
        self.sonidos["nivel"]     = self._arpegio([523, 784, 1046, 1318], 120, 0.35)
        self.sonidos["evento"]    = self._tono(200, 120, 0.30)
        self.sonidos["mover"]     = self._tono(440, 50, 0.18)
        self.sonidos["bloqueado"] = self._tono(140, 120, 0.30)
        self.sonidos["poder"]     = self._arpegio([784, 1046, 1318], 80, 0.30)

    def play(self, nombre):
        if not self.activo:
            return
        s = self.sonidos.get(nombre)
        if s:
            try:
                s.play()
            except pygame.error:
                pass
