"""
========================================================================
juego.py - CEREBRO DEL JUEGO LinkUp - Guardianes del Nexo
========================================================================
Este es el archivo MAS GRANDE y mas importante del proyecto. Contiene
toda la logica que conecta los demas modulos y dibuja las pantallas
con pygame.

Tiene TRES clases principales:

  1) UI:        helpers de interfaz (botones, paneles, texto, fuentes).
                Es la "capa de presentacion" reutilizable.

  2) EstadoJuego: contiene el estado actual de la partida (grafo,
                jugadores, salud, cola de eventos, etc.). Es un objeto
                contenedor sin metodos importantes — pura data.

  3) Juego:    el orquestador principal. Tiene el LOOP del juego (60 FPS),
                la maquina de estados de pantallas (menu -> mapa -> evento
                -> fin), los handlers de input, y las llamadas a red,
                audio, particulas, etc.

ARQUITECTURA DE PANTALLAS (state machine):
    menu  ->  config / lobby_host / lobby_cliente / ayuda
                                  |
                                  v
                                mapa  <-->  evento (decisiones)
                                  |
                                  +-->  pausa
                                  |
                                  +-->  fin

EL LOOP PRINCIPAL (correr()):
    cada frame:
      1) obtener eventos (mouse, teclado, cerrar ventana)
      2) procesar segun la pantalla activa
      3) actualizar particulas y transiciones
      4) pygame.display.flip()  (muestra todo)
========================================================================
"""

import math
import os
import random
import sys
import time

import pygame

# Numpy es opcional: si esta instalado, podemos aplicar el filtro
# daltonico global (post-procesamiento que tiñe toda la pantalla,
# incluyendo imagenes, para mantener la paleta accesible coherente).
# Si no esta instalado, el modo daltonico solo cambia la paleta de UI.
try:
    import numpy as _np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

import settings
from estructuras import Grafo, ArbolDecisiones, ColaPrioridad, Nodo
from situaciones import crear_situacion, nombre_aleatorio
from audio import GestorAudio
from red import Servidor, Cliente, descubrir_ip_local
from recursos import Recursos
from efectos import (
    crear_gradiente_cacheado,
    dibujar_glow,
    GestorParticulas,
    Transicion,
    pulso,
    aclarar,
)


# Directorio base del proyecto (carpeta donde esta este archivo).
# Lo usamos para construir rutas absolutas a fuentes/assets de forma
# robusta sin importar desde donde se lance python.
_DIR_BASE = os.path.dirname(os.path.abspath(__file__))


# ===========================================================================
# MATRIZ DE FILTRO DALTONICO (post-procesamiento)
# ===========================================================================
# Esta matriz se aplica pixel-por-pixel sobre toda la pantalla cuando el
# modo daltonico esta activo. Transforma los colores asi:
#   - El rojo (255,0,0) se vuelve naranja (sube canal verde junto al rojo)
#   - El verde (0,255,0) se vuelve cyan-azulado (sube canal azul junto al verde)
#   - El azul (0,0,255) se mantiene
# Resultado: rojo y verde dejan de confundirse para personas con
# deuteranopia/protanopia, y el efecto se aplica TAMBIEN a imagenes
# (no solo a colores programaticos de la paleta).
#
# La matriz se multiplica por cada vector (R, G, B) del frame final
# antes de mostrarlo en pantalla. Se usa numpy para eficiencia
# (matmul vectorizado sobre ~1M pixeles en pocos milisegundos).
_MATRIZ_DALTONIZE = (
    _np.array([
        [1.00, 0.00, 0.00],   # R' = 1.0 * R         (rojo se mantiene)
        [0.50, 0.70, 0.00],   # G' = 0.5R + 0.7G     (rojo + verde -> naranja)
        [0.00, 0.40, 1.00],   # B' = 0.4G + 1.0B     (verde + azul -> cyan)
    ], dtype=_np.float32)
    if _NUMPY_OK else None
)


# ===========================================================================
# SERIALIZACION DE ARBOLES DE DECISIONES PARA MULTIJUGADOR
# ===========================================================================
# Los clientes necesitan ver los mismos arboles de decisiones que el
# servidor. Sin esto, el invitado nunca veria opciones para salvar
# nodos (el bug que el usuario reporto). El servidor crea los arboles
# localmente con crear_situacion(), los serializa como dicts JSON, y
# los envia dentro del snapshot de ESTADO en cada difusion.
#
# El cliente deserializa de vuelta a NodoArbol/ArbolDecisiones cuando
# recibe el estado. Asi puede abrir su propia pantalla de evento,
# navegar el arbol localmente, y enviar la decision final como una
# accion "decidir" al servidor con la ruta de indices tomados.
#
# Los arboles son inmutables (no cambian durante la partida — solo
# cambia el cursor `arbol.actual` mientras navegas), asi que enviarlos
# en cada snapshot es redundante pero simple. JSON+LAN es barato
# (~30KB por snapshot, irrelevante en red local).
from estructuras import NodoArbol, ArbolDecisiones


def _serializar_nodo_arbol(nodo):
    """NodoArbol -> dict JSON-serializable.

    Recursivo: cada hijo en `opciones` se serializa tambien. Las hojas
    (sin opciones) terminan la recursion porque `nodo.opciones == []`.
    """
    return {
        "texto": nodo.texto,
        "terminal": nodo.terminal,
        "tipo_resultado": nodo.tipo_resultado,
        "efecto": nodo.efecto,
        "opciones": [
            [texto_op, _serializar_nodo_arbol(hijo), efecto]
            for texto_op, hijo, efecto in nodo.opciones
        ],
    }


def _deserializar_nodo_arbol(d):
    """dict -> NodoArbol. Inverso de _serializar_nodo_arbol."""
    n = NodoArbol(
        d["texto"],
        terminal=d.get("terminal", False),
        tipo_resultado=d.get("tipo_resultado", "neutro"),
        efecto=d.get("efecto", {}),
    )
    # Reconstruimos las opciones recursivamente.
    n.opciones = [
        (op[0], _deserializar_nodo_arbol(op[1]), op[2])
        for op in d.get("opciones", [])
    ]
    return n


def _serializar_situaciones(situaciones):
    """dict {nodo_id: ArbolDecisiones} -> dict serializable.

    Las claves del dict resultante son strings (JSON requiere claves
    string), las convertimos de vuelta a int al deserializar.
    """
    return {
        str(nid): _serializar_nodo_arbol(arbol.raiz)
        for nid, arbol in situaciones.items()
    }


def _deserializar_situaciones(d):
    """dict serializable -> dict {nodo_id: ArbolDecisiones}."""
    return {
        int(nid): ArbolDecisiones(_deserializar_nodo_arbol(arbol_d))
        for nid, arbol_d in d.items()
    }


# ===========================================================================
# CLASE UI - Helpers de interfaz (botones, paneles, texto)
# ===========================================================================
class UI:
    """Capa de helpers para dibujar elementos de UI consistentes.

    Centraliza la logica de:
      - Cargar fuentes (con fallback a Arial si Press Start 2P falta)
      - Acceder a la paleta de colores actual
      - Renderizar texto (con multi-linea, anchor, sombra)
      - Dibujar paneles glassmorphism
      - Dibujar botones con hover, sombra, glow, y soporte de imagenes

    Una sola instancia se crea en Juego.__init__ y se usa desde todas
    las pantallas.
    """

    def __init__(self, screen, paleta_clave="normal", tam_fuente="mediano",
                 recursos=None):
        # Surface principal donde dibujamos todo.
        self.screen = screen
        # Clave de la paleta a usar ("normal" o "daltonico").
        self.paleta_clave = paleta_clave
        # Clave del tamano de fuente ("pequeno", "mediano", "grande").
        self.tam_fuente = tam_fuente
        # Recursos (opcional): si se pasa, los botones pueden usar imagenes.
        self.recursos = recursos
        # Cargamos las fuentes al inicializar.
        self._cargar_fuentes()

    def _cargar_fuentes(self):
        """Carga las 5 fuentes (xs/sm/md/lg/xl) con fallback a Arial.

        Si el archivo Press Start 2P existe en assets/fonts/, lo usamos.
        Si no, caemos a Arial del sistema. Esto hace que el juego
        funcione sin tener que descargar nada.

        Los tamanos grandes (lg, xl) se consideran "titulos"; los
        pequenos (xs, sm, md) son "texto". Ambos apuntan a la misma
        fuente en nuestra configuracion actual, pero podrian ser
        distintos en el futuro.
        """
        tam = settings.TAMANOS_FUENTE[self.tam_fuente]
        ruta_titulo = os.path.join(_DIR_BASE, settings.FUENTE_TITULOS)
        ruta_texto = os.path.join(_DIR_BASE, settings.FUENTE_TEXTO)
        # Solo intentamos usar el TTF si el archivo existe en disco.
        usar_ttf_titulo = os.path.isfile(ruta_titulo)
        usar_ttf_texto = os.path.isfile(ruta_texto)

        def _fuente(size_key, valor):
            # Closure: crea una fuente de un tamano dado segun si es
            # "titulo" o no, con fallback a Arial.
            es_titulo = size_key in ("lg", "xl")
            try:
                if es_titulo and usar_ttf_titulo:
                    return pygame.font.Font(ruta_titulo, valor)
                if (not es_titulo) and usar_ttf_texto:
                    return pygame.font.Font(ruta_texto, valor)
            except (pygame.error, OSError):
                # Falla al abrir la fuente: ignoramos y caemos a Arial.
                pass
            # Fallback: fuente del sistema (Arial siempre esta en Windows).
            return pygame.font.SysFont("arial", valor, bold=es_titulo)

        # Diccionario clave (xs/sm/md/lg/xl) -> objeto pygame.Font.
        self.fuentes = {k: _fuente(k, v) for k, v in tam.items()}

    @property
    def col(self):
        """Atajo: devuelve el dict de colores de la paleta actual.
        En vez de escribir settings.PALETAS[self.paleta_clave] cada vez."""
        return settings.PALETAS[self.paleta_clave]

    def cambiar_paleta(self, clave):
        """Cambia la paleta (normal/daltonico)."""
        self.paleta_clave = clave

    def cambiar_tam_fuente(self, tam):
        """Cambia el tamano de fuente y recarga las fuentes."""
        self.tam_fuente = tam
        self._cargar_fuentes()

    def texto(self, txt, size, color=None, x=0, y=0, centrado=False, anchor=None,
              sombra=False):
        """Renderiza texto en (x, y) con la fuente del tamano dado.

        Soporta:
          - Texto multi-linea (separado por \n)
          - Color custom o el "texto" de la paleta por defecto
          - Anchor "topright" (alinea esquina sup-derecha en x,y)
          - Centrado horizontal en x
          - Sombra negra a 2px de offset para legibilidad sobre fondos
        """
        if color is None:
            color = self.col["texto"]
        fuente = self.fuentes[size]
        # Procesamos linea por linea para soportar \n.
        lineas = str(txt).split("\n")
        y_act = y
        for ln in lineas:
            # render() crea una Surface con el texto pintado.
            # True = antialiasing activado (mas suave).
            r = fuente.render(ln, True, color)
            # Calculamos el rect destino segun el modo de alineacion.
            if anchor == "topright":
                rect = r.get_rect(topright=(x, y_act))
            elif centrado:
                rect = r.get_rect(center=(x, y_act + r.get_height() // 2))
            else:
                rect = r.get_rect(topleft=(x, y_act))
            # Sombra: pintamos el mismo texto en negro 2px desplazado
            # antes del texto real. Da efecto de relieve y mejora la
            # legibilidad sobre fondos brillantes.
            if sombra:
                shadow = fuente.render(ln, True, (0, 0, 0))
                self.screen.blit(shadow, rect.move(2, 2))
            self.screen.blit(r, rect)
            # Avanzamos Y para la siguiente linea.
            y_act += r.get_height()

    def panel(self, rect, color=None, borde=None, radio=14, alpha=None):
        """Panel glassmorphism: fondo semitransparente + borde fino cian.

        Es el estilo "vidrio escarchado" tipico del cyberpunk: se ve
        translucido, con esquinas redondeadas y borde luminoso.

        Parametros:
            rect   -> pygame.Rect con posicion y tamano
            color  -> color de fondo (defecto: panel de la paleta)
            borde  -> color del borde (defecto: panel_borde de la paleta)
            radio  -> radio de las esquinas redondeadas
            alpha  -> opacidad 0-255 (defecto 180 = bastante transparente)
        """
        c = self.col
        if color is None:
            color = c["panel"]
        # Fondo translucido en una Surface separada (necesitamos
        # SRCALPHA para que el alpha del rect funcione).
        alpha_final = alpha if alpha is not None else 180
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (*color, alpha_final), surf.get_rect(),
                         border_radius=radio)
        self.screen.blit(surf, rect.topleft)
        # Borde solido (no usa alpha porque queremos que destaque).
        color_borde = borde if borde is not None else c.get("panel_borde", c["primario"])
        pygame.draw.rect(self.screen, color_borde, rect, 1, border_radius=radio)

    def boton(self, rect, etiqueta, hover=False, activo=False,
              color_bg=None, color_txt=None, clave_imagen=None,
              dibujar_texto=None):
        """Boton con hover (elevacion, glow y sombra).

        Sistema en CASCADA para el fondo del boton:
          1) Si clave_imagen+"_hover" existe Y estamos en hover -> usar esa
          2) Si clave_imagen existe -> usar esa
          3) Si "boton_hover/activo/normal" existe -> usar esa (genericos)
          4) Sino -> fallback glassmorphism (panel semi-transparente)

        Esto permite que el usuario:
          - Suba boton_jugar.png y se usa esa imagen para ese boton
          - Suba boton_normal.png y aplica a todos los demas
          - No suba nada y los botones se vean igual decentes

        Parametros importantes:
            hover         -> True si el mouse esta encima
            activo        -> True si esta seleccionado / es el "principal"
            clave_imagen  -> nombre base del PNG (ej. "boton_jugar")
            dibujar_texto -> None=auto, True=siempre, False=nunca.
                             En auto, solo dibujamos texto si NO se uso
                             imagen especifica (asumimos que las imagenes
                             ya traen su texto baked-in).
        """
        c = self.col
        col_primario = c["primario"]
        if color_txt is None:
            color_txt = c["texto"]

        # ---- BUSCAR IMAGEN APROPIADA ----
        # Recorremos la cascada de prioridades.
        img_boton = None
        if clave_imagen and self.recursos is not None:
            # Prioridad 1: variante _hover si estamos en hover.
            if hover:
                img_boton = self.recursos.escalar(
                    clave_imagen + "_hover", rect.w, rect.h)
            # Prioridad 2: imagen base del boton.
            if img_boton is None:
                img_boton = self.recursos.escalar(
                    clave_imagen, rect.w, rect.h)
            # Prioridad 3: imagen generica segun estado.
            if img_boton is None:
                nombre = "boton_hover" if hover else (
                    "boton_activo" if activo else "boton_normal")
                img_boton = self.recursos.escalar(nombre, rect.w, rect.h)

        # ---- SOMBRA PROYECTADA ----
        # La sombra se ofrecera un poco mas grande cuando hay hover
        # para reforzar la sensacion de elevacion.
        offset_sombra = 6 if hover else 4
        sombra = pygame.Surface((rect.w + 8, rect.h + offset_sombra + 4),
                                pygame.SRCALPHA)
        # Rect ligeramente mas pequeno (inflate -2,-2) para que la
        # sombra no salga por los bordes del rect dibujado.
        pygame.draw.rect(sombra, (0, 0, 0, 110),
                         sombra.get_rect().inflate(-2, -2),
                         border_radius=12)
        self.screen.blit(sombra, (rect.x - 4, rect.y + offset_sombra - 2))

        # ---- ELEVACION ----
        # En hover, dibujamos el boton 2px arriba. Combinado con la
        # sombra mas grande, da efecto de "levantarse" hacia el usuario.
        r_dibujo = rect.move(0, -2) if hover else rect

        # ---- GLOW TRASERO ----
        # El glow en hover es SUAVE, desaturado, sin blend aditivo.
        # La version original usaba BLEND_RGBA_ADD con alpha 70 y se
        # veia muy "fluorescente feo" (el usuario lo reporto).
        # Esta version mezcla el color primario con un gris claro
        # (45% del color + 90 puntos de luminosidad) para apagarlo.
        if hover and not activo:
            r_g = int(col_primario[0] * 0.45 + 90)
            g_g = int(col_primario[1] * 0.45 + 90)
            b_g = int(col_primario[2] * 0.45 + 90)
            glow = pygame.Surface((r_dibujo.w + 16, r_dibujo.h + 16),
                                  pygame.SRCALPHA)
            pygame.draw.rect(glow, (r_g, g_g, b_g, 35),
                             glow.get_rect(), border_radius=14)
            # Sin special_flags -> blend normal (no aditivo).
            self.screen.blit(glow, (r_dibujo.x - 8, r_dibujo.y - 8))

        # ---- DIBUJAR EL BOTON EN SI ----
        if img_boton is not None:
            # Modo imagen: solo pintamos el PNG.
            self.screen.blit(img_boton, r_dibujo.topleft)
        else:
            # Modo glassmorphism (fallback): rect semi-transparente
            # con borde luminoso.
            if color_bg is None:
                if activo:
                    color_bg = col_primario
                elif hover:
                    color_bg = aclarar(c["panel"], 1.35)
                else:
                    color_bg = c["panel"]
            fondo = pygame.Surface((r_dibujo.w, r_dibujo.h), pygame.SRCALPHA)
            pygame.draw.rect(fondo, (*color_bg, 230), fondo.get_rect(),
                             border_radius=12)
            self.screen.blit(fondo, r_dibujo.topleft)
            grosor_borde = 2 if hover or activo else 1
            color_borde = c["texto"] if activo else col_primario
            pygame.draw.rect(self.screen, color_borde, r_dibujo,
                             grosor_borde, border_radius=12)

        # ---- ETIQUETA DE TEXTO ----
        # Si usamos imagen, no dibujamos texto (asumimos que la imagen
        # ya lo trae). Si es fallback glassmorphism, si dibujamos texto.
        # El llamador puede forzar con dibujar_texto=True/False.
        if dibujar_texto is True or (dibujar_texto is None and img_boton is None):
            fuente = self.fuentes["md"]
            r = fuente.render(etiqueta, True, color_txt)
            self.screen.blit(r, r.get_rect(center=r_dibujo.center))


# ===========================================================================
# CLASE EstadoJuego - Datos puros del estado de la partida
# ===========================================================================
class EstadoJuego:
    """Contenedor del estado de la partida actual.

    Es basicamente un struct: no tiene metodos importantes, solo data.
    Cuando empezamos una partida nueva, simplemente creamos un nuevo
    EstadoJuego — esto resetea todo de un golpe sin tener que limpiar
    cada campo a mano.

    Campos:
      - grafo: el Grafo del mapa actual
      - situaciones: dict id_nodo -> ArbolDecisiones para ese nodo
      - cola_eventos: ColaPrioridad de eventos pendientes (propagaciones)
      - jugadores: lista de dicts {id, nombre, skin, pos, puntos, poderes}
      - jugador_local: indice del jugador local en la lista
      - salud_comunidad: HP global de la red (0 = derrota)
      - tiempo_inicio/actual: para mostrar duracion de partida
      - fin / victoria: flags del fin de partida
      - mensajes_flotantes / mensaje_log: notificaciones para el HUD
      - modo / dificultad: configuracion de la partida
    """
    def __init__(self):
        self.grafo = None
        self.situaciones = {}
        self.cola_eventos = ColaPrioridad()
        self.jugadores = []
        self.jugador_local = 0
        self.salud_comunidad = settings.SALUD_COMUNIDAD_INICIAL
        self.tiempo_inicio = 0
        self.tiempo_actual = 0
        self.fin = False
        self.victoria = False
        # mensajes_flotantes: lista de (texto, t0, color) — se muestran
        # por unos segundos abajo a la izq y desaparecen con fade.
        self.mensajes_flotantes = []
        # mensaje_log: ultimas N notificaciones, persisten en el HUD.
        self.mensaje_log = []
        self.modo = "individual"      # individual | servidor | cliente
        self.dificultad = "media"     # facil | media | dificil (no usado aun)

    def msg(self, texto, color=None):
        """Anade un mensaje a las notificaciones del juego.

        Se muestra como mensaje flotante (3s) y queda en el log
        permanente del HUD (ultimos 12 mensajes).
        """
        self.mensajes_flotantes.append((texto, time.time(), color))
        self.mensaje_log.append(texto)
        # Mantenemos el log acotado a 12 elementos para no consumir
        # memoria infinita en partidas largas.
        if len(self.mensaje_log) > 12:
            self.mensaje_log.pop(0)


# ===========================================================================
# CLASE Juego - El orquestador principal
# ===========================================================================
class Juego:
    """Cerebro del juego.

    Tiene el loop principal (correr) y todas las pantallas. La pantalla
    activa se almacena en self.pantalla y cada frame llamamos al metodo
    correspondiente (pantalla_menu, pantalla_mapa, etc.).
    """

    def __init__(self):
        # ---- INICIALIZACION DE PYGAME ----
        pygame.init()
        pygame.display.set_caption(settings.TITLE)
        # ---- VENTANA REDIMENSIONABLE ----
        # El flag pygame.RESIZABLE permite que el usuario arrastre la
        # esquina/borde de la ventana para agrandarla o achicarla.
        # Cuando lo hace, pygame emite un evento VIDEORESIZE que
        # manejamos en el loop principal (ver _redimensionar).
        self.screen = pygame.display.set_mode(
            (settings.WIDTH, settings.HEIGHT), pygame.RESIZABLE)
        # Clock controla la velocidad del loop (60 FPS objetivo).
        self.clock = pygame.time.Clock()

        # ---- SUBSISTEMAS ----
        self.audio = GestorAudio()
        self.recursos = Recursos()
        # Pasamos recursos a la UI para que pueda usar imagenes en botones.
        self.ui = UI(self.screen, "normal", "mediano", recursos=self.recursos)
        self.estado = EstadoJuego()

        # ---- ESTADO DE NAVEGACION ----
        self.pantalla = "menu"             # pantalla activa
        self.servidor = None               # instancia Servidor si somos host
        self.cliente = None                # instancia Cliente si somos invitado
        self.skin_idx = 0                  # skin elegido (0..len(SKINS)-1)
        self.nombre_jugador = "Guardian"
        self.config_host = settings.HOST_DEFAULT  # IP a conectar (modo cliente)
        self.config_port = settings.PORT_DEFAULT
        self.ip_local = descubrir_ip_local()   # IP propia para mostrar al host
        self.input_activo = None           # campo de texto activo (nombre/host)

        # ---- ESTADO DEL EVENTO ACTIVO ----
        self.nodo_evento_actual = None     # nodo cuya situacion estamos viendo
        self.opcion_hover = -1             # opcion del arbol bajo el mouse
        self.pantalla_anterior = "menu"    # a donde volver desde "ayuda"
        # Ruta de indices que el jugador eligio en el arbol actual.
        # Se llena cada vez que llamamos arbol.elegir(i) en pantalla_evento.
        # Cuando el cliente llega a una hoja, envia esta ruta al servidor
        # con la accion "decidir" para que el server pueda replayear el
        # mismo camino y aplicar el efecto correcto al jugador correcto.
        self.ruta_decision = []
        # Cliente: ultima posicion conocida del jugador local. Lo usamos
        # para detectar "acabo de moverme a un nuevo nodo" en
        # _sincronizar_desde_servidor, y auto-abrir la situacion si el
        # nodo tiene conflicto sin resolver. Sin esto, el invitado se
        # quedaba en el mapa sin poder accionar.
        self._pos_jugador_anterior = -1

        # ---- EFECTOS VISUALES ----
        self.particulas = GestorParticulas()
        self.transicion = Transicion()
        # Cache de gradientes: clave (paleta, w, h) -> Surface ya pintada.
        # Evita regenerar el gradiente cada frame (operacion cara).
        self._gradiente_cache = {}
        self._t_anim = 0.0                 # tiempo acumulado para animaciones

        # ---- ICONO DE VENTANA ----
        # Si existe un logo o icono, lo usamos como icono de la app.
        ic = self.recursos.cargar("LinkUp_Logo") or self.recursos.cargar("icono_app")
        if ic:
            try:
                pygame.display.set_icon(ic)
            except pygame.error:
                # No es critico si falla.
                pass

    def _gradiente_fondo(self):
        """Devuelve la Surface del gradiente de fondo cacheada para la
        paleta actual. Lo crea si no existe."""
        c = self.ui.col
        clave = (self.ui.paleta_clave, settings.WIDTH, settings.HEIGHT)
        if clave not in self._gradiente_cache:
            self._gradiente_cache[clave] = crear_gradiente_cacheado(
                settings.WIDTH, settings.HEIGHT, c["fondo"], c["fondo2"]
            )
        return self._gradiente_cache[clave]

    def cambiar_pantalla(self, destino):
        """Cambia de pantalla con efecto fade. Usar en vez de
        `self.pantalla = ...` para que la transicion sea suave."""
        def _aplicar(d):
            self.pantalla = d
        self.transicion.iniciar(destino, _aplicar)

    # ======================== LOOP PRINCIPAL ========================
    def correr(self):
        """Bucle infinito del juego.

        Cada iteracion (frame):
          1) Calcula dt (delta time) y actualiza _t_anim
          2) Procesa eventos globales (cerrar, F1, F2, F3)
          3) Llama al handler de la pantalla activa
          4) Actualiza/dibuja particulas globales
          5) Aplica transicion fade
          6) flip() muestra el frame al usuario
        """
        while True:
            # tick(FPS) duerme lo necesario para mantener 60 FPS.
            # Devuelve milisegundos transcurridos; / 1000 para segundos.
            dt = self.clock.tick(settings.FPS) / 1000.0
            self._t_anim += dt
            eventos = pygame.event.get()
            for e in eventos:
                if e.type == pygame.QUIT:
                    # Usuario cerro la ventana.
                    self.salir()
                # VIDEORESIZE: el usuario arrastro la esquina/borde para
                # cambiar el tamano de la ventana. Reaccionamos
                # actualizando settings.WIDTH/HEIGHT (que se leen en
                # todos lados) y reescalando posiciones de los nodos
                # si hay una partida en curso.
                if e.type == pygame.VIDEORESIZE:
                    self._redimensionar(e.w, e.h)
                # F1: abrir pantalla de ayuda (recordamos a donde volver)
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F1:
                    if self.pantalla != "ayuda":
                        self.pantalla_anterior = self.pantalla
                    self.pantalla = "ayuda"
                # F2: toggle paleta normal/daltonico
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F2:
                    nueva = "daltonico" if self.ui.paleta_clave == "normal" else "normal"
                    self.ui.cambiar_paleta(nueva)
                    # Limpiamos cache de gradientes para que se regeneren
                    # con los nuevos colores.
                    self._gradiente_cache.clear()
                    self.estado.msg(f"Paleta: {nueva}")
                # F3: ciclar entre pequeno/mediano/grande
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F3:
                    actuales = list(settings.TAMANOS_FUENTE.keys())
                    i = (actuales.index(self.ui.tam_fuente) + 1) % len(actuales)
                    self.ui.cambiar_tam_fuente(actuales[i])
                    self.estado.msg(f"Tamano texto: {actuales[i]}")

            # ---- DISPATCH a la pantalla activa ----
            if self.pantalla == "menu":
                self.pantalla_menu(eventos)
            elif self.pantalla == "config":
                self.pantalla_config(eventos)
            elif self.pantalla == "lobby_host":
                self.pantalla_lobby_host(eventos)
            elif self.pantalla == "lobby_cliente":
                self.pantalla_lobby_cliente(eventos)
            elif self.pantalla == "ayuda":
                self.pantalla_ayuda(eventos)
            elif self.pantalla == "mapa":
                self.pantalla_mapa(eventos, dt)
            elif self.pantalla == "pausa":
                self.pantalla_pausa(eventos)
            elif self.pantalla == "evento":
                self.pantalla_evento(eventos)
            elif self.pantalla == "fin":
                self.pantalla_fin(eventos)
            else:
                # Pantalla desconocida: volver al menu por seguridad.
                self.pantalla = "menu"

            # ---- CAPA DE EFECTOS GLOBALES ----
            # Las particulas se dibujan encima de todo lo de la pantalla
            # pero DEBAJO del fade. Asi se ven sobre cualquier escena.
            self.particulas.update(dt)
            self.particulas.dibujar(self.screen)

            # ---- TRANSICION FADE ----
            # Va siempre encima de todo para que el fundido cubra todo.
            self.transicion.update(dt)
            self.transicion.dibujar(self.screen)

            # ---- FILTRO DALTONICO (post-procesamiento) ----
            # Solo si el modo daltonico esta activo. Esto transforma
            # TODOS los pixeles del frame (incluyendo imagenes) para
            # mantener una paleta accesible consistente.
            if self.ui.paleta_clave == "daltonico":
                self._aplicar_filtro_daltonico()

            # flip() copia el buffer al display fisico (double-buffering).
            pygame.display.flip()

    def _aplicar_filtro_daltonico(self):
        """Aplica el filtro daltonico sobre TODA la pantalla del frame actual.

        Cuando el modo daltonico esta activo (F2 o desde el menu de pausa),
        llamamos a este metodo justo antes de pygame.display.flip(). El
        filtro hace una transformacion de color pixel-por-pixel sobre el
        framebuffer, asi que afecta:

          - Gradientes y rellenos dibujados con pygame.draw
          - Paneles glassmorphism y texto
          - IMAGENES (PNGs de nodos, botones, fondos, avatares)

        Esto resuelve la inconsistencia visual previa: antes el modo
        daltonico solo cambiaba la paleta de UI, pero las imagenes
        cargadas como bitmaps mantenian sus colores rojo/verde
        originales. Ahora todo se transforma uniformemente.

        Implementacion:
          1. pygame.surfarray.pixels3d() devuelve una VISTA del buffer
             (sin copiar la memoria). Esto lockea la surface.
          2. La aplanamos a (N, 3) para poder aplicar la matriz a
             todos los pixeles a la vez con un solo matmul de numpy.
          3. Clamp a [0, 255] y volver a uint8.
          4. Copiar de vuelta al buffer original con arr[:] (mantiene
             el lock; lo soltamos con `del arr` al final).

        Si numpy no esta instalado, el filtro se omite silenciosamente
        — el juego sigue funcionando, solo que las imagenes no recibiran
        el shift de color (caemos al comportamiento viejo).
        """
        if not _NUMPY_OK:
            return
        try:
            # pixels3d puede fallar si la surface no es accesible
            # como array (por ejemplo si esta en otro proceso o
            # comprimida). En ese caso simplemente no aplicamos filtro.
            arr = pygame.surfarray.pixels3d(self.screen)
        except (pygame.error, ValueError):
            return
        forma = arr.shape
        # Aplanar a (N_pixeles, 3) y promover a float para no perder
        # precision al multiplicar (uint8 desbordaria muy facil).
        pix = arr.reshape(-1, 3).astype(_np.float32)
        # Producto matricial: cada pixel pasa por la matriz daltonica.
        # @ es el operador matmul de numpy (equivalente a np.dot).
        nuevo = pix @ _MATRIZ_DALTONIZE.T
        # Clamp para evitar overflow al volver a uint8.
        _np.clip(nuevo, 0, 255, out=nuevo)
        # Volcar de regreso al buffer manteniendo la referencia (arr[:]
        # mantiene el lock; no usar `arr = ...` porque rompe la vista).
        arr[:] = nuevo.reshape(forma).astype(_np.uint8)
        # Liberar el lock soltando la referencia local.
        del arr

    def _redimensionar(self, nuevo_w, nuevo_h):
        """Reacciona al evento VIDEORESIZE.

        Pasos que hacemos cuando cambia el tamano de la ventana:
          1) Clampeamos al minimo (settings.MIN_WIDTH/MIN_HEIGHT) para
             que la UI no se rompa si el usuario hace la ventana muy
             chica.
          2) Calculamos los factores de escala (sx, sy) en base al
             tamano anterior. Los necesitamos para reposicionar los
             nodos del grafo proporcionalmente.
          3) Mutamos settings.WIDTH/HEIGHT. Como en el codigo siempre
             leemos `settings.WIDTH` (no una copia local), todos los
             modulos ven los nuevos valores automaticamente.
          4) Recreamos la Surface del display con el nuevo tamano.
             pygame.display.set_mode() es la unica forma de cambiar
             el tamano del buffer subyacente.
          5) Actualizamos `self.ui.screen` para que la UI dibuje en
             la nueva Surface.
          6) Limpiamos el cache de gradientes (esta keyeado por tamano,
             asi que las entradas viejas son inutiles y desperdician
             memoria).
          7) Si hay una partida en curso, reescalamos las posiciones
             de los nodos del grafo proporcionalmente para que no
             queden todos amontonados en la esquina superior izquierda
             cuando agrandemos, o saliendo de pantalla cuando achiquemos.
        """
        # 1) Clamp al minimo permitido.
        nuevo_w = max(nuevo_w, settings.MIN_WIDTH)
        nuevo_h = max(nuevo_h, settings.MIN_HEIGHT)

        # 2) Factor de escala basado en el tamano ANTERIOR. Lo usamos
        # mas abajo para reposicionar nodos. Ojo: no se puede hacer
        # despues de mutar settings, por eso lo guardamos ahora.
        sx = nuevo_w / settings.WIDTH
        sy = nuevo_h / settings.HEIGHT

        # 3) Mutamos los valores globales. settings es un modulo, y
        # WIDTH/HEIGHT son atributos a nivel de modulo. Cualquier
        # `settings.WIDTH` que se evalue despues vera el nuevo valor.
        settings.WIDTH = nuevo_w
        settings.HEIGHT = nuevo_h

        # 4) Recreamos la Surface del display con el flag RESIZABLE
        # (no perderlo, sino la ventana deja de ser redimensionable
        # despues del primer resize).
        self.screen = pygame.display.set_mode(
            (nuevo_w, nuevo_h), pygame.RESIZABLE)

        # 5) Actualizamos la referencia que la UI tiene del screen.
        # Si no lo hicieramos, la UI seguiria dibujando en la Surface
        # vieja y los textos/paneles no apareceria en pantalla.
        self.ui.screen = self.screen

        # 6) Limpiamos el cache de gradientes (su clave es (paleta, w, h),
        # entonces las entradas viejas ya no se van a usar).
        self._gradiente_cache.clear()

        # 7) Reescalar nodos del grafo si hay una partida activa.
        # Si no hay grafo (estamos en el menu, lobby, etc), no
        # hace nada.
        try:
            grafo = self.estado.grafo
        except AttributeError:
            grafo = None
        if grafo is not None and hasattr(grafo, "nodos"):
            for nodo in grafo.nodos.values():
                nodo.x *= sx
                nodo.y *= sy

    def salir(self):
        """Cierre limpio: detiene servidor, cliente, pygame, y termina."""
        try:
            if self.servidor:
                self.servidor.detener()
            if self.cliente:
                self.cliente.desconectar()
        except Exception:
            pass
        pygame.quit()
        sys.exit(0)

    # ===================== UTILIDADES DE FONDO =====================
    def _dibujar_fondo(self, nombre_imagen, fallback_animado=True):
        """Dibuja una imagen de fondo o, si no existe, gradiente +
        puntos animados como respaldo.

        Sobre la imagen siempre aplicamos un VELO gradiente sutil
        para oscurecer la parte inferior y resaltar la UI que va
        ahi (HUD, botones), ademas de unificar la estetica cyber.
        """
        c = self.ui.col
        fondo = self.recursos.fondo(nombre_imagen, settings.WIDTH, settings.HEIGHT)
        if fondo is not None:
            self.screen.blit(fondo, (0, 0))
            # Velo gradiente para oscurecer abajo.
            velo = pygame.Surface((settings.WIDTH, settings.HEIGHT),
                                  pygame.SRCALPHA)
            for y in range(settings.HEIGHT):
                t = y / settings.HEIGHT
                alpha = int(40 + 80 * t)  # mas opaco abajo
                pygame.draw.line(velo, (*c["fondo2"], alpha),
                                 (0, y), (settings.WIDTH, y))
            self.screen.blit(velo, (0, 0))
            return
        # ---- SIN IMAGEN: gradiente puro + animacion sutil ----
        self.screen.blit(self._gradiente_fondo(), (0, 0))
        if fallback_animado:
            # Puntos cyber girando en orbita. Pura decoracion para que
            # el fondo no se vea estatico cuando no hay imagen.
            t = time.time() * 0.3
            for i in range(40):
                ang = i * 0.4 + t
                r = 200 + 60 * math.sin(t * 0.7 + i)
                x = settings.WIDTH // 2 + math.cos(ang) * r
                y = settings.HEIGHT // 2 + math.sin(ang) * r * 0.6
                pygame.draw.circle(self.screen, c["primario"],
                                   (int(x), int(y)), 2)

    # ===================== PANTALLA: MENU PRINCIPAL =====================
    def pantalla_menu(self, eventos):
        """Pantalla inicial con logo, titulo, y botones grandes."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")

        # Logo del juego (centrado arriba). Si no existe, mostramos
        # un titulo de texto como fallback.
        logo = self.recursos.logo()
        if logo:
            # Calculamos tamano manteniendo la proporcion original.
            ratio = logo.get_width() / logo.get_height()
            h = 220
            w = int(h * ratio)
            if w > 700:
                w = 700; h = int(w / ratio)
            logo_esc = pygame.transform.smoothscale(logo, (w, h))
            self.screen.blit(logo_esc, (settings.WIDTH // 2 - w // 2, 30))
            y_titulo = 30 + h + 10
        else:
            self.ui.texto("LinkUp", "xl", c["primario"],
                          settings.WIDTH // 2, 60, centrado=True, sombra=True)
            self.ui.texto("Guardianes del Nexo", "lg", c["texto"],
                          settings.WIDTH // 2, 130, centrado=True, sombra=True)
            y_titulo = 175

        # Tagline (frase de mision).
        self.ui.texto("Construye empatia. Deten el odio. Une la red.",
                      "sm", c["texto_sec"], settings.WIDTH // 2, y_titulo,
                      centrado=True, sombra=True)

        # ---- BOTONES DEL MENU ----
        # Cada tupla: (texto_visible, accion_interna, nombre_imagen_PNG)
        opciones = [
            ("Jugar - Individual",       "individual", "boton_individual"),
            ("Hospedar partida (Host)",  "host",       "boton_host"),
            ("Unirse a partida",         "join",       "boton_unirse"),
            ("Configuracion",            "config",     "boton_config"),
            ("Ayuda",                    "ayuda",      "boton_ayuda"),
            ("Salir",                    "salir",      "boton_salir"),
        ]
        x = settings.WIDTH // 2 - 180
        y0 = max(280, y_titulo + 40)
        mouse = pygame.mouse.get_pos()
        # Dibujamos cada boton y verificamos clicks.
        for i, (txt, accion, clave_img) in enumerate(opciones):
            rect = pygame.Rect(x, y0 + i * 58, 360, 46)
            hover = rect.collidepoint(mouse)
            self.ui.boton(rect, txt, hover=hover, clave_imagen=clave_img)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect.collidepoint(e.pos):
                    self.audio.play("click")
                    self._accion_menu(accion)

        # Pie de pagina con teclas globales.
        self.ui.texto("F1 Ayuda  ·  F2 Modo daltonico  ·  F3 Tamano texto",
                      "xs", c["texto_sec"], settings.WIDTH // 2,
                      settings.HEIGHT - 28, centrado=True, sombra=True)

    def _accion_menu(self, accion):
        """Despacha el clic de cada boton del menu principal."""
        if accion == "individual":
            self.estado.modo = "individual"
            self._iniciar_partida_local()
        elif accion == "host":
            self.estado.modo = "servidor"
            self._iniciar_host()
        elif accion == "join":
            self.estado.modo = "cliente"
            self.pantalla = "lobby_cliente"
        elif accion == "config":
            self.pantalla = "config"
        elif accion == "ayuda":
            self.pantalla = "ayuda"
        elif accion == "salir":
            self.salir()

    # ===================== PANTALLA: CONFIGURACION =====================
    def pantalla_config(self, eventos):
        """Pantalla donde el jugador elige skin y escribe su nombre."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Configuracion", "xl", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True, sombra=True)

        # ---- SELECTOR DE SKIN ----
        self.ui.texto("Elige tu skin:", "md", c["texto"], 80, 130, sombra=True)
        mouse = pygame.mouse.get_pos()
        for i, skin in enumerate(settings.SKINS):
            x = 80 + i * 200
            y = 170
            rect = pygame.Rect(x, y, 180, 280)
            # Si es el skin seleccionado actualmente, el panel es cyan.
            color_bg = c["panel"] if i != self.skin_idx else c["primario"]
            self.ui.panel(rect, color=color_bg, borde=c["primario"], radio=12)

            # Intentamos cargar la imagen del skin completo. Si no
            # existe, dibujamos un circulo de color con su simbolo.
            img = self.recursos.skin_completo(skin["nombre"])
            if img:
                r = img.get_width() / img.get_height()
                h = 200
                w = int(h * r)
                if w > rect.w - 16:
                    w = rect.w - 16; h = int(w / r)
                img_esc = pygame.transform.smoothscale(img, (w, h))
                self.screen.blit(img_esc, (rect.centerx - w // 2, rect.y + 20))
            else:
                # Fallback: circulo + simbolo
                pygame.draw.circle(self.screen, skin["color"],
                                   (rect.centerx, rect.y + 90), 50)
                self.ui.texto(skin["simbolo"], "xl", (20, 20, 30),
                              rect.centerx, rect.y + 60, centrado=True)

            self.ui.texto(skin["nombre"], "md", c["texto"],
                          rect.centerx, rect.bottom - 36, centrado=True)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect.collidepoint(e.pos):
                    self.skin_idx = i
                    self.audio.play("click")

        # ---- CAMPO DE TEXTO: NOMBRE ----
        self.ui.texto("Tu nombre:", "md", c["texto"], 80, 480, sombra=True)
        rect_nombre = pygame.Rect(80, 520, 400, 40)
        pygame.draw.rect(self.screen, c["panel"], rect_nombre, border_radius=8)
        pygame.draw.rect(self.screen, c["primario"], rect_nombre, 2, border_radius=8)
        self.ui.texto(self.nombre_jugador, "md", c["texto"],
                      rect_nombre.x + 10, rect_nombre.y + 8)
        for e in eventos:
            # Click en el campo: activamos input.
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_nombre.collidepoint(e.pos):
                self.input_activo = "nombre"
            # Si el input esta activo, procesamos teclado.
            if e.type == pygame.KEYDOWN and self.input_activo == "nombre":
                if e.key == pygame.K_RETURN:
                    self.input_activo = None
                elif e.key == pygame.K_BACKSPACE:
                    self.nombre_jugador = self.nombre_jugador[:-1]
                elif len(self.nombre_jugador) < 16 and e.unicode.isprintable():
                    # Limitamos a 16 caracteres y a imprimibles.
                    self.nombre_jugador += e.unicode

        # Info de accesibilidad actual.
        self.ui.texto(
            f"Paleta: {self.ui.paleta_clave} (F2) · Texto: {self.ui.tam_fuente} (F3)",
            "sm", c["texto_sec"], 80, 580, sombra=True)

        # Boton de volver al menu.
        rect_volver = pygame.Rect(80, settings.HEIGHT - 70, 200, 46)
        self.ui.boton(rect_volver, "<- Volver",
                      hover=rect_volver.collidepoint(mouse),
                      clave_imagen="boton_volver")
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_volver.collidepoint(e.pos):
                self.audio.play("click")
                self.pantalla = "menu"

    # ===================== PANTALLA: AYUDA =====================
    def pantalla_ayuda(self, eventos):
        """Pantalla con instrucciones del juego, controles y estructuras
        de datos usadas. Accesible desde F1 en cualquier momento."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        # Panel grande semi-transparente con todo el texto.
        rect_p = pygame.Rect(40, 30, settings.WIDTH - 80, settings.HEIGHT - 110)
        self.ui.panel(rect_p, color=c["fondo"], borde=c["primario"],
                      radio=14, alpha=220)
        self.ui.texto("Como jugar", "xl", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True)

        # Texto largo en un solo string para no romper el flujo visual.
        texto = (
            "  Eres un Guardian del Nexo en CiberNexo. Tu mision es recorrer\n"
            "  la red social ayudando a victimas de ciberbullying,\n"
            "  neutralizando acosadores y formando puentes de empatia.\n\n"
            "Controles:\n"
            "  · Click en un nodo vecino para moverte.\n"
            "  · Click en tu nodo o uno vecino activo: abre el arbol de decisiones.\n"
            "  · Algunas aristas son muros de odio (rojas): usa Voz Amplificada (P).\n"
            "  · P: usa el poder mas relevante en tu posicion.\n"
            "  · F1 ayuda · F2 daltonico · F3 tamano texto · ESC menu · R reiniciar\n\n"
            "Tipos de nodo:\n"
            "  · Victima: necesita apoyo · Bully: acosador a transformar\n"
            "  · Aliado: puede unirse · Neutro: observador · Central: el corazon\n\n"
            "Estructuras de datos usadas:\n"
            "  · GRAFO   -> la red social\n"
            "  · ARBOL   -> arbol de decisiones de cada situacion\n"
            "  · COLA DE PRIORIDAD -> orden de propagacion del odio\n\n"
            "Inclusion: modo daltonico, texto ajustable, skins diversos,\n"
            "iconos + colores, contraste alto, audio descriptivo."
        )
        self.ui.texto(texto, "sm", c["texto"], 80, 100)

        # Boton de volver. La pantalla destino la guardamos antes de
        # entrar a ayuda (en pantalla_anterior), asi sabemos a donde
        # regresar (puede ser menu, pausa, etc.)
        rect_volver = pygame.Rect(settings.WIDTH // 2 - 90,
                                  settings.HEIGHT - 70, 180, 46)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_volver, "Volver",
                      hover=rect_volver.collidepoint(mouse),
                      clave_imagen="boton_volver")
        destino_volver = self.pantalla_anterior or "menu"
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_volver.collidepoint(e.pos):
                self.audio.play("click")
                self.pantalla = destino_volver
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.pantalla = destino_volver

    # ===================== PANTALLAS DE LOBBY (multijugador) =====================
    def pantalla_lobby_host(self, eventos):
        """Sala de espera del host: muestra IP, jugadores conectados,
        y permite iniciar la partida."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Sala de Guardianes (HOST)", "lg", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True, sombra=True)
        self.ui.texto("Comparte esta IP con tus aliados:", "md", c["texto"],
                      settings.WIDTH // 2, 120, centrado=True, sombra=True)
        # IP local + puerto, en grande, para que sea facil de copiar.
        self.ui.texto(f"{self.ip_local} : {self.config_port}", "xl",
                      c["primario"], settings.WIDTH // 2, 160,
                      centrado=True, sombra=True)

        # Si el servidor esta corriendo, mostramos la lista de conectados.
        if self.servidor:
            # IMPORTANTE: procesar() lee mensajes pendientes (JOIN, etc.)
            # Sin esto el host no veria los clientes que se conectan.
            self.servidor.procesar()
            jugs = self.servidor.jugadores()
            panel = pygame.Rect(settings.WIDTH//2 - 250, 240, 500, 280)
            self.ui.panel(panel, alpha=180)
            # +1 porque el host tambien cuenta (no esta en jugs).
            self.ui.texto(f"Conectados: {len(jugs) + 1}/4", "md", c["texto"],
                          panel.x + 20, panel.y + 20)
            self.ui.texto(f"  · Tu (Host) — {self.nombre_jugador}", "sm",
                          c["texto"], panel.x + 30, panel.y + 60)
            for i, (jid, nom, sk) in enumerate(jugs):
                self.ui.texto(f"  · Cliente #{jid} — {nom}", "sm",
                              c["texto"], panel.x + 30, panel.y + 90 + i * 28)

        # Botones de iniciar / cancelar.
        rect_start = pygame.Rect(settings.WIDTH // 2 - 150,
                                 settings.HEIGHT - 130, 300, 56)
        rect_cancel = pygame.Rect(settings.WIDTH // 2 - 100,
                                  settings.HEIGHT - 64, 200, 44)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_start, "Iniciar partida",
                      hover=rect_start.collidepoint(mouse), activo=True,
                      clave_imagen="boton_iniciar")
        self.ui.boton(rect_cancel, "Cancelar",
                      hover=rect_cancel.collidepoint(mouse),
                      clave_imagen="boton_cancelar")
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if rect_start.collidepoint(e.pos):
                    self.audio.play("nivel")
                    self._iniciar_partida_multijugador()
                elif rect_cancel.collidepoint(e.pos):
                    if self.servidor:
                        self.servidor.detener()
                        self.servidor = None
                    self.pantalla = "menu"

    def pantalla_lobby_cliente(self, eventos):
        """Pantalla del cliente: campo para ingresar IP y boton conectar."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Unirse a una partida", "lg", c["primario"],
                      settings.WIDTH // 2, 60, centrado=True, sombra=True)
        self.ui.texto("IP del host:", "md", c["texto"], 200, 160, sombra=True)
        # Campo de texto para la IP.
        rect_ip = pygame.Rect(200, 200, 400, 40)
        pygame.draw.rect(self.screen, c["panel"], rect_ip, border_radius=8)
        pygame.draw.rect(self.screen, c["primario"], rect_ip, 2, border_radius=8)
        self.ui.texto(self.config_host, "md", c["texto"],
                      rect_ip.x + 10, rect_ip.y + 8)

        mouse = pygame.mouse.get_pos()
        rect_conn = pygame.Rect(settings.WIDTH // 2 - 120, 300, 240, 50)
        self.ui.boton(rect_conn, "Conectar",
                      hover=rect_conn.collidepoint(mouse), activo=True,
                      clave_imagen="boton_conectar")
        rect_back = pygame.Rect(80, settings.HEIGHT - 70, 200, 44)
        self.ui.boton(rect_back, "<- Volver",
                      hover=rect_back.collidepoint(mouse),
                      clave_imagen="boton_volver")

        # Si ya hay cliente activo, mostramos estado de conexion.
        if self.cliente:
            self.cliente.procesar()
            self.ui.texto("Estado:", "md", c["primario"], 80, 400, sombra=True)
            estado_txt = "Conectado" if self.cliente.conectado else "Desconectado"
            self.ui.texto(estado_txt, "md", c["texto"], 200, 400, sombra=True)
            # Ultimos 6 mensajes del log del cliente.
            for i, m in enumerate(self.cliente.mensajes[-6:]):
                self.ui.texto(m, "sm", c["texto_sec"], 80, 440 + i * 24, sombra=True)
            # Cuando recibimos el primer ESTADO del servidor, eso
            # significa que el host inicio la partida. Sincronizamos
            # nuestro estado local y saltamos al mapa.
            if self.cliente.estado_juego:
                self._sincronizar_desde_servidor()
                self.pantalla = "mapa"

        # ---- INPUT ----
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if rect_ip.collidepoint(e.pos):
                    self.input_activo = "host"
                elif rect_conn.collidepoint(e.pos):
                    self.audio.play("click")
                    self._conectar_cliente()
                elif rect_back.collidepoint(e.pos):
                    if self.cliente:
                        self.cliente.desconectar()
                        self.cliente = None
                    self.pantalla = "menu"
            # Tipear en el campo de IP.
            if e.type == pygame.KEYDOWN and self.input_activo == "host":
                if e.key == pygame.K_RETURN:
                    self.input_activo = None
                elif e.key == pygame.K_BACKSPACE:
                    self.config_host = self.config_host[:-1]
                elif len(self.config_host) < 20:
                    ch = e.unicode
                    # Solo aceptamos digitos y puntos (formato IP).
                    if ch and (ch.isdigit() or ch == "."):
                        self.config_host += ch

    # ===================== PANTALLA: MAPA (el juego principal) =====================
    def pantalla_mapa(self, eventos, dt):
        """Pantalla principal donde se juega. Dibuja el grafo, los
        jugadores, el HUD, y procesa input para moverse / usar poderes.

        Es la pantalla mas compleja por todo lo que tiene que pintar
        cada frame: gradiente/imagen de fondo, aristas con paquetes
        animados, nodos con glow y pulso, jugadores, HUD lateral,
        mensajes flotantes, tooltips.
        """
        c = self.ui.col
        self._dibujar_fondo("fondo_mapa")

        # ---- SINCRONIZACION DE RED ----
        # Si somos servidor, leemos mensajes y aplicamos acciones de
        # los clientes. _sincronizar_jugadores_conectados elimina de
        # nuestra lista los clientes que se desconectaron.
        if self.servidor:
            self.servidor.procesar()
            self._sincronizar_jugadores_conectados()
            self._procesar_acciones_servidor()

        # (Bloque duplicado historico — no rompe pero podria limpiarse.)
        if self.servidor:
            self.servidor.procesar()
            self._procesar_acciones_servidor()
        # Si somos cliente, leemos el ESTADO del server y sincronizamos.
        if self.cliente:
            self.cliente.procesar()
            if self.cliente.estado_juego:
                self._sincronizar_desde_servidor()

        # _tick avanza el tiempo, ejecuta eventos de cola, checa victoria/derrota.
        self._tick(dt)

        g = self.estado.grafo
        if g is None:
            return

        # ---- DIBUJO DE ARISTAS CON PAQUETES DE DATOS ANIMADOS ----
        t_anim = self._t_anim
        for u, adj in g.aristas.items():
            for v, info in adj.items():
                # u >= v: evita dibujar dos veces la misma arista
                # (recuerda: el grafo es no-dirigido).
                if u >= v:
                    continue
                nu, nv = g.nodos[u], g.nodos[v]
                color = c["arista"]
                ancho = 2
                animada = True
                # Si es muro intacto: roja y gruesa, sin animacion.
                if info["muro"] and not info["rota"]:
                    color = c["muro"]; ancho = 4; animada = False
                # Si fue muro pero ya esta rota: verde y normal.
                elif info["muro"] and info["rota"]:
                    color = c["exito"]; ancho = 2
                # aaline: linea con antialias (mas suave).
                pygame.draw.aaline(self.screen, color,
                                   (nu.x, nu.y), (nv.x, nv.y))
                # Si es gruesa (muro), pintamos otra linea encima para
                # ver el grosor (aaline solo da 1px).
                if ancho > 2:
                    pygame.draw.line(self.screen, color,
                                     (nu.x, nu.y), (nv.x, nv.y), ancho)
                # Paquetes viajando: solo si la arista esta "viva".
                if animada:
                    self._dibujar_paquetes_arista(nu, nv, color, t_anim, u + v)

        # ---- DIBUJO DE NODOS ----
        mouse = pygame.mouse.get_pos()
        nodo_hover = None
        for nodo in g.nodos.values():
            # Tamano base segun tipo. El nodo central es mas grande.
            radio_base = 30 if nodo.tipo == "central" else 24
            extra_pulso = 0.0

            # Pulso animado segun importancia/estado.
            if nodo.tipo == "central":
                # Central late lento y amplio: "corazon" de la red.
                extra_pulso = pulso(velocidad=1.6, amplitud=3.5)
            elif nodo.tipo == "bully" and nodo.estado != "resuelto":
                # Bullies pulsan rapido: amenaza activa.
                extra_pulso = pulso(velocidad=2.4, amplitud=2.5)
            elif nodo.estado == "infectado":
                # Infectados pulsan MUY rapido y siempre creciendo
                # (abs()): sensacion de fiebre.
                extra_pulso = abs(pulso(velocidad=4.0, amplitud=6.0))

            radio = int(radio_base + extra_pulso)

            # Glow neon detras del nodo segun su tipo/estado.
            color_glow = self._color_glow_nodo(nodo)
            if color_glow is not None:
                # Central tiene mas capas para verse mas brillante.
                capas = 5 if nodo.tipo == "central" else 4
                # Infectado tiene glow mas opaco para mayor alarma.
                alpha = 90 if nodo.estado == "infectado" else 70
                dibujar_glow(self.screen, int(nodo.x), int(nodo.y),
                             radio, color_glow, capas=capas, alpha_base=alpha)

            # Imagen del nodo (si existe) o fallback procedural.
            tam = radio * 2
            img = self.recursos.imagen_nodo(nodo.tipo, nodo.estado)
            if img:
                img_esc = self.recursos.escalar(
                    self._nombre_archivo_nodo(nodo), tam, tam)
                if img_esc is not None:
                    rect = img_esc.get_rect(center=(int(nodo.x), int(nodo.y)))
                    self.screen.blit(img_esc, rect)
                else:
                    self._dibujar_nodo_fallback(nodo, radio)
            else:
                self._dibujar_nodo_fallback(nodo, radio)

            # Indicador de "resuelto": punto verde arriba a la derecha.
            if nodo.estado == "resuelto":
                pygame.draw.circle(self.screen, c["exito"],
                                   (int(nodo.x + radio), int(nodo.y - radio)), 7)
                pygame.draw.circle(self.screen, c["fondo"],
                                   (int(nodo.x + radio), int(nodo.y - radio)), 7, 2)

            # Deteccion de hover por distancia (cuadrado al cuadrado
            # evita un sqrt costoso).
            if (nodo.x - mouse[0]) ** 2 + (nodo.y - mouse[1]) ** 2 < (radio + 6) ** 2:
                nodo_hover = nodo

        # ---- DIBUJO DE JUGADORES (avatares) ----
        # Los jugadores se dibujan ENCIMA de los nodos, con un offset
        # para que no se tapen (cuando varios estan en el mismo nodo).
        for jug in self.estado.jugadores:
            n = g.nodos.get(jug["pos"])
            if not n:
                continue
            # Offset basado en id_jugador para que se espacien.
            offset_x = (jug["id"] - 1.5) * 18
            offset_y = -34
            sk = settings.SKINS[jug["skin"] % len(settings.SKINS)]
            cx, cy = int(n.x + offset_x), int(n.y + offset_y)
            # Avatar pequeno (PNG) o fallback.
            avatar = self.recursos.avatar_skin(sk["nombre"])
            if avatar:
                avatar_esc = self.recursos.escalar(
                    f"nodo_{sk['nombre'].lower()}", 36, 36)
                if avatar_esc:
                    # Circulo del color del skin como fondo del avatar.
                    pygame.draw.circle(self.screen, sk["color"], (cx, cy), 20)
                    rect = avatar_esc.get_rect(center=(cx, cy))
                    self.screen.blit(avatar_esc, rect)
                    # Borde blanco para destacar.
                    pygame.draw.circle(self.screen, c["texto"], (cx, cy), 20, 2)
                else:
                    self._dibujar_jugador_fallback(cx, cy, sk, c)
            else:
                self._dibujar_jugador_fallback(cx, cy, sk, c)
            # Nombre del jugador debajo del avatar (truncado a 8 chars).
            self.ui.texto(jug["nombre"][:8], "xs", c["texto"],
                          cx, cy + 18, centrado=True, sombra=True)

        # ---- HUD (panel lateral derecho) ----
        self._dibujar_hud(nodo_hover)
        self._dibujar_mensajes_flotantes()
        # Tooltip al pasar el mouse sobre un nodo.
        if nodo_hover:
            self._dibujar_tooltip_nodo(nodo_hover, mouse)

        # ---- INPUT DEL MAPA ----
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._click_mapa(e.pos)
            if e.type == pygame.KEYDOWN:
                # ESC = pausa
                if e.key == pygame.K_ESCAPE:
                    self.audio.play("click")
                    self.pantalla = "pausa"
                # P = usar poder
                if e.key == pygame.K_p:
                    self._usar_poder()
                # R = reiniciar (solo en individual)
                if e.key == pygame.K_r and self.estado.modo == "individual":
                    self._iniciar_partida_local()

    # ---- HELPERS DE DIBUJO DE NODOS ----
    def _nombre_archivo_nodo(self, nodo):
        """Devuelve el nombre base del PNG segun estado/tipo del nodo.
        Estado tiene prioridad sobre tipo (infectado / resuelto > bully)."""
        if nodo.estado == "resuelto":
            return "nodo_resuelto"
        if nodo.estado == "infectado":
            return "nodo_infectado"
        return f"nodo_{nodo.tipo}"

    def _dibujar_nodo_fallback(self, nodo, radio):
        """Dibuja un nodo procedural cuando no hay imagen disponible:
        circulo de color con simbolo del tipo encima."""
        c = self.ui.col
        color = self._color_nodo(nodo)
        pygame.draw.circle(self.screen, color, (int(nodo.x), int(nodo.y)), radio)
        # Anillo oscuro como "marco" para separar del fondo.
        pygame.draw.circle(self.screen, c["fondo"],
                           (int(nodo.x), int(nodo.y)), radio, 3)
        # Simbolo unico por tipo (icono semantico ademas del color).
        simbolo = {"victima": "♥", "bully": "✖", "aliado": "+",
                   "neutro": "•", "central": "★"}.get(nodo.tipo, "")
        self.ui.texto(simbolo, "md", (20, 20, 30),
                      nodo.x, nodo.y - 12, centrado=True)

    def _dibujar_jugador_fallback(self, cx, cy, sk, c):
        """Avatar procedural cuando no hay PNG del skin: circulo +
        simbolo del skin."""
        pygame.draw.circle(self.screen, sk["color"], (cx, cy), 14)
        pygame.draw.circle(self.screen, c["texto"], (cx, cy), 14, 2)
        self.ui.texto(sk["simbolo"], "sm", (20, 20, 30),
                      cx, cy - 10, centrado=True)

    def _color_nodo(self, nodo):
        """Color RGB para dibujar el nodo segun tipo/estado."""
        c = self.ui.col
        if nodo.estado == "resuelto":
            return c["nodo_ok"]
        if nodo.estado == "infectado":
            return c["nodo_bully"]
        mapa = {
            "victima": c["nodo_victima"], "bully": c["nodo_bully"],
            "aliado":  c["nodo_ok"], "neutro": c["nodo_neutro"],
            "central": c["nodo_central"],
        }
        return mapa.get(nodo.tipo, c["nodo_neutro"])

    def _color_glow_nodo(self, nodo):
        """Color del halo/glow del nodo. None si no queremos halo
        (nodos neutros sin estado especial)."""
        c = self.ui.col
        if nodo.estado == "resuelto":
            return c["exito"]
        if nodo.estado == "infectado":
            return c["peligro"]
        if nodo.tipo == "central":
            return c["primario"]
        if nodo.tipo == "bully":
            return c["peligro"]
        if nodo.tipo == "victima":
            return c["alerta"]
        if nodo.tipo == "aliado":
            return c["exito"]
        return None

    def _dibujar_paquetes_arista(self, nu, nv, color, t, semilla):
        """Dibuja 1-2 puntitos viajando por la arista (paquetes de datos).

        Da sensacion de red activa. Usa una `semilla` (suma de IDs de
        los nodos) para que cada arista tenga su propia fase y no
        parezca todo sincronizado.
        """
        dx = nv.x - nu.x
        dy = nv.y - nu.y
        dist = math.hypot(dx, dy)
        # Aristas muy cortas: no dibujamos paquetes para no saturar.
        if dist < 30:
            return
        velocidad = 0.5
        # Fase inicial unica por arista basada en la semilla.
        fase = (semilla * 0.137) % 1.0
        # 2 paquetes desfasados 0.5 (uno en cada mitad del recorrido).
        for k in range(2):
            offset = (fase + k * 0.5 + t * velocidad) % 1.0
            px = nu.x + dx * offset
            py = nu.y + dy * offset
            # Cuerpo brillante + halo: el truco para que se vean "luminosos".
            s = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(s, (*color, 200), (5, 5), 3)
            pygame.draw.circle(s, (*color, 90), (5, 5), 5)
            # Blend aditivo: los paquetes se suman al fondo y brillan.
            self.screen.blit(s, (int(px - 5), int(py - 5)),
                             special_flags=pygame.BLEND_RGBA_ADD)

    def _dibujar_hud(self, nodo_hover):
        """Panel lateral derecho con info del jugador, poderes,
        cola de eventos y mensajes. Tambien muestra el minimapa."""
        c = self.ui.col
        rect = pygame.Rect(settings.WIDTH - 280, 10, 270, settings.HEIGHT - 20)
        self.ui.panel(rect, borde=c["primario"], alpha=210)
        self.ui.texto("HUD", "lg", c["primario"], rect.x + 20, rect.y + 12)

        # Info del jugador local (nombre, puntos).
        y = rect.y + 60
        jl = self.estado.jugadores[self.estado.jugador_local]
        self.ui.texto(f"Jugador: {jl['nombre']}", "sm", c["texto"], rect.x + 20, y); y += 22
        self.ui.texto(f"Puntos: {jl['puntos']}", "sm", c["texto"], rect.x + 20, y); y += 22
        self.ui.texto(f"Salud red: {self.estado.salud_comunidad}", "sm",
                      c["texto"], rect.x + 20, y); y += 28

        # Barra de salud comunitaria con color segun nivel.
        bar = pygame.Rect(rect.x + 20, y, 230, 12)
        pygame.draw.rect(self.screen, c["panel"], bar, border_radius=4)
        ratio = max(0, self.estado.salud_comunidad) / settings.SALUD_COMUNIDAD_INICIAL
        bar_in = pygame.Rect(bar.x, bar.y, int(bar.w * ratio), bar.h)
        # Verde > 50%, amarillo entre 25-50%, rojo < 25%.
        col_bar = c["exito"] if ratio > 0.5 else c["alerta"] if ratio > 0.25 else c["peligro"]
        pygame.draw.rect(self.screen, col_bar, bar_in, border_radius=4)
        y += 28

        # Lista de poderes con cargas disponibles.
        self.ui.texto("Poderes (P)", "md", c["primario"], rect.x + 20, y); y += 28
        for k, n in jl["poderes"].items():
            self.ui.texto(f"{self._nombre_poder(k)}: {n}", "sm", c["texto"],
                          rect.x + 20, y); y += 22

        y += 10
        # Cola de propagaciones pendientes (proximos 5 eventos).
        self.ui.texto("Cola del odio", "md", c["primario"], rect.x + 20, y); y += 28
        eventos = self.estado.cola_eventos.listar()[:5]
        if not eventos:
            self.ui.texto("(vacia)", "sm", c["texto_sec"], rect.x + 20, y); y += 22
        for p, dato in eventos:
            self.ui.texto(f"t+{p:.1f}s -> nodo {dato.get('nodo','?')}",
                          "xs", c["texto"], rect.x + 20, y); y += 18

        y += 10
        # Log de mensajes (ultimos 7).
        self.ui.texto("Mensajes", "md", c["primario"], rect.x + 20, y); y += 24
        for m in self.estado.mensaje_log[-7:]:
            # Truncamos a 34 chars para que quepa en el panel.
            self.ui.texto(m[:34], "xs", c["texto_sec"], rect.x + 20, y); y += 18

        # Minimapa abajo del HUD.
        mini_rect = pygame.Rect(rect.x + 20, settings.HEIGHT - 180, 230, 160)
        self.ui.panel(mini_rect, color=c["fondo2"], borde=c["primario"])
        self._dibujar_minimapa(mini_rect)

        # Chips arriba a la izquierda con info de modo + atajo de pausa.
        tipo_modo = {"individual": "Solo", "servidor": "Host", "cliente": "Cliente"}
        modo_txt = f"Modo: {tipo_modo.get(self.estado.modo,'?')}"
        chip = pygame.Rect(10, 10, 180, 36)
        self.ui.panel(chip, borde=c["primario"], alpha=180, radio=18)
        self.ui.texto(modo_txt, "sm", c["texto"], chip.x + 16, chip.y + 7)

        chip2 = pygame.Rect(10, 54, 180, 30)
        self.ui.panel(chip2, alpha=140, radio=15)
        self.ui.texto("ESC para pausar", "xs", c["texto_sec"],
                      chip2.x + 14, chip2.y + 7)

    def _dibujar_minimapa(self, mini_rect):
        """Dibuja el grafo entero en miniatura dentro del rect dado.
        Util para ver donde estan los nodos importantes y los jugadores."""
        g = self.estado.grafo
        if not g:
            return
        # Calculamos la bounding box de los nodos para mapear sus
        # coordenadas a las del mini_rect.
        xs = [n.x for n in g.nodos.values()]
        ys = [n.y for n in g.nodos.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = max(1, maxx - minx); h = max(1, maxy - miny); pad = 6

        def proy(n):
            """Proyecta coordenadas del mapa real al mini_rect."""
            x = mini_rect.x + pad + (n.x - minx) / w * (mini_rect.w - 2 * pad)
            y = mini_rect.y + pad + (n.y - miny) / h * (mini_rect.h - 2 * pad)
            return int(x), int(y)

        # Aristas como lineas finas.
        for u, adj in g.aristas.items():
            for v in adj:
                if u >= v:
                    continue
                pygame.draw.line(self.screen, self.ui.col["arista"],
                                 proy(g.nodos[u]), proy(g.nodos[v]), 1)
        # Nodos como puntitos del color del tipo.
        for nodo in g.nodos.values():
            pygame.draw.circle(self.screen, self._color_nodo(nodo), proy(nodo), 3)
        # Jugadores como puntos del color de su skin.
        for jug in self.estado.jugadores:
            n = g.nodos[jug["pos"]]
            sk = settings.SKINS[jug["skin"] % len(settings.SKINS)]
            pygame.draw.circle(self.screen, sk["color"], proy(n), 4)

    def _dibujar_tooltip_nodo(self, nodo, mouse):
        """Tooltip flotante cerca del mouse con info del nodo bajo el cursor."""
        c = self.ui.col
        info = [f"{nodo.nombre} ({nodo.tipo})", f"Estado: {nodo.estado}"]
        w = 200; h = 14 + 22 * len(info)
        # Evitar que el tooltip salga de la pantalla.
        x = min(mouse[0] + 12, settings.WIDTH - w - 10)
        y = min(mouse[1] + 12, settings.HEIGHT - h - 10)
        rect = pygame.Rect(x, y, w, h)
        self.ui.panel(rect, borde=c["primario"], alpha=220)
        for i, t in enumerate(info):
            self.ui.texto(t, "xs", c["texto"], x + 8, y + 6 + i * 18)

    def _dibujar_mensajes_flotantes(self):
        """Mensajes que aparecen abajo y se desvanecen en 3 segundos.

        Cada mensaje tiene tiempo de creacion; calculamos su alpha
        para que vaya desapareciendo gradualmente. Solo mostramos
        los 4 ultimos para no saturar la pantalla.
        """
        ahora = time.time()
        # Limpiamos los expirados.
        nuevos = []
        for txt, t0, col in self.estado.mensajes_flotantes:
            if ahora - t0 > 3.0:
                continue
            nuevos.append((txt, t0, col))
        self.estado.mensajes_flotantes = nuevos
        # Dibujamos los ultimos 4.
        for i, (txt, t0, col) in enumerate(self.estado.mensajes_flotantes[-4:]):
            # Alpha: 255 al inicio, 0 al final (lineal).
            alpha = max(0, 255 - int(((ahora - t0) / 3.0) * 255))
            color = col or self.ui.col["alerta"]
            f = self.ui.fuentes["md"]
            surf = f.render(txt, True, color)
            surf.set_alpha(alpha)
            self.screen.blit(surf, (40, settings.HEIGHT - 240 - i * 28))

    def _click_mapa(self, pos):
        """Procesa click en el mapa. Puede:
          - Abrir la situacion del nodo actual (si haces click en ti)
          - Mover al jugador al nodo vecino clickeado
          - Mostrar mensaje de "muro de odio" si el vecino esta bloqueado
        """
        g = self.estado.grafo
        if not g:
            return
        jl = self.estado.jugadores[self.estado.jugador_local]
        nodo_actual = g.nodos[jl["pos"]]
        # Buscamos sobre que nodo hicimos click (radio de hit = 30).
        for nodo in g.nodos.values():
            if (nodo.x - pos[0]) ** 2 + (nodo.y - pos[1]) ** 2 <= 30 * 30:
                # Click en MI nodo: abrir situacion (si la tiene).
                if nodo.id == nodo_actual.id:
                    self._abrir_situacion(nodo)
                    return
                # Click en un vecino: intentar moverse.
                if nodo.id in g.vecinos(nodo_actual.id):
                    # En multijugador, no podemos pisar un nodo que otro
                    # jugador ya esta ocupando. Damos feedback inmediato
                    # asi el usuario sabe por que no pasa nada.
                    if self.estado.modo in ("servidor", "cliente"):
                        mi_id = self.estado.jugadores[self.estado.jugador_local]["id"]
                        if any(j["pos"] == nodo.id and j["id"] != mi_id
                               for j in self.estado.jugadores):
                            self.audio.play("bloqueado")
                            self.estado.msg("Nodo ocupado por otro jugador.",
                                            self.ui.col["alerta"])
                            return
                    if g.arista_transitable(nodo_actual.id, nodo.id):
                        # Si somos cliente, mandamos la accion al server
                        # en vez de aplicarla nosotros (server es la fuente
                        # de verdad).
                        if self.estado.modo == "cliente":
                            self.cliente.enviar_accion("mover", {"destino": nodo.id})
                        else:
                            self._mover_jugador(self.estado.jugador_local, nodo.id)
                    else:
                        # Arista bloqueada: feedback al usuario.
                        self.audio.play("bloqueado")
                        self.estado.msg("Muro de odio: usa Voz Amplificada (P).",
                                        self.ui.col["peligro"])
                return

    # ===================== PANTALLA: PAUSA =====================
    def pantalla_pausa(self, eventos):
        """Menu de pausa: reanudar, accesibilidad, ayuda, salir.

        Detras del menu se ve el mapa congelado (sin animaciones),
        cubierto por un velo oscuro para enfatizar la pausa.
        """
        c = self.ui.col

        # Dibujamos el mapa al fondo (congelado, sin tick).
        self._dibujar_fondo("fondo_mapa")
        if self.estado.grafo:
            g = self.estado.grafo
            # Aristas simples (sin paquetes animados).
            for u, adj in g.aristas.items():
                for v, info in adj.items():
                    if u >= v:
                        continue
                    nu, nv = g.nodos[u], g.nodos[v]
                    color = c["arista"]
                    if info["muro"] and not info["rota"]:
                        color = c["muro"]
                    pygame.draw.line(self.screen, color,
                                     (nu.x, nu.y), (nv.x, nv.y), 2)
            # Nodos simples (sin glow ni pulso).
            for nodo in g.nodos.values():
                pygame.draw.circle(self.screen, self._color_nodo(nodo),
                                   (int(nodo.x), int(nodo.y)), 14)

        # Velo oscuro encima del mapa congelado.
        velo = pygame.Surface((settings.WIDTH, settings.HEIGHT),
                              pygame.SRCALPHA)
        velo.fill((0, 0, 0, 170))
        self.screen.blit(velo, (0, 0))

        # Panel central con las opciones.
        panel_w, panel_h = 520, 540
        panel = pygame.Rect((settings.WIDTH - panel_w) // 2,
                            (settings.HEIGHT - panel_h) // 2,
                            panel_w, panel_h)
        self.ui.panel(panel, color=c["fondo"], borde=c["primario"],
                      radio=18, alpha=240)

        self.ui.texto("Pausa", "xl", c["primario"],
                      panel.centerx, panel.y + 20, centrado=True)
        self.ui.texto("La partida esta en pausa.", "sm", c["texto_sec"],
                      panel.centerx, panel.y + 80, centrado=True)

        mouse = pygame.mouse.get_pos()
        bx = panel.x + 60
        bw = panel.w - 120
        by = panel.y + 120
        gap = 60

        # 1. Reanudar
        rect_resume = pygame.Rect(bx, by, bw, 50)
        self.ui.boton(rect_resume, "Reanudar partida",
                      hover=rect_resume.collidepoint(mouse), activo=True,
                      clave_imagen="boton_reanudar")

        # 2. Toggle paleta normal/daltonico
        rect_paleta = pygame.Rect(bx, by + gap, bw, 50)
        nombre_paleta = "Normal" if self.ui.paleta_clave == "normal" else "Daltonico"
        self.ui.boton(rect_paleta, f"Modo color: {nombre_paleta}",
                      hover=rect_paleta.collidepoint(mouse),
                      clave_imagen="boton_modo_color")

        # 3. Ciclar tamano de texto
        rect_texto = pygame.Rect(bx, by + gap * 2, bw, 50)
        nombre_tam = {"pequeno": "Pequeno", "mediano": "Mediano",
                      "grande": "Grande"}.get(self.ui.tam_fuente, "Mediano")
        self.ui.boton(rect_texto, f"Tamano texto: {nombre_tam}",
                      hover=rect_texto.collidepoint(mouse),
                      clave_imagen="boton_tam_text")

        # 4. Ayuda
        rect_ayuda = pygame.Rect(bx, by + gap * 3, bw, 50)
        self.ui.boton(rect_ayuda, "Ver ayuda / instrucciones",
                      hover=rect_ayuda.collidepoint(mouse),
                      clave_imagen="boton_ayuda")

        # 5. Salir al menu (cierra servidor/cliente)
        rect_salir = pygame.Rect(bx, by + gap * 4, bw, 50)
        self.ui.boton(rect_salir, "Salir al menu principal",
                      hover=rect_salir.collidepoint(mouse),
                      clave_imagen="boton_menu_principal")

        # 6. Salir del juego completo
        rect_quit = pygame.Rect(bx, by + gap * 5, bw, 50)
        self.ui.boton(rect_quit, "Salir del juego",
                      hover=rect_quit.collidepoint(mouse),
                      clave_imagen="boton_salir")

        # Pista al pie del panel.
        self.ui.texto("Pulsa ESC para reanudar", "xs", c["texto_sec"],
                      panel.centerx, panel.bottom - 30, centrado=True)

        # ---- INPUT ----
        for e in eventos:
            # ESC tambien reanuda (atajo del lobby).
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.audio.play("click")
                self.pantalla = "mapa"
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if rect_resume.collidepoint(e.pos):
                    self.audio.play("click")
                    self.pantalla = "mapa"
                elif rect_paleta.collidepoint(e.pos):
                    nueva = "daltonico" if self.ui.paleta_clave == "normal" else "normal"
                    self.ui.cambiar_paleta(nueva)
                    self.audio.play("click")
                elif rect_texto.collidepoint(e.pos):
                    actuales = list(settings.TAMANOS_FUENTE.keys())
                    i = (actuales.index(self.ui.tam_fuente) + 1) % len(actuales)
                    self.ui.cambiar_tam_fuente(actuales[i])
                    self.audio.play("click")
                elif rect_ayuda.collidepoint(e.pos):
                    self.audio.play("click")
                    self.pantalla_anterior = "pausa"
                    self.pantalla = "ayuda"
                elif rect_salir.collidepoint(e.pos):
                    self.audio.play("click")
                    # Cerramos cualquier conexion antes de volver al menu.
                    if self.servidor:
                        try: self.servidor.detener()
                        except Exception: pass
                        self.servidor = None
                    if self.cliente:
                        try: self.cliente.desconectar()
                        except Exception: pass
                        self.cliente = None
                    self.pantalla = "menu"
                elif rect_quit.collidepoint(e.pos):
                    self.salir()

    # ===================== PANTALLA: EVENTO (decision) =====================
    def pantalla_evento(self, eventos):
        """Pantalla del arbol de decisiones cuando entras a un nodo
        con conflicto. Muestra el texto de la situacion y las opciones."""
        c = self.ui.col
        # Si existe un fondo especifico de evento, lo usamos; sino menu.
        self._dibujar_fondo("fondo_evento" if self.recursos.cargar("fondo_evento") else "fondo_menu")
        nodo = self.nodo_evento_actual
        if nodo is None:
            self.pantalla = "mapa"; return
        arbol = self.estado.situaciones.get(nodo.id)
        if not arbol:
            self.pantalla = "mapa"; return

        # Panel grande para el dialogo.
        panel = pygame.Rect(80, 60, settings.WIDTH - 160, settings.HEIGHT - 120)
        self.ui.panel(panel, borde=c["primario"], radio=18, alpha=230)

        # Imagen del nodo a la izquierda (mas grande, 140x140).
        img_nodo = self.recursos.imagen_nodo(nodo.tipo, nodo.estado)
        if img_nodo:
            img_esc = pygame.transform.smoothscale(img_nodo, (140, 140))
            self.screen.blit(img_esc, (panel.x + 30, panel.y + 30))
            x_texto = panel.x + 200
        else:
            x_texto = panel.x + 30

        # Titulo y descripcion del nodo actual del arbol.
        self.ui.texto(f"Nodo {nodo.nombre} ({nodo.tipo})", "lg",
                      c["primario"], x_texto, panel.y + 30)
        self.ui.texto(arbol.actual.texto, "md", c["texto"],
                      x_texto, panel.y + 90)

        # ---- SI YA LLEGAMOS A UNA HOJA (final del arbol) ----
        if arbol.actual.es_hoja():
            tipo = arbol.actual.tipo_resultado
            # Color y mensaje segun resultado.
            col = {"bueno": c["exito"], "neutro": c["alerta"],
                   "malo": c["peligro"]}.get(tipo, c["texto"])
            self.ui.texto(
                {"bueno": "Excelente decision",
                 "neutro": "Decision aceptable",
                 "malo":  "Consecuencias negativas"}[tipo],
                "lg", col, x_texto, panel.y + 260)

            # Boton de continuar: aplica el efecto y vuelve al mapa.
            rect_cont = pygame.Rect(panel.right - 250, panel.bottom - 80, 220, 50)
            mouse = pygame.mouse.get_pos()
            self.ui.boton(rect_cont, "Continuar",
                          hover=rect_cont.collidepoint(mouse), activo=True,
                          clave_imagen="boton_continuar")
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_cont.collidepoint(e.pos):
                    # _finalizar_decision aplica localmente si soy host/solo,
                    # o envia accion "decidir" al servidor si soy cliente.
                    self.audio.play("nivel" if tipo == "bueno" else "fallo")
                    self._finalizar_decision(nodo, arbol)
                if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                    self._finalizar_decision(nodo, arbol)
            return

        # ---- SI HAY OPCIONES (rama intermedia) ----
        y = panel.y + 320
        mouse = pygame.mouse.get_pos()
        for i, (texto_op, _h, _ef) in enumerate(arbol.actual.opciones):
            rect = pygame.Rect(panel.x + 30, y + i * 70, panel.w - 60, 56)
            hover = rect.collidepoint(mouse)
            # Numeramos las opciones (1. 2. 3.) por accesibilidad
            # — se pueden elegir con teclas 1/2/3 tambien.
            self.ui.boton(rect, f"{i+1}. {texto_op}", hover=hover)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect.collidepoint(e.pos):
                    # Trackear el indice elegido para la ruta de decision.
                    # En multijugador, esto se envia al servidor cuando
                    # llegamos a la hoja final.
                    self.ruta_decision.append(i)
                    arbol.elegir(i); self.audio.play("click")
                # Teclas numericas para elegir opciones rapidamente.
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    idx = e.key - pygame.K_1
                    if idx < len(arbol.actual.opciones):
                        self.ruta_decision.append(idx)
                        arbol.elegir(idx); self.audio.play("click")

        # Boton de salir (escape sin tomar decision).
        rect_back = pygame.Rect(panel.x + 30, panel.bottom - 70, 180, 46)
        self.ui.boton(rect_back, "Salir", hover=rect_back.collidepoint(mouse),
                      clave_imagen="boton_volver")
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_back.collidepoint(e.pos):
                self.pantalla = "mapa"

    # ===================== PANTALLA: FIN =====================
    def pantalla_fin(self, eventos):
        """Pantalla final con estadisticas y opcion de jugar otra vez."""
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        titulo = "Victoria!" if self.estado.victoria else "Fin de la partida"
        col = c["exito"] if self.estado.victoria else c["peligro"]
        self.ui.texto(titulo, "xl", col, settings.WIDTH // 2, 70,
                      centrado=True, sombra=True)

        # Estadisticas finales.
        n_res = sum(1 for n in self.estado.grafo.nodos.values() if n.estado == "resuelto")
        n_inf = sum(1 for n in self.estado.grafo.nodos.values() if n.estado == "infectado")
        tiempo = int(self.estado.tiempo_actual - self.estado.tiempo_inicio)
        lineas = [
            f"Tiempo jugado: {tiempo} s",
            f"Salud final de la red: {self.estado.salud_comunidad}",
            f"Nodos resueltos: {n_res}/{len(self.estado.grafo.nodos)}",
            f"Nodos infectados: {n_inf}",
        ]
        # Puntos por jugador.
        for jug in self.estado.jugadores:
            lineas.append(f"Jugador {jug['nombre']}: {jug['puntos']} pts")
        for i, t in enumerate(lineas):
            self.ui.texto(t, "md", c["texto"], settings.WIDTH // 2,
                          180 + i * 36, centrado=True, sombra=True)

        # Mensaje moral segun resultado.
        mensaje = ("Ayudaste a construir empatia. Tu red es mas fuerte."
                   if self.estado.victoria else
                   "El odio se propago. La empatia gana cuando actuamos a tiempo.")
        self.ui.texto(mensaje, "md", c["primario"], settings.WIDTH // 2,
                      settings.HEIGHT - 180, centrado=True, sombra=True)

        # Botones de reiniciar o volver al menu.
        rect_re = pygame.Rect(settings.WIDTH // 2 - 220, settings.HEIGHT - 110, 200, 56)
        rect_menu = pygame.Rect(settings.WIDTH // 2 + 20, settings.HEIGHT - 110, 200, 56)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_re, "Jugar otra vez",
                      hover=rect_re.collidepoint(mouse), activo=True,
                      clave_imagen="boton_jugar_otra")
        self.ui.boton(rect_menu, "Menu principal",
                      hover=rect_menu.collidepoint(mouse),
                      clave_imagen="boton_menu_principal")
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if rect_re.collidepoint(e.pos):
                    self.audio.play("click"); self._iniciar_partida_local()
                elif rect_menu.collidepoint(e.pos):
                    self.audio.play("click"); self.pantalla = "menu"

    # ===================== LOGICA DE PARTIDA =====================
    def _iniciar_partida_local(self):
        """Crea una partida nueva en modo individual:
          1) Genera un grafo aleatorio
          2) Asigna situaciones a los nodos relevantes
          3) Crea el jugador local
          4) Programa los eventos iniciales (propagaciones)
          5) Cambia a la pantalla de mapa con fade-in
        """
        n = random.randint(settings.NUM_NODOS_MIN, settings.NUM_NODOS_MAX)
        # Reservamos espacio para el HUD (-300 ancho) y un margen abajo.
        ancho_juego = settings.WIDTH - 300
        alto_juego = settings.HEIGHT - 40
        g = Grafo.aleatorio(n, settings.PROB_ARISTA, settings.PROB_MURO,
                            ancho_juego, alto_juego,
                            settings.PROB_BULLY, settings.PROB_VICTIMA)
        # Estado fresco para esta partida.
        self.estado = EstadoJuego()
        self.estado.grafo = g
        # Asignamos situaciones a todos los nodos no-neutros, y a
        # algunos neutros (30%) para que no estemos seguros de que
        # no tienen nada.
        for nodo in g.nodos.values():
            if nodo.tipo != "neutro" or random.random() < 0.3:
                self.estado.situaciones[nodo.id] = crear_situacion(
                    nodo.tipo, nodo.nombre)
        # Creamos el jugador local (id=0).
        partida_color = settings.SKINS[self.skin_idx]["color"]
        self.estado.jugadores = [{
            "id": 0, "nombre": self.nombre_jugador, "skin": self.skin_idx,
            "pos": 0, "puntos": 0,
            # dict() crea una COPIA del dict; sin esto, todos los
            # jugadores compartirian la misma referencia a poderes.
            "poderes": dict(settings.PODERES_INICIALES),
            "color": partida_color,
            # es_host=True: bandera para que sync no nos elimine si
            # un cliente se desconecta (ver _sincronizar_jugadores_conectados).
            "es_host": True,
        }]
        self.estado.jugador_local = 0
        self.estado.tiempo_inicio = time.time()
        self.estado.tiempo_actual = time.time()
        self._programar_eventos_iniciales()
        self.pantalla = "mapa"
        self.transicion.fade_in()
        self.audio.play("nivel")
        self.estado.msg("Bienvenido, Guardian!", self.ui.col["primario"])

    def _iniciar_host(self):
        """Arranca el servidor TCP y va a la pantalla de lobby host."""
        if self.servidor:
            self.servidor.detener()
        self.servidor = Servidor(settings.HOST_DEFAULT, settings.PORT_DEFAULT)
        try:
            self.servidor.iniciar()
            self.pantalla = "lobby_host"
        except OSError as e:
            # Puerto ocupado, falta permisos, etc.
            self.estado.msg(f"No se pudo iniciar el servidor: {e}",
                            self.ui.col["peligro"])

    def _conectar_cliente(self):
        """Conecta al servidor con la IP que escribio el usuario.

        Acepta formato "192.168.1.12" o "192.168.1.12:50007".
        Si la conexion falla, muestra un mensaje rojo al usuario.
        """
        if self.cliente:
            self.cliente.desconectar()
        # Permite "192.168.1.12" o "192.168.1.12:50007".
        host = self.config_host.strip()
        puerto = self.config_port
        if ":" in host:
            # Separamos host y puerto.
            host, _, puerto_txt = host.partition(":")
            host = host.strip()
            try:
                puerto = int(puerto_txt.strip())
            except ValueError:
                # Puerto invalido: caemos al default.
                puerto = self.config_port
        self.cliente = Cliente(host, puerto,
                            self.nombre_jugador, self.skin_idx)
        ok = self.cliente.conectar()
        if not ok:
            self.estado.msg("Error de conexion", self.ui.col["peligro"])

    def _sincronizar_jugadores_conectados(self):
        """Elimina de la lista de jugadores a los que ya no estan en el servidor.

        ATENCION: El host siempre se preserva (bandera es_host=True).
        Sin esto, el host se eliminaba a si mismo porque el host NO
        aparece en self.servidor.jugadores() (esa lista es solo de
        clientes conectados, no incluye al host).

        Es uno de los bugs mas raros que tuvo el juego en multijugador.
        """
        if not self.servidor:
            return
        # IDs activos del servidor + 1 (offset para no chocar con host id=0)
        ids_activos = {jid + 1 for jid, _, _ in self.servidor.jugadores()}
        antes = len(self.estado.jugadores)
        # Conservamos: el host (es_host=True) o cualquier cliente activo.
        self.estado.jugadores = [
            j for j in self.estado.jugadores
            if j.get("es_host") or j["id"] in ids_activos
        ]
        # Si alguien se fue, notificar y resincronizar a los demas.
        if len(self.estado.jugadores) < antes:
            self.estado.msg("Un jugador se desconecto", self.ui.col["texto"])
            self._difundir_estado()

    def _iniciar_partida_multijugador(self):
        """Inicia partida en modo host: primero crea la partida local
        (reutilizamos esa logica), luego anade los clientes ya conectados
        a la lista de jugadores y difunde el estado inicial."""
        self._iniciar_partida_local()
        self.estado.modo = "servidor"
        # Anadimos un jugador por cada cliente conectado al servidor.
        for jid, nombre, skin in self.servidor.jugadores():
            self.estado.jugadores.append({
                "id": jid + 1,  # offset para no chocar con host id=0
                "nombre": nombre, "skin": skin, "pos": 0, "puntos": 0,
                "poderes": dict(settings.PODERES_INICIALES),
                "color": settings.SKINS[skin]["color"],
                "es_host": False,
            })
        # Mandamos el primer ESTADO a todos: esto hace que los
        # clientes salten al mapa.
        self._difundir_estado()
        self.audio.play("nivel")

    def _programar_eventos_iniciales(self):
        """Cada bully tiene programada una propagacion inicial entre
        20 y 60 segundos despues del inicio. Esto va llenando la
        cola de prioridad."""
        bullies = [n for n in self.estado.grafo.nodos.values() if n.tipo == "bully"]
        for b in bullies:
            tiempo = random.uniform(20, 60)
            self.estado.cola_eventos.push(tiempo, {"tipo": "propagar", "nodo": b.id})

    def _tick(self, dt):
        """Avanza el tiempo del juego un frame.

        Se ejecuta cada frame mientras estamos en el mapa. Sus
        responsabilidades:
          1) Acumular tiempo real
          2) Ejecutar eventos vencidos de la cola de prioridad
          3) Chequear condicion de derrota (salud <= 0)
          4) Chequear condicion de victoria (70% resueltos sin central infectado)
        """
        if self.estado.fin:
            return
        self.estado.tiempo_actual += dt
        elapsed = self.estado.tiempo_actual - self.estado.tiempo_inicio
        # Ejecutamos todos los eventos cuyo tiempo ya paso.
        while not self.estado.cola_eventos.vacia():
            prox = self.estado.cola_eventos.peek()
            if prox is None:
                break
            p, dato = prox
            if elapsed >= p:
                self.estado.cola_eventos.pop()
                self._ejecutar_evento(dato)
            else:
                # El siguiente evento todavia no toca: salimos.
                break

        # ---- CONDICIONES DE FIN DE PARTIDA ----
        if self.estado.salud_comunidad <= 0:
            # Derrota: la comunidad colapso.
            self.estado.fin = True; self.estado.victoria = False
            self.audio.play("fallo"); self.pantalla = "fin"
            self.transicion.fade_in(); return

        # Victoria: 70%+ de los nodos resueltos Y el central no infectado.
        nodos = list(self.estado.grafo.nodos.values())
        resueltos = sum(1 for n in nodos if n.estado == "resuelto")
        central = self.estado.grafo.nodos[0]
        if resueltos >= max(1, int(len(nodos) * 0.7)) and central.estado != "infectado":
            self.estado.fin = True; self.estado.victoria = True
            self.audio.play("nivel"); self.pantalla = "fin"
            self.transicion.fade_in()

    def _ejecutar_evento(self, dato):
        """Aplica un evento extraido de la cola de prioridad.

        Por ahora solo soportamos eventos de tipo "propagar": un bully
        contagia el odio a un vecino con 40% de probabilidad. Si lo
        contagia, el vecino se vuelve victima/infectado, baja la salud
        global, dispara particulas rojas, y programa otra propagacion
        15-30s despues (efecto cascada).
        """
        if dato["tipo"] == "propagar":
            nodo = self.estado.grafo.nodos.get(dato["nodo"])
            if nodo is None or nodo.estado == "resuelto":
                return
            for v in self.estado.grafo.vecinos(nodo.id):
                vn = self.estado.grafo.nodos[v]
                if vn.estado == "resuelto":
                    continue
                if random.random() < 0.4:
                    # Convertimos en victima (excepto bullies y central).
                    if vn.tipo not in ("bully", "central"):
                        vn.tipo = "victima"
                        # Si no tenia situacion, le creamos una nueva.
                        if v not in self.estado.situaciones:
                            self.estado.situaciones[v] = crear_situacion("victima", vn.nombre)
                    vn.estado = "infectado"
                    self.estado.salud_comunidad -= 5
                    self.estado.msg(f"El odio se propago a {vn.nombre}",
                                    self.ui.col["peligro"])
                    self.audio.play("evento")
                    # Burst de particulas rojas en el nodo infectado.
                    self.particulas.burst(vn.x, vn.y,
                                          self.ui.col["peligro"],
                                          cantidad=22, velocidad=140,
                                          vida=0.9, tam=3)
                    # Programamos otra propagacion en cadena.
                    self.estado.cola_eventos.push(
                        (self.estado.tiempo_actual - self.estado.tiempo_inicio) + random.uniform(15, 30),
                        {"tipo": "propagar", "nodo": v})

    def _mover_jugador(self, id_jug, destino):
        """Mueve a un jugador al nodo destino si la arista es transitable.

        Si el destino tiene una situacion no resuelta y soy el jugador
        local, abrimos la pantalla de evento (decision).

        Despues del movimiento, difundimos el estado para que clientes
        se enteren.
        """
        g = self.estado.grafo
        jl = self.estado.jugadores[id_jug]
        # En multijugador, rechazar el movimiento si otro jugador ya esta
        # en ese nodo. El servidor es la autoridad: aunque el cliente
        # tambien valida antes de mandar, podria llegar una accion vieja
        # cuando ya alguien ocupo el nodo. Rechazarla aqui evita teleports
        # accidentales y conflictos visuales.
        if self.estado.modo in ("servidor", "cliente"):
            for i, otro in enumerate(self.estado.jugadores):
                if i != id_jug and otro["pos"] == destino:
                    # Notificar al jugador que intento moverse.
                    if id_jug == self.estado.jugador_local:
                        self.audio.play("bloqueado")
                        self.estado.msg("Nodo ocupado por otro jugador.",
                                        self.ui.col["alerta"])
                    return
        if destino in g.vecinos(jl["pos"]) and g.arista_transitable(jl["pos"], destino):
            jl["pos"] = destino
            self.audio.play("mover")
            self.estado.msg(f"{jl['nombre']} -> {g.nodos[destino].nombre}")
            nodo = g.nodos[destino]
            # Solo abrimos situacion si SOMOS el jugador que se movio
            # (no abrirla cuando se mueve otro jugador en multi).
            if (id_jug == self.estado.jugador_local
                    and nodo.estado != "resuelto"
                    and nodo.id in self.estado.situaciones):
                self._abrir_situacion(nodo)
            self._difundir_estado()

    def _abrir_situacion(self, nodo):
        """Reinicia el arbol de la situacion y va a la pantalla evento."""
        arbol = self.estado.situaciones.get(nodo.id)
        if arbol is None or nodo.estado == "resuelto":
            return
        # reiniciar() vuelve al nodo raiz del arbol (por si el jugador
        # ya habia avanzado en este arbol antes).
        arbol.reiniciar()
        # Limpiamos la ruta de decision para empezar a registrar de cero.
        # Importante para multijugador: la ruta es lo que enviamos al
        # servidor cuando llegamos a una hoja.
        self.ruta_decision = []
        self.nodo_evento_actual = nodo
        self.pantalla = "evento"

    def _finalizar_decision(self, nodo, arbol):
        """Cierra la pantalla de evento.

        Si soy CLIENTE, no aplico el efecto localmente: envio la ruta
        de indices al servidor con la accion "decidir" y dejo que el
        servidor aplique el efecto al jugador correspondiente (yo) y
        difunda el nuevo estado a todos. Asi el invitado puede tomar
        decisiones reales en multijugador.

        Si soy HOST o SOLO, aplico el efecto localmente como siempre.
        """
        if self.estado.modo == "cliente" and self.cliente is not None:
            # Cliente: enviar la ruta tomada al servidor. El server tiene
            # los mismos arboles y puede replayear la ruta para aplicar
            # el efecto correcto.
            self.cliente.enviar_accion("decidir", {
                "nodo": nodo.id,
                "ruta": list(self.ruta_decision),
            })
        else:
            # Host o solo: aplicar localmente.
            self._aplicar_efecto_hoja(nodo, arbol.actual)
        self.ruta_decision = []
        self.pantalla = "mapa"

    def _aplicar_efecto_hoja(self, nodo, hoja, id_jugador=None):
        """Aplica los efectos numericos (puntos, salud, resolver, poder)
        de una hoja del arbol de decisiones al estado del juego.

        Esto se llama cuando el jugador hace click en "Continuar" tras
        llegar a una hoja del arbol.

        id_jugador: indice del jugador en self.estado.jugadores al que
        aplicar los puntos/poderes. Por defecto el jugador_local (host
        o solo). En multijugador, el server llama esto pasando el id
        del cliente que tomo la decision.
        """
        if id_jugador is None:
            id_jugador = self.estado.jugador_local
        jl = self.estado.jugadores[id_jugador]
        ef = hoja.efecto or {}
        pts = ef.get("puntos", 0)
        salud = ef.get("salud", 0)
        jl["puntos"] += pts
        # Cap superior: salud no puede pasar de SALUD_INICIAL + 50.
        # Cap inferior: salud no puede bajar de 0.
        self.estado.salud_comunidad = max(0, min(settings.SALUD_COMUNIDAD_INICIAL + 50,
                                                 self.estado.salud_comunidad + salud))
        if ef.get("resolver"):
            nodo.estado = "resuelto"
            # Los bullies resueltos se convierten en aliados (redencion).
            if nodo.tipo == "bully":
                nodo.tipo = "aliado"
            self.estado.msg(f"{nodo.nombre} resuelto (+{pts})", self.ui.col["exito"])
            # Burst de particulas verdes para celebrar.
            self.particulas.burst(nodo.x, nodo.y,
                                  self.ui.col["exito"],
                                  cantidad=26, velocidad=160,
                                  vida=1.0, tam=3)
        else:
            self.estado.msg(f"Resultado: {pts:+d} pts, salud {salud:+d}",
                            self.ui.col["alerta"])
        # Si la hoja da un poder, lo sumamos al inventario.
        if ef.get("poder"):
            poder = ef["poder"]
            jl["poderes"][poder] = jl["poderes"].get(poder, 0) + 1
            self.estado.msg(f"Obtienes: {self._nombre_poder(poder)}!", self.ui.col["primario"])
            self.audio.play("poder")
        self._difundir_estado()

    def _nombre_poder(self, k):
        """Convierte la clave interna del poder a un nombre humano."""
        return {
            "escudo_empatia":  "Escudo de Empatia",
            "red_apoyo":       "Red de Apoyo",
            "voz_amplificada": "Voz Amplificada",
        }.get(k, k)

    def _usar_poder(self):
        """Activa el poder mas relevante segun el contexto actual.

        La logica es: chequeamos en orden de prioridad cada poder.
        El primero aplicable se usa. Si ninguno aplica, sonido de bloqueado.

        Prioridades:
          1) Voz Amplificada: si hay muro adyacente, romperlo
          2) Escudo de Empatia: si estoy en una victima activa, protegerla
          3) Red de Apoyo: si tengo 2+ vecinos no conectados entre si,
                           crear una arista nueva entre ellos
        """
        jl = self.estado.jugadores[self.estado.jugador_local]
        g = self.estado.grafo
        pos = jl["pos"]
        # 1) Buscar muros adyacentes que romper.
        muros = [v for v in g.vecinos(pos)
                 if g.aristas[pos][v]["muro"] and not g.aristas[pos][v]["rota"]]
        if muros and jl["poderes"].get("voz_amplificada", 0) > 0:
            g.romper_muro(pos, muros[0])
            jl["poderes"]["voz_amplificada"] -= 1
            self.estado.msg("Muro roto con Voz Amplificada!", self.ui.col["exito"])
            self.audio.play("poder"); self._difundir_estado(); return
        # 2) Escudo si estoy en una victima no resuelta.
        nodo = g.nodos[pos]
        if nodo.tipo == "victima" and nodo.estado != "resuelto" and jl["poderes"].get("escudo_empatia", 0) > 0:
            nodo.estado = "resuelto"
            jl["poderes"]["escudo_empatia"] -= 1
            jl["puntos"] += 10
            self.estado.msg("Escudo de Empatia: victima protegida", self.ui.col["exito"])
            self.particulas.burst(nodo.x, nodo.y, self.ui.col["exito"],
                                  cantidad=24, velocidad=150, vida=1.0)
            self.audio.play("poder"); self._difundir_estado(); return
        # 3) Red de Apoyo: conectar dos vecinos no conectados entre si.
        if jl["poderes"].get("red_apoyo", 0) > 0 and len(g.vecinos(pos)) >= 2:
            v1, v2 = g.vecinos(pos)[:2]
            if v2 not in g.vecinos(v1):
                g.agregar_arista(v1, v2)
                jl["poderes"]["red_apoyo"] -= 1
                self.estado.msg("Red de Apoyo: nueva conexion creada", self.ui.col["primario"])
                self.audio.play("poder"); self._difundir_estado(); return
        # Nada aplicable.
        self.estado.msg("Sin poder aplicable aqui.", self.ui.col["alerta"])
        self.audio.play("bloqueado")

    # ===================== RED (servidor y cliente) =====================
    def _procesar_acciones_servidor(self):
        """En modo servidor, procesamos las acciones que mandaron los
        clientes desde la ultima vez. Solo soportamos "mover" por ahora."""
        if not self.servidor:
            return
        for accion in self.servidor.acciones_pendientes:
            id_j = accion["id_jugador"]
            ac = accion.get("accion")
            datos = accion.get("datos", {})
            # IDs del cliente + 1 para alinear con nuestra lista (host es 0).
            idx = id_j + 1
            if idx >= len(self.estado.jugadores):
                continue
            if ac == "mover":
                self._mover_jugador(idx, int(datos.get("destino", 0)))
            elif ac == "decidir":
                # Cliente eligio una opcion final en su arbol de decision.
                # Replayeamos la ruta sobre nuestro propio arbol del nodo
                # y aplicamos el efecto al jugador correspondiente.
                nodo_id = int(datos.get("nodo", -1))
                ruta = datos.get("ruta", []) or []
                if (nodo_id in self.estado.situaciones
                        and nodo_id in self.estado.grafo.nodos):
                    arbol = self.estado.situaciones[nodo_id]
                    arbol.reiniciar()
                    # Avanzamos por la misma ruta de indices que tomo el
                    # cliente. Si la ruta es invalida (indices fuera de
                    # rango), elegir() devuelve sin hacer nada.
                    for i in ruta:
                        try:
                            arbol.elegir(int(i))
                        except (ValueError, TypeError):
                            break
                    # Solo aplicamos efecto si efectivamente llegamos a
                    # una hoja (sino el cliente envio una ruta incompleta).
                    if arbol.actual.es_hoja():
                        nodo = self.estado.grafo.nodos[nodo_id]
                        self._aplicar_efecto_hoja(nodo, arbol.actual,
                                                  id_jugador=idx)
        # Vaciamos la cola para no procesar dos veces.
        self.servidor.acciones_pendientes.clear()

    def _difundir_estado(self):
        """Manda el snapshot del estado a todos los clientes."""
        if not self.servidor:
            return
        self.servidor.difundir_estado(self._snapshot_estado())

    def _snapshot_estado(self):
        """Serializa el estado del juego en un dict JSON-compatible.

        Solo incluye lo que los clientes necesitan saber para dibujar
        y entender el juego (no enviamos cosas como las situaciones
        completas porque pesan mucho y el cliente no necesita el arbol
        - el servidor maneja las decisiones).
        """
        g = self.estado.grafo
        return {
            "salud": self.estado.salud_comunidad,
            "nodos": [
                {"id": n.id, "tipo": n.tipo, "estado": n.estado,
                 "x": n.x, "y": n.y, "nombre": n.nombre}
                for n in g.nodos.values()
            ],
            # Aristas como tuplas [u, v, muro, rota]. Solo enviamos una
            # direccion (u < v) ya que es no-dirigido y el cliente
            # reconstruye ambos sentidos.
            "aristas": [
                [u, v, info["muro"], info["rota"]]
                for u, adj in g.aristas.items() for v, info in adj.items()
                if u < v
            ],
            "jugadores": [
                {"id": j["id"], "nombre": j["nombre"], "skin": j["skin"],
                 "pos": j["pos"], "puntos": j["puntos"]}
                for j in self.estado.jugadores
            ],
            # IMPORTANTE para multijugador: enviamos los arboles de
            # decision serializados para que los clientes puedan abrir
            # situaciones y elegir opciones. Sin esto, los invitados
            # nunca podrian "salvar" a nadie.
            "situaciones": _serializar_situaciones(self.estado.situaciones),
            "fin": self.estado.fin, "victoria": self.estado.victoria,
        }

    def _sincronizar_desde_servidor(self):
        """En modo cliente, leemos el snapshot del servidor y
        reconstruimos nuestro estado local.

        Esto se llama cada vez que recibimos un ESTADO del servidor.
        Es una sincronizacion completa (no incremental) - simple y robusta.
        """
        s = self.cliente.estado_juego
        if not s:
            return
        # Si no teniamos grafo, lo creamos.
        if self.estado.grafo is None:
            self.estado.grafo = Grafo()
        g = self.estado.grafo
        # Aplicar nodos: anadimos los nuevos y actualizamos los existentes.
        for n in s["nodos"]:
            if n["id"] not in g.nodos:
                g.agregar_nodo(Nodo(n["id"], n["tipo"], n["x"], n["y"], n["nombre"]))
            nodo = g.nodos[n["id"]]
            nodo.tipo = n["tipo"]; nodo.estado = n["estado"]
            nodo.x = n["x"]; nodo.y = n["y"]; nodo.nombre = n["nombre"]
        # Aristas: reconstruimos desde cero para reflejar muros rotos.
        g.aristas = {nid: {} for nid in g.nodos}
        for u, v, muro, rota in s["aristas"]:
            g.aristas.setdefault(u, {})[v] = {"muro": muro, "rota": rota}
            g.aristas.setdefault(v, {})[u] = {"muro": muro, "rota": rota}
        # Jugadores: lista completa nueva.
        self.estado.jugadores = []
        for j in s["jugadores"]:
            self.estado.jugadores.append({
                "id": j["id"], "nombre": j["nombre"], "skin": j["skin"],
                "pos": j["pos"], "puntos": j["puntos"],
                "poderes": dict(settings.PODERES_INICIALES),
                "color": settings.SKINS[j["skin"] % len(settings.SKINS)]["color"],
            })
        # Identificamos cual jugador soy yo (segun mi id_cliente +1).
        if self.cliente.id_jugador is not None:
            self.estado.jugador_local = self.cliente.id_jugador + 1
            if self.estado.jugador_local >= len(self.estado.jugadores):
                self.estado.jugador_local = 0
        self.estado.salud_comunidad = s["salud"]
        # Deserializar las situaciones que el servidor nos envio. Asi
        # podemos abrir nuestra propia pantalla de evento cuando caigamos
        # en un nodo con conflicto.
        sit_data = s.get("situaciones", {})
        if sit_data:
            self.estado.situaciones = _deserializar_situaciones(sit_data)
        # Auto-abrir situacion si acabamos de cambiar de posicion y
        # estamos parados sobre un nodo con conflicto no resuelto. Sin
        # esto, el invitado se quedaria en el mapa sin saber que tiene
        # que hacer click otra vez en su propio nodo.
        try:
            mi_idx = self.estado.jugador_local
            if 0 <= mi_idx < len(self.estado.jugadores):
                mi_pos = self.estado.jugadores[mi_idx]["pos"]
                if (mi_pos != self._pos_jugador_anterior
                        and self.pantalla == "mapa"
                        and mi_pos in self.estado.grafo.nodos):
                    nodo_actual = self.estado.grafo.nodos[mi_pos]
                    if (nodo_actual.estado != "resuelto"
                            and mi_pos in self.estado.situaciones):
                        self._abrir_situacion(nodo_actual)
                self._pos_jugador_anterior = mi_pos
        except (KeyError, AttributeError):
            # Si algo sale mal en el auto-open, no es critico: el
            # cliente puede hacer click en su nodo para abrir manualmente.
            pass
        # Si el servidor marca fin de partida, vamos a la pantalla de fin.
        if s.get("fin"):
            self.estado.fin = True
            self.estado.victoria = s.get("victoria", False)
            self.pantalla = "fin"
