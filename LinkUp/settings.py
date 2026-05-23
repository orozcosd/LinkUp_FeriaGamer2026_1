"""
Configuracion global del juego LinkUp.
"""

# Dimensiones de la ventana
WIDTH = 1280
HEIGHT = 720
FPS = 60

# Titulo
TITLE = "LinkUp - Guardianes del Nexo"

# Paletas de colores
PALETAS = {
    "normal": {
        "fondo":       (10, 14, 39),
        "fondo2":      (5, 8, 22),
        "panel":       (20, 28, 58),
        "panel_borde": (90, 200, 255),
        "texto":       (235, 240, 255),
        "texto_sec":   (140, 160, 200),
        "primario":    (0, 212, 255),
        "exito":       (6, 255, 165),
        "peligro":     (255, 67, 101),
        "alerta":      (255, 200, 80),
        "acento":      (255, 0, 110),
        "nodo_ok":     (6, 255, 165),
        "nodo_bully":  (255, 67, 101),
        "nodo_victima":(255, 200, 80),
        "nodo_neutro": (120, 160, 220),
        "nodo_central":(200, 130, 255),
        "arista":      (90, 130, 190),
        "muro":        (255, 67, 101),
        "jugador":     (255, 255, 255),
    },
    "daltonico": {
        "fondo":       (10, 14, 39),
        "fondo2":      (5, 8, 22),
        "panel":       (20, 28, 58),
        "panel_borde": (90, 200, 255),
        "texto":       (235, 240, 255),
        "texto_sec":   (170, 180, 210),
        "primario":    (90, 180, 255),
        "exito":       (80, 200, 255),
        "peligro":     (255, 140, 0),
        "alerta":      (240, 230, 80),
        "acento":      (255, 140, 0),
        "nodo_ok":     (80, 200, 255),
        "nodo_bully":  (255, 140, 0),
        "nodo_victima":(240, 230, 80),
        "nodo_neutro": (180, 180, 200),
        "nodo_central":(200, 130, 255),
        "arista":      (200, 200, 220),
        "muro":        (255, 140, 0),
        "jugador":     (255, 255, 255),
    },
}

# Fuente personalizada (con fallback a sans-serif del sistema si falta)
FUENTE_TITULOS = "assets/fonts/Orbitron-Bold.ttf"
FUENTE_TEXTO = "assets/fonts/Orbitron-Regular.ttf"

# Tamanos de fuente
TAMANOS_FUENTE = {
    "pequeno":  {"xs": 14, "sm": 16, "md": 20, "lg": 28, "xl": 40},
    "mediano":  {"xs": 16, "sm": 20, "md": 26, "lg": 36, "xl": 52},
    "grande":   {"xs": 20, "sm": 24, "md": 32, "lg": 44, "xl": 64},
}

# Skins disponibles
SKINS = [
    {"nombre": "Aura",    "color": (90, 200, 255),  "simbolo": "*"},
    {"nombre": "Eko",     "color": (255, 140, 100), "simbolo": "o"},
    {"nombre": "Lyra",    "color": (200, 130, 255), "simbolo": "+"},
    {"nombre": "Nova",    "color": (90, 230, 160),  "simbolo": "x"},
    {"nombre": "Zen",     "color": (255, 210, 100), "simbolo": "v"},
    {"nombre": "Onix",    "color": (180, 180, 200), "simbolo": "#"},
]

# Configuracion del juego
NUM_NODOS_MIN = 10
NUM_NODOS_MAX = 16
PROB_ARISTA = 0.25
PROB_MURO = 0.18
PROB_BULLY = 0.25
PROB_VICTIMA = 0.30

# Poderes
PODERES_INICIALES = {
    "escudo_empatia": 2,
    "red_apoyo":      2,
    "voz_amplificada":1,
}

# Red
HOST_DEFAULT = "0.0.0.0"
PORT_DEFAULT = 50007

# Estado del juego
SALUD_COMUNIDAD_INICIAL = 100
PUNTOS_AYUDA = 15
PUNTOS_NEUTRALIZAR = 25
PUNTOS_PUENTE = 10
PENALIZACION_ERROR = -10
