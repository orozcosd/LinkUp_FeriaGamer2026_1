"""
Configuración global del juego LinkUp.
Incluye colores (con modo daltónico), tamaños de texto y constantes.
"""

# Dimensiones de la ventana
WIDTH = 1280
HEIGHT = 720
FPS = 60

# Título
TITLE = "LinkUp - Guardianes del Nexo"

# Paletas de colores
PALETAS = {
    "normal": {
        "fondo":      (15, 20, 40),
        "fondo2":     (25, 30, 55),
        "panel":      (35, 45, 75),
        "texto":      (235, 240, 255),
        "texto_sec":  (170, 180, 210),
        "primario":   (90, 180, 255),     # azul
        "exito":      (90, 220, 140),     # verde
        "peligro":    (235, 90, 110),     # rojo
        "alerta":     (255, 190, 80),     # amarillo
        "nodo_ok":    (90, 220, 140),
        "nodo_bully": (235, 90, 110),
        "nodo_victima":(255, 190, 80),
        "nodo_neutro":(120, 140, 200),
        "nodo_central":(200, 130, 255),
        "arista":     (110, 130, 170),
        "muro":       (170, 70, 70),
        "jugador":    (255, 255, 255),
    },
    # Modo daltónico (deuteranopía/protanopía: evitar rojo-verde)
    "daltonico": {
        "fondo":      (15, 20, 40),
        "fondo2":     (25, 30, 55),
        "panel":      (35, 45, 75),
        "texto":      (235, 240, 255),
        "texto_sec":  (170, 180, 210),
        "primario":   (90, 180, 255),
        "exito":      (80, 160, 230),     # azul claro en vez de verde
        "peligro":    (255, 140, 0),      # naranja en vez de rojo
        "alerta":     (240, 230, 80),
        "nodo_ok":    (80, 160, 230),
        "nodo_bully": (255, 140, 0),
        "nodo_victima":(240, 230, 80),
        "nodo_neutro":(180, 180, 200),
        "nodo_central":(200, 130, 255),
        "arista":     (200, 200, 220),
        "muro":       (255, 140, 0),
        "jugador":    (255, 255, 255),
    },
}

# Tamaños de fuente (3 niveles para accesibilidad)
TAMANOS_FUENTE = {
    "pequeno":  {"xs": 14, "sm": 16, "md": 20, "lg": 28, "xl": 40},
    "mediano":  {"xs": 16, "sm": 20, "md": 26, "lg": 36, "xl": 52},
    "grande":   {"xs": 20, "sm": 24, "md": 32, "lg": 44, "xl": 64},
}

# Skins disponibles (representación inclusiva)
SKINS = [
    {"nombre": "Aura",    "color": (90, 200, 255),  "simbolo": "★"},
    {"nombre": "Eko",     "color": (255, 140, 100), "simbolo": "♦"},
    {"nombre": "Lyra",    "color": (200, 130, 255), "simbolo": "♣"},
    {"nombre": "Nova",    "color": (90, 230, 160),  "simbolo": "✦"},
    {"nombre": "Zen",     "color": (255, 210, 100), "simbolo": "♥"},
    {"nombre": "Onix",    "color": (180, 180, 200), "simbolo": "◆"},
]

# Configuración del juego
NUM_NODOS_MIN = 10
NUM_NODOS_MAX = 16
PROB_ARISTA = 0.25
PROB_MURO = 0.18      # probabilidad de que una arista sea muro de odio
PROB_BULLY = 0.25
PROB_VICTIMA = 0.30

# Poderes
PODERES_INICIALES = {
    "escudo_empatia": 2,   # protege a víctima
    "red_apoyo":      2,   # conecta dos nodos
    "voz_amplificada":1,   # neutraliza acosador
}

# Red
HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 50007

# Estado del juego
SALUD_COMUNIDAD_INICIAL = 100
PUNTOS_AYUDA = 15
PUNTOS_NEUTRALIZAR = 25
PUNTOS_PUENTE = 10
PENALIZACION_ERROR = -10
