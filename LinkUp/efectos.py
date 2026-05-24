"""
========================================================================
efectos.py - EFECTOS VISUALES REUTILIZABLES
========================================================================
Este modulo contiene todos los "trucos visuales" del juego que pueden
usarse desde cualquier pantalla:

  - GRADIENTES: fondos con degradado vertical (cyber-neon look)
  - GLOW: halos de varias capas alrededor de elementos (efecto neon)
  - PARTICULAS: explosiones de puntitos animados (cuando algo pasa)
  - TRANSICIONES: fundidos a negro entre pantallas
  - UTILIDADES: pulsos seno, interpolacion de colores, aclarar colores

Disenado para encajar con la estetica cyber-neon de LinkUp.
Todo esta optimizado: los gradientes se cachean, las particulas usan
__slots__ para reducir memoria, las superficies con alpha se crean
solo cuando hace falta.
========================================================================
"""

import math
import random
import time

import pygame


# ---------------------------------------------------------------------------
# GRADIENTES
# ---------------------------------------------------------------------------
def dibujar_gradiente_vertical(superficie, color_top, color_bot):
    """Pinta un degradado vertical desde color_top arriba a color_bot abajo.

    Algoritmo: para cada linea horizontal de pixels (y de 0 a H-1),
    calculamos un valor t entre 0 y 1, y interpolamos los canales RGB
    entre color_top y color_bot. Luego dibujamos una linea horizontal
    de ese color.

    Es lineal y no usa pygame.gfxdraw para mantener compatibilidad
    maxima. Es lento si lo haces cada frame, por eso usamos la version
    cacheada (abajo) en el juego.
    """
    w, h = superficie.get_size()
    for y in range(h):
        # t va de 0 (arriba) a 1 (abajo). max(1, h-1) evita division /0.
        t = y / max(1, h - 1)
        # Interpolacion lineal de cada canal RGB.
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        pygame.draw.line(superficie, (r, g, b), (0, y), (w, y))


def crear_gradiente_cacheado(w, h, color_top, color_bot):
    """Crea (y devuelve) una superficie con el gradiente pre-renderizado.

    Llamala UNA VEZ al iniciar el juego (o al cambiar de paleta) y
    luego haz blit de la superficie devuelta cada frame. Asi pagas
    el costo del gradiente solo una vez.

    Es la diferencia entre 720 lineas dibujadas por frame y 1 sola
    operacion de blit.
    """
    # convert() optimiza la Surface para coincidir con el formato
    # de pixel del display, lo que acelera mucho el blitting.
    surf = pygame.Surface((w, h)).convert()
    dibujar_gradiente_vertical(surf, color_top, color_bot)
    return surf


# ---------------------------------------------------------------------------
# GLOW (resplandor neon)
# ---------------------------------------------------------------------------
def dibujar_glow(superficie, cx, cy, radio, color, capas=4, alpha_base=60):
    """Dibuja un halo de varias capas semitransparentes alrededor de (cx, cy).

    Da sensacion de neon. Usar ANTES de dibujar el nodo real encima.

    Como funciona:
      Dibujamos varios circulos concentricos cada vez mas grandes
      y cada vez mas transparentes. La combinacion de muchas capas
      semitransparentes con BLEND_RGBA_ADD (suma de colores) produce
      el efecto luminoso caracteristico de un letrero de neon.

    Parametros:
        capas      -> cuantas capas dibujar (mas = mas brillante y suave)
        alpha_base -> opacidad de la capa mas interna (0-255)
    """
    for i in range(capas, 0, -1):
        # Cada capa es mas grande que la anterior.
        r = radio + i * 6
        # Y mas transparente (las externas casi no se notan, lo que
        # crea el degradado suave hacia afuera).
        alpha = max(8, alpha_base - i * 12)
        # SRCALPHA: superficie con canal alpha, necesario para
        # transparencia real.
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (r, r), r)
        # BLEND_RGBA_ADD: suma los colores en vez de mezclarlos.
        # Es lo que da el efecto "fluorescente" tipico del cyberpunk.
        superficie.blit(s, (cx - r, cy - r), special_flags=pygame.BLEND_RGBA_ADD)


# ---------------------------------------------------------------------------
# PARTICULAS
# ---------------------------------------------------------------------------
class Particula:
    """Una particula individual: punto que se mueve, decae, y desaparece.

    Usamos __slots__ para AHORRAR MEMORIA. Sin __slots__, cada
    instancia tendria su propio __dict__ (consume ~300 bytes).
    Con __slots__, solo los atributos listados existen y consumen
    ~50 bytes. Con 400 particulas activas, la diferencia importa.
    """
    __slots__ = ("x", "y", "vx", "vy", "vida", "vida_max", "color", "tam")

    def __init__(self, x, y, vx, vy, vida, color, tam=3):
        self.x = x          # posicion actual X
        self.y = y          # posicion actual Y
        self.vx = vx        # velocidad X (pixels/segundo)
        self.vy = vy        # velocidad Y
        self.vida = vida    # tiempo restante (segundos)
        self.vida_max = vida  # vida original (para calcular fade)
        self.color = color  # tupla RGB
        self.tam = tam      # tamano del circulo

    def update(self, dt):
        """Avanza la particula un frame. Devuelve True si sigue viva."""
        # Movimiento basico: pos += velocidad * delta_tiempo.
        self.x += self.vx * dt
        self.y += self.vy * dt
        # Gravedad sutil hacia abajo (30 pixels/segundo^2). Hace que
        # las particulas "caigan" naturalmente despues del impulso.
        self.vy += 30 * dt
        # Friccion horizontal: la velocidad X decae al 98% cada frame.
        # Esto hace que las particulas se "frenen" suavemente.
        self.vx *= 0.98
        self.vida -= dt
        # True si todavia esta viva, False para que el gestor la borre.
        return self.vida > 0

    def dibujar(self, superficie):
        """Pinta la particula en la superficie con fade segun su vida."""
        if self.vida <= 0:
            return
        # t va de 1 (recien nacida) a 0 (muerta). Lo usamos para el
        # fade y el cambio de tamano.
        t = max(0.0, min(1.0, self.vida / self.vida_max))
        alpha = int(255 * t)
        # El tamano tambien decae un poco (de 100% a 60%).
        tam = max(1, int(self.tam * (0.6 + 0.4 * t)))
        s = pygame.Surface((tam * 2, tam * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (tam, tam), tam)
        # BLEND_RGBA_ADD para que las particulas se "sumen" cuando se
        # superponen, dando efecto luminoso.
        superficie.blit(s, (int(self.x - tam), int(self.y - tam)),
                        special_flags=pygame.BLEND_RGBA_ADD)


class GestorParticulas:
    """Mantiene una lista global de particulas activas.

    Patron: una sola instancia compartida en Juego. Cualquier parte
    del codigo puede pedirle que cree particulas (burst, chispa), y
    el gestor se encarga de actualizar y dibujar a todas cada frame.
    """

    # Tope de seguridad: si pasamos este numero descartamos la mitad
    # mas vieja para que no se desmadre el rendimiento.
    MAX_PARTICULAS = 400

    def __init__(self):
        self.particulas = []

    def burst(self, x, y, color, cantidad=18, velocidad=120, vida=0.9, tam=3):
        """Explosion radial de particulas en (x, y).

        Usada para eventos importantes: infeccion (rojas), curacion
        (verdes), uso de poder. Lanza N particulas en angulos
        aleatorios alrededor del centro.
        """
        # Si nos pasamos del tope, descartamos las mas viejas.
        if len(self.particulas) > self.MAX_PARTICULAS:
            self.particulas = self.particulas[-self.MAX_PARTICULAS // 2:]
        for _ in range(cantidad):
            # Angulo aleatorio en circulo completo (0 a 2*pi).
            ang = random.uniform(0, math.tau)
            # Velocidad variable (40% a 100% del maximo) para que
            # las particulas no se vean uniformes.
            vel = velocidad * random.uniform(0.4, 1.0)
            self.particulas.append(Particula(
                x, y,
                math.cos(ang) * vel,
                # Restamos un poco a vy para que tengan impulso INICIAL
                # hacia arriba (la gravedad luego las baja).
                math.sin(ang) * vel - random.uniform(20, 60),
                vida * random.uniform(0.7, 1.1),
                color,
                tam=tam,
            ))

    def chispa(self, x, y, color, cantidad=5):
        """Chispitas pequenas hacia arriba (gestos sutiles, hover de botones).

        Diferencia con burst: angulo restringido al hemisferio superior
        (-pi a 0), velocidad menor, menos particulas. Subtil.
        """
        for _ in range(cantidad):
            ang = random.uniform(-math.pi, 0)  # solo hacia arriba
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
        """Avanza todas las particulas y borra las muertas.

        Usamos list comprehension porque es la forma mas rapida en
        Python de filtrar + transformar una lista.
        """
        self.particulas = [p for p in self.particulas if p.update(dt)]

    def dibujar(self, superficie):
        """Pinta todas las particulas activas."""
        for p in self.particulas:
            p.dibujar(superficie)


# ---------------------------------------------------------------------------
# TRANSICION FADE ENTRE PANTALLAS
# ---------------------------------------------------------------------------
class Transicion:
    """Maneja un fade-out -> fade-in cuando cambias de pantalla.

    Es una pequena maquina de estados con tres fases:
      - idle: no esta pasando nada, alpha = 0
      - out:  oscureciendo (alpha sube de 0 a 255)
      - in:   aclarando   (alpha baja de 255 a 0)

    Uso tipico:
        self.transicion.iniciar("mapa")   # arranca fade-out
        # cuando el fade-out termina, transicion.aplicar() llama
        # callback y empieza el fade-in.

    El truco esta en el callback: cuando termina el fade-out,
    ejecutamos el cambio de pantalla en ese momento exacto. El
    usuario ve la pantalla a negro un instante y luego aparece la
    nueva pantalla aclarandose. Esto disimula los cambios bruscos.
    """

    # Duracion de CADA fase (out e in), en segundos. Total = 2 * 0.28s.
    # Si lo subes, el fade es mas lento y "cinematografico".
    DURACION = 0.28

    def __init__(self):
        self.alpha = 0           # 0 transparente, 255 negro
        self.fase = "idle"       # idle | out | in
        self.t = 0.0             # tiempo acumulado en la fase actual
        self.destino = None      # a que pantalla vamos
        self._callback = None    # que ejecutar al terminar el fade-out

    def iniciar(self, destino, callback=None):
        """Arranca un fade-out + cambio + fade-in.

        Si ya hay una transicion en curso, no hace nada (evita
        encolar transiciones sin querer).
        """
        if self.fase != "idle":
            return
        self.fase = "out"
        self.t = 0.0
        self.destino = destino
        self._callback = callback

    def fade_in(self):
        """Fade visual de negro a transparente.

        No requiere callback ni cambio de pantalla — util al entrar
        a una pantalla recien creada para que aparezca con suavidad
        (por ejemplo cuando arranca una partida nueva).
        """
        self.fase = "in"
        self.t = 0.0
        self.alpha = 255
        self.destino = None
        self._callback = None

    def update(self, dt):
        """Avanza la transicion. Devuelve el destino si se completo
        el cambio (para que el juego sepa que ya cambio de pantalla),
        None en otros casos."""
        if self.fase == "idle":
            return None
        self.t += dt
        # Ratio: 0 (recien empezo) a 1 (termino).
        ratio = min(1.0, self.t / self.DURACION)
        if self.fase == "out":
            # alpha sube de 0 a 255 (cada vez mas negro).
            self.alpha = int(255 * ratio)
            if ratio >= 1.0:
                # Fin del fade-out: aqui ejecutamos el cambio.
                destino = self.destino
                cb = self._callback
                # Pasamos a fade-in inmediatamente.
                self.fase = "in"
                self.t = 0.0
                if cb:
                    cb(destino)
                return destino
        elif self.fase == "in":
            # alpha baja de 255 a 0 (revelando la nueva pantalla).
            self.alpha = int(255 * (1.0 - ratio))
            if ratio >= 1.0:
                self.alpha = 0
                self.fase = "idle"
                self.destino = None
        return None

    def dibujar(self, superficie):
        """Pinta el rectangulo negro semi-transparente que cubre todo.

        Se llama AL FINAL del frame, despues de todo lo demas, asi
        el fade siempre queda encima.
        """
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
    """Valor oscilante senoidal en torno a 0.

    Util para hacer "latir" cosas: nodos que palpitan, botones que
    respiran. Combinas el resultado con un valor base:
        radio = radio_base + pulso(velocidad=2, amplitud=3)

    velocidad -> cuantos ciclos por segundo (aprox)
    amplitud  -> que tan grande es la oscilacion
    """
    # time.time() es el reloj global del sistema; lo usamos para que
    # el pulso sea consistente entre frames sin acumular un contador.
    return math.sin(time.time() * velocidad) * amplitud


def lerp_color(c1, c2, t):
    """Interpola dos colores RGB. t entre 0 y 1.

    t=0 -> c1, t=1 -> c2, t=0.5 -> color intermedio.
    Util para crear transiciones de color suaves.
    """
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def aclarar(color, factor=1.2):
    """Devuelve un color mas claro (para efectos de hover).

    Multiplica cada canal RGB por el factor, sin pasarse de 255.
    factor=1.2 -> 20% mas claro.
    """
    return tuple(min(255, int(c * factor)) for c in color[:3])
