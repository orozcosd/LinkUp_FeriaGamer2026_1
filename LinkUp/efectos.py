"""
Efectos visuales reutilizables: gradientes, partículas, glow y transiciones.
Diseñados para encajar con la estética cyber-neon de LinkUp.
"""

import math
import random
import time

import pygame


# ---------------------------------------------------------------------------
# GRADIENTES
# ---------------------------------------------------------------------------
def dibujar_gradiente_vertical(superficie, color_top, color_bot):
    """Pinta un degradado vertical desde color_top arriba a color_bot abajo."""
    w, h = superficie.get_size()
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        pygame.draw.line(superficie, (r, g, b), (0, y), (w, y))


def crear_gradiente_cacheado(w, h, color_top, color_bot):
    """Crea (y devuelve) una superficie con el gradiente pre-renderizado.
    Mucho más rápido que recalcular cada frame."""
    surf = pygame.Surface((w, h)).convert()
    dibujar_gradiente_vertical(surf, color_top, color_bot)
    return surf


# ---------------------------------------------------------------------------
# GLOW (resplandor)
# ---------------------------------------------------------------------------
def dibujar_glow(superficie, cx, cy, radio, color, capas=4, alpha_base=60):
    """Dibuja un halo de varias capas semitransparentes alrededor de (cx, cy).
    Da sensación de neón. Usar ANTES de dibujar el nodo real encima."""
    for i in range(capas, 0, -1):
        r = radio + i * 6
        alpha = max(8, alpha_base - i * 12)
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (r, r), r)
        superficie.blit(s, (cx - r, cy - r), special_flags=pygame.BLEND_RGBA_ADD)


# ---------------------------------------------------------------------------
# PARTÍCULAS
# ---------------------------------------------------------------------------
class Particula:
    __slots__ = ("x", "y", "vx", "vy", "vida", "vida_max", "color", "tam")

    def __init__(self, x, y, vx, vy, vida, color, tam=3):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.vida = vida
        self.vida_max = vida
        self.color = color
        self.tam = tam

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        # leve gravedad / desaceleración
        self.vy += 30 * dt
        self.vx *= 0.98
        self.vida -= dt
        return self.vida > 0

    def dibujar(self, superficie):
        if self.vida <= 0:
            return
        t = max(0.0, min(1.0, self.vida / self.vida_max))
        alpha = int(255 * t)
        tam = max(1, int(self.tam * (0.6 + 0.4 * t)))
        s = pygame.Surface((tam * 2, tam * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (tam, tam), tam)
        superficie.blit(s, (int(self.x - tam), int(self.y - tam)),
                        special_flags=pygame.BLEND_RGBA_ADD)


class GestorParticulas:
    """Mantiene una lista global de partículas activas."""

    MAX_PARTICULAS = 400  # tope para que no se desmadre

    def __init__(self):
        self.particulas = []

    def burst(self, x, y, color, cantidad=18, velocidad=120, vida=0.9, tam=3):
        """Explosión de partículas en (x, y) — para infección o curación."""
        if len(self.particulas) > self.MAX_PARTICULAS:
            self.particulas = self.particulas[-self.MAX_PARTICULAS // 2:]
        for _ in range(cantidad):
            ang = random.uniform(0, math.tau)
            vel = velocidad * random.uniform(0.4, 1.0)
            self.particulas.append(Particula(
                x, y,
                math.cos(ang) * vel,
                math.sin(ang) * vel - random.uniform(20, 60),  # leve impulso arriba
                vida * random.uniform(0.7, 1.1),
                color,
                tam=tam,
            ))

    def chispa(self, x, y, color, cantidad=5):
        """Chispitas pequeñas (para hover de botones u otros gestos sutiles)."""
        for _ in range(cantidad):
            ang = random.uniform(-math.pi, 0)  # hacia arriba
            vel = random.uniform(40, 90)
            self.particulas.append(Particula(
                x + random.uniform(-6, 6), y,
                math.cos(ang) * vel,
                math.sin(ang) * vel,
                random.uniform(0.4, 0.8),
                color,
                tam=2,
            ))

    def update(self, dt):
        self.particulas = [p for p in self.particulas if p.update(dt)]

    def dibujar(self, superficie):
        for p in self.particulas:
            p.dibujar(superficie)


# ---------------------------------------------------------------------------
# TRANSICIÓN FADE ENTRE PANTALLAS
# ---------------------------------------------------------------------------
class Transicion:
    """Maneja un fade-out → fade-in cuando cambias de pantalla.

    Uso típico:
        self.transicion.iniciar("mapa")   # arranca fade-out
        # cuando el fade-out termina, transicion.aplicar() llama callback
        # y empieza el fade-in.
    """

    DURACION = 0.28  # segundos por cada lado (out + in)

    def __init__(self):
        self.alpha = 0       # 0 transparente, 255 negro
        self.fase = "idle"   # idle | out | in
        self.t = 0.0
        self.destino = None
        self._callback = None

    def iniciar(self, destino, callback=None):
        if self.fase != "idle":
            return
        self.fase = "out"
        self.t = 0.0
        self.destino = destino
        self._callback = callback

    def fade_in(self):
        """Fade visual de negro a transparente. No requiere callback ni
        cambio de pantalla — útil al entrar a una pantalla recién creada."""
        self.fase = "in"
        self.t = 0.0
        self.alpha = 255
        self.destino = None
        self._callback = None

    def update(self, dt):
        if self.fase == "idle":
            return None
        self.t += dt
        ratio = min(1.0, self.t / self.DURACION)
        if self.fase == "out":
            self.alpha = int(255 * ratio)
            if ratio >= 1.0:
                # Disparar el cambio de pantalla
                destino = self.destino
                cb = self._callback
                self.fase = "in"
                self.t = 0.0
                if cb:
                    cb(destino)
                return destino
        elif self.fase == "in":
            self.alpha = int(255 * (1.0 - ratio))
            if ratio >= 1.0:
                self.alpha = 0
                self.fase = "idle"
                self.destino = None
        return None

    def dibujar(self, superficie):
        if self.fase == "idle" or self.alpha <= 0:
            return
        w, h = superficie.get_size()
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((0, 0, 0, self.alpha))
        superficie.blit(s, (0, 0))


# ---------------------------------------------------------------------------
# UTILIDADES VARIAS
# ---------------------------------------------------------------------------
def pulso(velocidad=2.0, amplitud=3.0):
    """Valor oscilante senoidal en torno a 0 — útil para hacer 'latir' nodos."""
    return math.sin(time.time() * velocidad) * amplitud


def lerp_color(c1, c2, t):
    """Interpola dos colores RGB. t entre 0 y 1."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def aclarar(color, factor=1.2):
    """Devuelve color más claro (para hover)."""
    return tuple(min(255, int(c * factor)) for c in color[:3])
