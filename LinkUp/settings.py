"""
========================================================================
settings.py - CONFIGURACION GLOBAL del juego LinkUp
========================================================================
Aqui viven TODAS las constantes que controlan el comportamiento del
juego. Si quieres cambiar el tamano de la ventana, los colores, las
probabilidades del grafo, o los puntos que da cada accion, lo haces
aqui sin tocar la logica del juego.

Por que separarlo? Porque permite que cualquier persona (incluido tu
en 6 meses) entienda y ajuste el balance del juego sin tener que
bucear en el codigo. Tambien facilita hacer un "modo dificil" o
"modo facil" cambiando solo numeros.
========================================================================
"""

# --------------------------------------------------------------------
# DIMENSIONES DE LA VENTANA
# --------------------------------------------------------------------
# Resolucion INICIAL de 1280x720 (HD): se ve bien en cualquier monitor
# moderno y es proporcion 16:9 estandar.
#
# La ventana ahora es REDIMENSIONABLE: el usuario puede arrastrar la
# esquina para agrandarla o achicarla. En tiempo de ejecucion, los
# valores WIDTH/HEIGHT se MUTAN para reflejar el tamano actual de la
# ventana (vease pygame.VIDEORESIZE en juego.py).
WIDTH = 1280
HEIGHT = 720
# Tamano MINIMO al que se puede achicar la ventana. Por debajo de esto
# la UI empieza a romperse (paneles que no caben, HUD sobre el mapa,
# etc), asi que rechazamos cambios mas chicos.
MIN_WIDTH = 900
MIN_HEIGHT = 600
# Frames por segundo objetivo. 60 es el estandar para que se sienta
# fluido sin gastar bateria de mas.
FPS = 60

# Titulo que aparece en la barra superior de la ventana del juego.
TITLE = "LinkUp - Guardianes del Nexo"


# --------------------------------------------------------------------
# PALETAS DE COLORES
# --------------------------------------------------------------------
# Definimos DOS paletas completas con las MISMAS claves:
#   - "normal":    estetica cyber-neon (azul, rojo, verde fluorescente)
#   - "daltonico": reemplaza rojo/verde por naranja/azul-claro
#                  porque rojo-verde es la combinacion mas problematica
#                  para personas con deuteranopia/protanopia (~8% de
#                  hombres en el mundo).
#
# Cada color es una tupla RGB (rojo, verde, azul) con valores 0-255.
# El juego cambia de paleta en runtime con F2 (o desde Configuracion).
PALETAS = {
    "normal": {
        "fondo":       (10, 14, 39),     # azul casi negro (fondo del juego)
        "fondo2":      (5, 8, 22),       # aun mas oscuro (parte baja del gradiente)
        "panel":       (20, 28, 58),     # azul oscuro para paneles UI
        "panel_borde": (90, 200, 255),   # cian claro para bordes
        "texto":       (235, 240, 255),  # blanco azulado para texto principal
        "texto_sec":   (140, 160, 200),  # gris azulado para texto secundario
        "primario":    (0, 212, 255),    # cian electrico (color principal)
        "exito":       (6, 255, 165),    # verde menta brillante (acciones buenas)
        "peligro":     (255, 67, 101),   # rojo coral (acciones malas, bullies)
        "alerta":      (255, 200, 80),   # amarillo dorado (advertencias)
        "acento":      (255, 0, 110),    # magenta (acentos)
        "nodo_ok":     (6, 255, 165),    # verde para nodos sanos/resueltos
        "nodo_bully":  (255, 67, 101),   # rojo para bullies
        "nodo_victima":(255, 200, 80),   # amarillo para victimas
        "nodo_neutro": (120, 160, 220),  # azul medio para neutros
        "nodo_central":(200, 130, 255),  # morado para el nodo central
        "arista":      (90, 130, 190),   # azul para las conexiones
        "muro":        (255, 67, 101),   # rojo para muros de odio
        "jugador":     (255, 255, 255),  # blanco para el avatar
    },
    "daltonico": {
        # Misma estructura, pero rojo->naranja y verde->azul-claro
        "fondo":       (10, 14, 39),
        "fondo2":      (5, 8, 22),
        "panel":       (20, 28, 58),
        "panel_borde": (90, 200, 255),
        "texto":       (235, 240, 255),
        "texto_sec":   (170, 180, 210),
        "primario":    (90, 180, 255),
        "exito":       (80, 200, 255),    # azul claro en vez de verde
        "peligro":     (255, 140, 0),     # naranja en vez de rojo
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


# --------------------------------------------------------------------
# FUENTES
# --------------------------------------------------------------------
# Press Start 2P es una fuente bitmap estilo arcade 8-bit (consolas
# de los 80s). Le da al juego una vibra retro-cyber. Si el archivo
# .ttf no existe en assets/fonts/, el juego cae a Arial automatica-
# mente (gracias a la logica de fallback en UI._cargar_fuentes).
#
# Ambas constantes apuntan al mismo archivo porque queremos que TODO
# el texto del juego tenga el mismo estilo pixelado uniforme.
FUENTE_TITULOS = "assets/fonts/PressStart2P-Regular.ttf"
FUENTE_TEXTO = "assets/fonts/PressStart2P-Regular.ttf"

# Tamanos de fuente disponibles. Press Start 2P es MUCHO mas ancha
# que una sans-serif normal (cada letra ocupa una cuadricula 8x8),
# por eso los tamanos son mas chicos que los de una fuente normal.
# Las claves xs/sm/md/lg/xl son los tamanos abreviados al estilo CSS:
# xs=extra-small, sm=small, md=medium, lg=large, xl=extra-large.
TAMANOS_FUENTE = {
    "pequeno":  {"xs": 8,  "sm": 10, "md": 12, "lg": 16, "xl": 22},
    "mediano":  {"xs": 10, "sm": 12, "md": 14, "lg": 20, "xl": 28},
    "grande":   {"xs": 12, "sm": 14, "md": 18, "lg": 24, "xl": 34},
}


# --------------------------------------------------------------------
# SKINS (apariencia del jugador)
# --------------------------------------------------------------------
# Lista de 6 personajes para elegir antes de jugar. Cada skin tiene:
#   - nombre: como se llama (sale en el HUD)
#   - color:  color de respaldo si no hay imagen PNG
#   - simbolo: caracter unico que aparece encima si no hay PNG
#
# Si existe assets/skin_<nombre>.png el juego usa esa imagen completa
# en el selector. Si existe assets/nodo_<nombre>.png la usa como
# avatar circular pequeno en el mapa. Si no existen, fallback al
# circulo de color con el simbolo encima.
SKINS = [
    {"nombre": "Aura",    "color": (90, 200, 255),  "simbolo": "*"},
    {"nombre": "Eko",     "color": (255, 140, 100), "simbolo": "o"},
    {"nombre": "Lyra",    "color": (200, 130, 255), "simbolo": "+"},
    {"nombre": "Nova",    "color": (90, 230, 160),  "simbolo": "x"},
    {"nombre": "Zen",     "color": (255, 210, 100), "simbolo": "v"},
    {"nombre": "Onix",    "color": (180, 180, 200), "simbolo": "#"},
]


# --------------------------------------------------------------------
# GENERACION DEL GRAFO (mapa del juego)
# --------------------------------------------------------------------
# El grafo se genera aleatoriamente al iniciar cada partida.
# Estos valores controlan que tan grande y denso es.
NUM_NODOS_MIN = 10        # nodos minimos (mapa pequeno)
NUM_NODOS_MAX = 16        # nodos maximos (mapa grande)
PROB_ARISTA = 0.25        # probabilidad de conectar dos nodos cualquiera
PROB_MURO = 0.18          # probabilidad de que una arista sea muro de odio
PROB_BULLY = 0.25         # probabilidad de que un nodo sea bully
PROB_VICTIMA = 0.30       # probabilidad de que un nodo sea victima
# El resto de probabilidad (1 - 0.25 - 0.30 = 0.45) se reparte
# entre aliados y neutros.


# --------------------------------------------------------------------
# PODERES INICIALES del jugador
# --------------------------------------------------------------------
# Cuantas cargas tiene cada poder al empezar la partida:
#   - escudo_empatia: protege a una victima
#   - red_apoyo: crea una conexion nueva entre dos nodos
#   - voz_amplificada: rompe un muro de odio
# Limitamos las cargas a 2/2/1 para que el jugador tenga que pensar
# cuando usarlos (no son infinitos).
PODERES_INICIALES = {
    "escudo_empatia": 2,
    "red_apoyo":      2,
    "voz_amplificada":1,
}


# --------------------------------------------------------------------
# RED (multijugador)
# --------------------------------------------------------------------
# Host por defecto. 0.0.0.0 significa "acepta conexiones de cualquier
# interfaz de red" — esto es CRITICO para que funcione el multi en
# red local (LAN). Si pusieras "127.0.0.1" solo aceptaria conexiones
# desde la misma maquina (localhost).
HOST_DEFAULT = "0.0.0.0"
# Puerto TCP donde escucha el servidor. 50007 esta libre en casi
# todas las redes (los puertos < 1024 requieren permisos especiales).
PORT_DEFAULT = 50007


# --------------------------------------------------------------------
# ECONOMIA del juego (puntos y salud)
# --------------------------------------------------------------------
# Salud inicial de la comunidad. Si llega a 0 = derrota.
SALUD_COMUNIDAD_INICIAL = 100
# Puntos por accion: ayudar a una victima vale menos que neutralizar
# a un bully porque neutralizar corta la propagacion en la raiz.
PUNTOS_AYUDA = 15
PUNTOS_NEUTRALIZAR = 25
PUNTOS_PUENTE = 10
# Penalizacion por accion equivocada (numero negativo).
PENALIZACION_ERROR = -10

# --------------------------------------------------------------------
# SALUD DE LA COMUNIDAD y SISTEMA DE PUNTUACION
# --------------------------------------------------------------------
# Salud inicial de la red social. Si llega a 0 se pierde la partida.
SALUD_COMUNIDAD_INICIAL = 100
# Puntos por accion (no usados directamente pero referenciables).
PUNTOS_AYUDA       = 15   # ayudar a una victima
PUNTOS_NEUTRALIZAR = 25   # neutralizar a un bully
PUNTOS_PUENTE      = 10   # reconectar componente aislado
PENALIZACION_ERROR = -10  # decision incorrecta
