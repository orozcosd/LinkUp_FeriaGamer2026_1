"""
LinkUp - Guardianes del Nexo
Lógica principal y pantallas pygame, con soporte de imágenes desde assets/.
"""

import math
import random
import sys
import time

import pygame

import settings
from estructuras import Grafo, ArbolDecisiones, ColaPrioridad, Nodo
from situaciones import crear_situacion, nombre_aleatorio
from audio import GestorAudio
from red import Servidor, Cliente, descubrir_ip_local
from recursos import Recursos


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class UI:
    def __init__(self, screen, paleta_clave="normal", tam_fuente="mediano"):
        self.screen = screen
        self.paleta_clave = paleta_clave
        self.tam_fuente = tam_fuente
        self._cargar_fuentes()

    def _cargar_fuentes(self):
        tam = settings.TAMANOS_FUENTE[self.tam_fuente]
        self.fuentes = {
            k: pygame.font.SysFont("arial", v, bold=(k in ("lg", "xl")))
            for k, v in tam.items()
        }

    @property
    def col(self):
        return settings.PALETAS[self.paleta_clave]

    def cambiar_paleta(self, clave):
        self.paleta_clave = clave

    def cambiar_tam_fuente(self, tam):
        self.tam_fuente = tam
        self._cargar_fuentes()

    def texto(self, txt, size, color=None, x=0, y=0, centrado=False, anchor=None,
              sombra=False):
        if color is None:
            color = self.col["texto"]
        fuente = self.fuentes[size]
        lineas = str(txt).split("\n")
        y_act = y
        for ln in lineas:
            r = fuente.render(ln, True, color)
            if anchor == "topright":
                rect = r.get_rect(topright=(x, y_act))
            elif centrado:
                rect = r.get_rect(center=(x, y_act + r.get_height() // 2))
            else:
                rect = r.get_rect(topleft=(x, y_act))
            if sombra:
                shadow = fuente.render(ln, True, (0, 0, 0))
                self.screen.blit(shadow, rect.move(2, 2))
            self.screen.blit(r, rect)
            y_act += r.get_height()

    def panel(self, rect, color=None, borde=None, radio=12, alpha=None):
        if color is None:
            color = self.col["panel"]
        if alpha is not None:
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, (*color, alpha), surf.get_rect(),
                             border_radius=radio)
            self.screen.blit(surf, rect.topleft)
        else:
            pygame.draw.rect(self.screen, color, rect, border_radius=radio)
        if borde:
            pygame.draw.rect(self.screen, borde, rect, 2, border_radius=radio)

    def boton(self, rect, etiqueta, hover=False, activo=False,
              color_bg=None, color_txt=None):
        c = self.col
        if color_bg is None:
            color_bg = c["primario"] if activo else c["panel"]
        if hover and not activo:
            color_bg = tuple(min(255, v + 25) for v in color_bg)
        if color_txt is None:
            color_txt = c["texto"]
        pygame.draw.rect(self.screen, color_bg, rect, border_radius=10)
        pygame.draw.rect(self.screen, c["primario"] if not activo else c["texto"],
                         rect, 2, border_radius=10)
        fuente = self.fuentes["md"]
        r = fuente.render(etiqueta, True, color_txt)
        self.screen.blit(r, r.get_rect(center=rect.center))


# ---------------------------------------------------------------------------
# ESTADO DEL JUEGO
# ---------------------------------------------------------------------------
class EstadoJuego:
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
        self.mensajes_flotantes = []
        self.mensaje_log = []
        self.modo = "individual"
        self.dificultad = "media"

    def msg(self, texto, color=None):
        self.mensajes_flotantes.append((texto, time.time(), color))
        self.mensaje_log.append(texto)
        if len(self.mensaje_log) > 12:
            self.mensaje_log.pop(0)


# ---------------------------------------------------------------------------
# JUEGO PRINCIPAL
# ---------------------------------------------------------------------------
class Juego:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(settings.TITLE)
        self.screen = pygame.display.set_mode((settings.WIDTH, settings.HEIGHT))
        self.clock = pygame.time.Clock()
        self.ui = UI(self.screen, "normal", "mediano")
        self.audio = GestorAudio()
        self.recursos = Recursos()
        self.estado = EstadoJuego()
        self.pantalla = "menu"
        self.servidor = None
        self.cliente = None
        self.skin_idx = 0
        self.nombre_jugador = "Guardián"
        self.config_host = settings.HOST_DEFAULT
        self.config_port = settings.PORT_DEFAULT
        self.ip_local = descubrir_ip_local()
        self.input_activo = None

        self.nodo_evento_actual = None
        self.opcion_hover = -1
        self.pantalla_anterior = "menu"   # a dónde volver desde 'ayuda'

        # Ícono de ventana si está disponible
        ic = self.recursos.cargar("LinkUp_Logo") or self.recursos.cargar("icono_app")
        if ic:
            try:
                pygame.display.set_icon(ic)
            except pygame.error:
                pass

    def correr(self):
        while True:
            dt = self.clock.tick(settings.FPS) / 1000.0
            eventos = pygame.event.get()
            for e in eventos:
                if e.type == pygame.QUIT:
                    self.salir()
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F1:
                    if self.pantalla != "ayuda":
                        self.pantalla_anterior = self.pantalla
                    self.pantalla = "ayuda"
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F2:
                    nueva = "daltonico" if self.ui.paleta_clave == "normal" else "normal"
                    self.ui.cambiar_paleta(nueva)
                    self.estado.msg(f"Paleta: {nueva}")
                if e.type == pygame.KEYDOWN and e.key == pygame.K_F3:
                    actuales = list(settings.TAMANOS_FUENTE.keys())
                    i = (actuales.index(self.ui.tam_fuente) + 1) % len(actuales)
                    self.ui.cambiar_tam_fuente(actuales[i])
                    self.estado.msg(f"Tamaño texto: {actuales[i]}")

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
                self.pantalla = "menu"

            pygame.display.flip()

    def salir(self):
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
        """Dibuja una imagen de fondo si existe; si no, anima puntos."""
        fondo = self.recursos.fondo(nombre_imagen, settings.WIDTH, settings.HEIGHT)
        if fondo is not None:
            self.screen.blit(fondo, (0, 0))
            return
        c = self.ui.col
        self.screen.fill(c["fondo"])
        if fallback_animado:
            t = time.time() * 0.3
            for i in range(40):
                ang = i * 0.4 + t
                r = 200 + 60 * math.sin(t * 0.7 + i)
                x = settings.WIDTH // 2 + math.cos(ang) * r
                y = settings.HEIGHT // 2 + math.sin(ang) * r * 0.6
                pygame.draw.circle(self.screen, c["fondo2"], (int(x), int(y)), 3)

    # ===================== MENÚ =====================
    def pantalla_menu(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")

        # Logo
        logo = self.recursos.logo()
        if logo:
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

        self.ui.texto("Construye empatía. Detén el odio. Une la red.",
                      "sm", c["texto_sec"], settings.WIDTH // 2, y_titulo,
                      centrado=True, sombra=True)

        opciones = [
            ("Jugar - Individual",       "individual"),
            ("Hospedar partida (Host)",  "host"),
            ("Unirse a partida",         "join"),
            ("Configuración",            "config"),
            ("Ayuda",                    "ayuda"),
            ("Salir",                    "salir"),
        ]
        x = settings.WIDTH // 2 - 180
        y0 = max(280, y_titulo + 40)
        mouse = pygame.mouse.get_pos()
        for i, (txt, accion) in enumerate(opciones):
            rect = pygame.Rect(x, y0 + i * 58, 360, 46)
            hover = rect.collidepoint(mouse)
            self.ui.boton(rect, txt, hover=hover)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect.collidepoint(e.pos):
                    self.audio.play("click")
                    self._accion_menu(accion)

        self.ui.texto("F1 Ayuda  ·  F2 Modo daltónico  ·  F3 Tamaño texto",
                      "xs", c["texto_sec"], settings.WIDTH // 2,
                      settings.HEIGHT - 28, centrado=True, sombra=True)

    def _accion_menu(self, accion):
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

    # ===================== CONFIG =====================
    def pantalla_config(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Configuración", "xl", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True, sombra=True)

        # Skin selector (con imagen completa si existe)
        self.ui.texto("Elige tu skin:", "md", c["texto"], 80, 130, sombra=True)
        mouse = pygame.mouse.get_pos()
        for i, skin in enumerate(settings.SKINS):
            x = 80 + i * 200
            y = 170
            rect = pygame.Rect(x, y, 180, 280)
            color_bg = c["panel"] if i != self.skin_idx else c["primario"]
            self.ui.panel(rect, color=color_bg, borde=c["primario"], radio=12)

            # Imagen completa del skin
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
                # fallback: círculo con símbolo
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

        # Nombre
        self.ui.texto("Tu nombre:", "md", c["texto"], 80, 480, sombra=True)
        rect_nombre = pygame.Rect(80, 520, 400, 40)
        pygame.draw.rect(self.screen, c["panel"], rect_nombre, border_radius=8)
        pygame.draw.rect(self.screen, c["primario"], rect_nombre, 2, border_radius=8)
        self.ui.texto(self.nombre_jugador, "md", c["texto"],
                      rect_nombre.x + 10, rect_nombre.y + 8)
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_nombre.collidepoint(e.pos):
                self.input_activo = "nombre"
            if e.type == pygame.KEYDOWN and self.input_activo == "nombre":
                if e.key == pygame.K_RETURN:
                    self.input_activo = None
                elif e.key == pygame.K_BACKSPACE:
                    self.nombre_jugador = self.nombre_jugador[:-1]
                elif len(self.nombre_jugador) < 16 and e.unicode.isprintable():
                    self.nombre_jugador += e.unicode

        # Accesibilidad info
        self.ui.texto(
            f"Paleta: {self.ui.paleta_clave} (F2) · Texto: {self.ui.tam_fuente} (F3)",
            "sm", c["texto_sec"], 80, 580, sombra=True)

        rect_volver = pygame.Rect(80, settings.HEIGHT - 70, 200, 46)
        self.ui.boton(rect_volver, "← Volver",
                      hover=rect_volver.collidepoint(mouse))
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_volver.collidepoint(e.pos):
                self.audio.play("click")
                self.pantalla = "menu"

    # ===================== AYUDA =====================
    def pantalla_ayuda(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        # Panel semi-transparente
        rect_p = pygame.Rect(40, 30, settings.WIDTH - 80, settings.HEIGHT - 110)
        self.ui.panel(rect_p, color=c["fondo"], borde=c["primario"],
                      radio=14, alpha=220)
        self.ui.texto("Cómo jugar", "xl", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True)

        texto = (
            "  Eres un Guardián del Nexo en CiberNexo. Tu misión es recorrer\n"
            "  la red social ayudando a víctimas de ciberbullying,\n"
            "  neutralizando acosadores y formando puentes de empatía.\n\n"
            "Controles:\n"
            "  · Click en un nodo vecino para moverte.\n"
            "  · Click en tu nodo o uno vecino activo: abre el árbol de decisiones.\n"
            "  · Algunas aristas son muros de odio (rojas): usa Voz Amplificada (P).\n"
            "  · P: usa el poder más relevante en tu posición.\n"
            "  · F1 ayuda · F2 daltónico · F3 tamaño texto · ESC menú · R reiniciar\n\n"
            "Tipos de nodo:\n"
            "  · Víctima: necesita apoyo · Bully: acosador a transformar\n"
            "  · Aliado: puede unirse · Neutro: observador · Central: el corazón\n\n"
            "Estructuras de datos usadas:\n"
            "  · GRAFO   → la red social\n"
            "  · ÁRBOL   → árbol de decisiones de cada situación\n"
            "  · COLA DE PRIORIDAD → orden de propagación del odio\n\n"
            "Inclusión: modo daltónico, texto ajustable, skins diversos,\n"
            "iconos + colores, contraste alto, audio descriptivo."
        )
        self.ui.texto(texto, "sm", c["texto"], 80, 100)

        rect_volver = pygame.Rect(settings.WIDTH // 2 - 90,
                                  settings.HEIGHT - 70, 180, 46)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_volver, "Volver",
                      hover=rect_volver.collidepoint(mouse))
        destino_volver = self.pantalla_anterior or "menu"
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_volver.collidepoint(e.pos):
                self.audio.play("click")
                self.pantalla = destino_volver
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.pantalla = destino_volver

    # ===================== LOBBIES =====================
    def pantalla_lobby_host(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Sala de Guardianes (HOST)", "lg", c["primario"],
                      settings.WIDTH // 2, 50, centrado=True, sombra=True)
        self.ui.texto("Comparte esta IP con tus aliados:", "md", c["texto"],
                      settings.WIDTH // 2, 120, centrado=True, sombra=True)
        self.ui.texto(f"{self.ip_local} : {self.config_port}", "xl",
                      c["primario"], settings.WIDTH // 2, 160,
                      centrado=True, sombra=True)

        if self.servidor:
            self.servidor.procesar()
            jugs = self.servidor.jugadores()
            panel = pygame.Rect(settings.WIDTH//2 - 250, 240, 500, 280)
            self.ui.panel(panel, alpha=180)
            self.ui.texto(f"Conectados: {len(jugs) + 1}/4", "md", c["texto"],
                          panel.x + 20, panel.y + 20)
            self.ui.texto(f"  · Tú (Host) — {self.nombre_jugador}", "sm",
                          c["texto"], panel.x + 30, panel.y + 60)
            for i, (jid, nom, sk) in enumerate(jugs):
                self.ui.texto(f"  · Cliente #{jid} — {nom}", "sm",
                              c["texto"], panel.x + 30, panel.y + 90 + i * 28)

        rect_start = pygame.Rect(settings.WIDTH // 2 - 150,
                                 settings.HEIGHT - 130, 300, 56)
        rect_cancel = pygame.Rect(settings.WIDTH // 2 - 100,
                                  settings.HEIGHT - 64, 200, 44)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_start, "Iniciar partida",
                      hover=rect_start.collidepoint(mouse), activo=True)
        self.ui.boton(rect_cancel, "Cancelar",
                      hover=rect_cancel.collidepoint(mouse))
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
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        self.ui.texto("Unirse a una partida", "lg", c["primario"],
                      settings.WIDTH // 2, 60, centrado=True, sombra=True)
        self.ui.texto("IP del host:", "md", c["texto"], 200, 160, sombra=True)
        rect_ip = pygame.Rect(200, 200, 400, 40)
        pygame.draw.rect(self.screen, c["panel"], rect_ip, border_radius=8)
        pygame.draw.rect(self.screen, c["primario"], rect_ip, 2, border_radius=8)
        self.ui.texto(self.config_host, "md", c["texto"],
                      rect_ip.x + 10, rect_ip.y + 8)

        mouse = pygame.mouse.get_pos()
        rect_conn = pygame.Rect(settings.WIDTH // 2 - 120, 300, 240, 50)
        self.ui.boton(rect_conn, "Conectar",
                      hover=rect_conn.collidepoint(mouse), activo=True)
        rect_back = pygame.Rect(80, settings.HEIGHT - 70, 200, 44)
        self.ui.boton(rect_back, "← Volver",
                      hover=rect_back.collidepoint(mouse))

        if self.cliente:
            self.cliente.procesar()
            self.ui.texto("Estado:", "md", c["primario"], 80, 400, sombra=True)
            estado_txt = "Conectado" if self.cliente.conectado else "Desconectado"
            self.ui.texto(estado_txt, "md", c["texto"], 200, 400, sombra=True)
            for i, m in enumerate(self.cliente.mensajes[-6:]):
                self.ui.texto(m, "sm", c["texto_sec"], 80, 440 + i * 24, sombra=True)
            if self.cliente.estado_juego:
                self._sincronizar_desde_servidor()
                self.pantalla = "mapa"

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
            if e.type == pygame.KEYDOWN and self.input_activo == "host":
                if e.key == pygame.K_RETURN:
                    self.input_activo = None
                elif e.key == pygame.K_BACKSPACE:
                    self.config_host = self.config_host[:-1]
                elif len(self.config_host) < 20:
                    ch = e.unicode
                    if ch and (ch.isdigit() or ch == ".:"):
                        self.config_host += ch

    # ===================== MAPA =====================
    def pantalla_mapa(self, eventos, dt):
        c = self.ui.col
        self._dibujar_fondo("fondo_mapa")

        if self.servidor:
            self.servidor.procesar()
            self._procesar_acciones_servidor()
        if self.cliente:
            self.cliente.procesar()
            if self.cliente.estado_juego:
                self._sincronizar_desde_servidor()

        self._tick(dt)

        g = self.estado.grafo
        if g is None:
            return

        # Aristas
        for u, adj in g.aristas.items():
            for v, info in adj.items():
                if u >= v:
                    continue
                nu, nv = g.nodos[u], g.nodos[v]
                color = c["arista"]
                ancho = 2
                if info["muro"] and not info["rota"]:
                    color = c["muro"]; ancho = 4
                elif info["muro"] and info["rota"]:
                    color = c["exito"]; ancho = 2
                pygame.draw.line(self.screen, color,
                                 (nu.x, nu.y), (nv.x, nv.y), ancho)

        # Nodos
        mouse = pygame.mouse.get_pos()
        nodo_hover = None
        for nodo in g.nodos.values():
            radio = 30 if nodo.tipo == "central" else 24
            pulse = 0
            if nodo.estado == "infectado":
                pulse = int(6 * abs(math.sin(time.time() * 4)))

            tam = (radio + pulse) * 2
            img = self.recursos.imagen_nodo(nodo.tipo, nodo.estado)
            if img:
                img_esc = self.recursos.escalar(
                    self._nombre_archivo_nodo(nodo), tam, tam)
                if img_esc is not None:
                    rect = img_esc.get_rect(center=(int(nodo.x), int(nodo.y)))
                    self.screen.blit(img_esc, rect)
                else:
                    self._dibujar_nodo_fallback(nodo, radio + pulse)
            else:
                self._dibujar_nodo_fallback(nodo, radio + pulse)

            if nodo.estado == "resuelto":
                pygame.draw.circle(self.screen, c["exito"],
                                   (int(nodo.x + radio), int(nodo.y - radio)), 7)
                pygame.draw.circle(self.screen, c["fondo"],
                                   (int(nodo.x + radio), int(nodo.y - radio)), 7, 2)

            if (nodo.x - mouse[0]) ** 2 + (nodo.y - mouse[1]) ** 2 < (radio + 6) ** 2:
                nodo_hover = nodo

        # Jugadores
        for jug in self.estado.jugadores:
            n = g.nodos.get(jug["pos"])
            if not n:
                continue
            offset_x = (jug["id"] - 1.5) * 18
            offset_y = -34
            sk = settings.SKINS[jug["skin"] % len(settings.SKINS)]
            cx, cy = int(n.x + offset_x), int(n.y + offset_y)
            avatar = self.recursos.avatar_skin(sk["nombre"])
            if avatar:
                avatar_esc = self.recursos.escalar(
                    f"nodo_{sk['nombre'].lower()}", 36, 36)
                if avatar_esc:
                    pygame.draw.circle(self.screen, sk["color"], (cx, cy), 20)
                    rect = avatar_esc.get_rect(center=(cx, cy))
                    self.screen.blit(avatar_esc, rect)
                    pygame.draw.circle(self.screen, c["texto"], (cx, cy), 20, 2)
                else:
                    self._dibujar_jugador_fallback(cx, cy, sk, c)
            else:
                self._dibujar_jugador_fallback(cx, cy, sk, c)
            self.ui.texto(jug["nombre"][:8], "xs", c["texto"],
                          cx, cy + 18, centrado=True, sombra=True)

        self._dibujar_hud(nodo_hover)
        self._dibujar_mensajes_flotantes()
        if nodo_hover:
            self._dibujar_tooltip_nodo(nodo_hover, mouse)

        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._click_mapa(e.pos)
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.audio.play("click")
                    self.pantalla = "pausa"
                if e.key == pygame.K_p:
                    self._usar_poder()
                if e.key == pygame.K_r and self.estado.modo == "individual":
                    self._iniciar_partida_local()

    def _nombre_archivo_nodo(self, nodo):
        if nodo.estado == "resuelto":
            return "nodo_resuelto"
        if nodo.estado == "infectado":
            return "nodo_infectado"
        return f"nodo_{nodo.tipo}"

    def _dibujar_nodo_fallback(self, nodo, radio):
        c = self.ui.col
        color = self._color_nodo(nodo)
        pygame.draw.circle(self.screen, color, (int(nodo.x), int(nodo.y)), radio)
        pygame.draw.circle(self.screen, c["fondo"],
                           (int(nodo.x), int(nodo.y)), radio, 3)
        simbolo = {"victima": "♥", "bully": "✖", "aliado": "+",
                   "neutro": "•", "central": "★"}.get(nodo.tipo, "")
        self.ui.texto(simbolo, "md", (20, 20, 30),
                      nodo.x, nodo.y - 12, centrado=True)

    def _dibujar_jugador_fallback(self, cx, cy, sk, c):
        pygame.draw.circle(self.screen, sk["color"], (cx, cy), 14)
        pygame.draw.circle(self.screen, c["texto"], (cx, cy), 14, 2)
        self.ui.texto(sk["simbolo"], "sm", (20, 20, 30),
                      cx, cy - 10, centrado=True)

    def _color_nodo(self, nodo):
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

    def _dibujar_hud(self, nodo_hover):
        c = self.ui.col
        rect = pygame.Rect(settings.WIDTH - 280, 10, 270, settings.HEIGHT - 20)
        self.ui.panel(rect, borde=c["primario"], alpha=210)
        self.ui.texto("HUD", "lg", c["primario"], rect.x + 20, rect.y + 12)

        y = rect.y + 60
        jl = self.estado.jugadores[self.estado.jugador_local]
        self.ui.texto(f"Jugador: {jl['nombre']}", "sm", c["texto"], rect.x + 20, y); y += 22
        self.ui.texto(f"Puntos: {jl['puntos']}", "sm", c["texto"], rect.x + 20, y); y += 22
        self.ui.texto(f"Salud red: {self.estado.salud_comunidad}", "sm",
                      c["texto"], rect.x + 20, y); y += 28
        bar = pygame.Rect(rect.x + 20, y, 230, 12)
        pygame.draw.rect(self.screen, c["panel"], bar, border_radius=4)
        ratio = max(0, self.estado.salud_comunidad) / settings.SALUD_COMUNIDAD_INICIAL
        bar_in = pygame.Rect(bar.x, bar.y, int(bar.w * ratio), bar.h)
        col_bar = c["exito"] if ratio > 0.5 else c["alerta"] if ratio > 0.25 else c["peligro"]
        pygame.draw.rect(self.screen, col_bar, bar_in, border_radius=4)
        y += 28

        self.ui.texto("Poderes (P)", "md", c["primario"], rect.x + 20, y); y += 28
        for k, n in jl["poderes"].items():
            self.ui.texto(f"{self._nombre_poder(k)}: {n}", "sm", c["texto"],
                          rect.x + 20, y); y += 22

        y += 10
        self.ui.texto("Cola del odio", "md", c["primario"], rect.x + 20, y); y += 28
        eventos = self.estado.cola_eventos.listar()[:5]
        if not eventos:
            self.ui.texto("(vacía)", "sm", c["texto_sec"], rect.x + 20, y); y += 22
        for p, dato in eventos:
            self.ui.texto(f"t+{p:.1f}s → nodo {dato.get('nodo','?')}",
                          "xs", c["texto"], rect.x + 20, y); y += 18

        y += 10
        self.ui.texto("Mensajes", "md", c["primario"], rect.x + 20, y); y += 24
        for m in self.estado.mensaje_log[-7:]:
            self.ui.texto(m[:34], "xs", c["texto_sec"], rect.x + 20, y); y += 18

        mini_rect = pygame.Rect(rect.x + 20, settings.HEIGHT - 180, 230, 160)
        self.ui.panel(mini_rect, color=c["fondo2"], borde=c["primario"])
        self._dibujar_minimapa(mini_rect)

        # Pequeña etiqueta de modo + recordatorio de pausa, sin barra superior grande
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
        g = self.estado.grafo
        if not g:
            return
        xs = [n.x for n in g.nodos.values()]
        ys = [n.y for n in g.nodos.values()]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        w = max(1, maxx - minx); h = max(1, maxy - miny); pad = 6
        def proy(n):
            x = mini_rect.x + pad + (n.x - minx) / w * (mini_rect.w - 2 * pad)
            y = mini_rect.y + pad + (n.y - miny) / h * (mini_rect.h - 2 * pad)
            return int(x), int(y)
        for u, adj in g.aristas.items():
            for v in adj:
                if u >= v:
                    continue
                pygame.draw.line(self.screen, self.ui.col["arista"],
                                 proy(g.nodos[u]), proy(g.nodos[v]), 1)
        for nodo in g.nodos.values():
            pygame.draw.circle(self.screen, self._color_nodo(nodo), proy(nodo), 3)
        for jug in self.estado.jugadores:
            n = g.nodos[jug["pos"]]
            sk = settings.SKINS[jug["skin"] % len(settings.SKINS)]
            pygame.draw.circle(self.screen, sk["color"], proy(n), 4)

    def _dibujar_tooltip_nodo(self, nodo, mouse):
        c = self.ui.col
        info = [f"{nodo.nombre} ({nodo.tipo})", f"Estado: {nodo.estado}"]
        w = 200; h = 14 + 22 * len(info)
        x = min(mouse[0] + 12, settings.WIDTH - w - 10)
        y = min(mouse[1] + 12, settings.HEIGHT - h - 10)
        rect = pygame.Rect(x, y, w, h)
        self.ui.panel(rect, borde=c["primario"], alpha=220)
        for i, t in enumerate(info):
            self.ui.texto(t, "xs", c["texto"], x + 8, y + 6 + i * 18)

    def _dibujar_mensajes_flotantes(self):
        ahora = time.time()
        nuevos = []
        for txt, t0, col in self.estado.mensajes_flotantes:
            if ahora - t0 > 3.0:
                continue
            nuevos.append((txt, t0, col))
        self.estado.mensajes_flotantes = nuevos
        for i, (txt, t0, col) in enumerate(self.estado.mensajes_flotantes[-4:]):
            alpha = max(0, 255 - int(((ahora - t0) / 3.0) * 255))
            color = col or self.ui.col["alerta"]
            f = self.ui.fuentes["md"]
            surf = f.render(txt, True, color)
            surf.set_alpha(alpha)
            self.screen.blit(surf, (40, settings.HEIGHT - 240 - i * 28))

    def _click_mapa(self, pos):
        g = self.estado.grafo
        if not g:
            return
        jl = self.estado.jugadores[self.estado.jugador_local]
        nodo_actual = g.nodos[jl["pos"]]
        for nodo in g.nodos.values():
            if (nodo.x - pos[0]) ** 2 + (nodo.y - pos[1]) ** 2 <= 30 * 30:
                if nodo.id == nodo_actual.id:
                    self._abrir_situacion(nodo)
                    return
                if nodo.id in g.vecinos(nodo_actual.id):
                    if g.arista_transitable(nodo_actual.id, nodo.id):
                        if self.estado.modo == "cliente":
                            self.cliente.enviar_accion("mover", {"destino": nodo.id})
                        else:
                            self._mover_jugador(self.estado.jugador_local, nodo.id)
                    else:
                        self.audio.play("bloqueado")
                        self.estado.msg("Muro de odio: usa Voz Amplificada (P).",
                                        self.ui.col["peligro"])
                return

    # ===================== PAUSA =====================
    def pantalla_pausa(self, eventos):
        """Menú de pausa: reanudar, accesibilidad, ayuda, salir."""
        c = self.ui.col

        # Mostrar el mapa congelado al fondo
        self._dibujar_fondo("fondo_mapa")
        if self.estado.grafo:
            g = self.estado.grafo
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
            for nodo in g.nodos.values():
                pygame.draw.circle(self.screen, self._color_nodo(nodo),
                                   (int(nodo.x), int(nodo.y)), 14)

        # Velo oscuro semi-transparente
        velo = pygame.Surface((settings.WIDTH, settings.HEIGHT),
                              pygame.SRCALPHA)
        velo.fill((0, 0, 0, 170))
        self.screen.blit(velo, (0, 0))

        # Panel de pausa
        panel_w, panel_h = 520, 540
        panel = pygame.Rect((settings.WIDTH - panel_w) // 2,
                            (settings.HEIGHT - panel_h) // 2,
                            panel_w, panel_h)
        self.ui.panel(panel, color=c["fondo"], borde=c["primario"],
                      radio=18, alpha=240)

        self.ui.texto("⏸  Pausa", "xl", c["primario"],
                      panel.centerx, panel.y + 20, centrado=True)
        self.ui.texto("La partida está en pausa.", "sm", c["texto_sec"],
                      panel.centerx, panel.y + 80, centrado=True)

        mouse = pygame.mouse.get_pos()
        bx = panel.x + 60
        bw = panel.w - 120
        by = panel.y + 120
        gap = 60

        # 1. Reanudar
        rect_resume = pygame.Rect(bx, by, bw, 50)
        self.ui.boton(rect_resume, "Reanudar partida",
                      hover=rect_resume.collidepoint(mouse), activo=True)

        # 2. Toggle paleta
        rect_paleta = pygame.Rect(bx, by + gap, bw, 50)
        nombre_paleta = "Normal" if self.ui.paleta_clave == "normal" else "Daltónico"
        self.ui.boton(rect_paleta, f"Modo color: {nombre_paleta}",
                      hover=rect_paleta.collidepoint(mouse))

        # 3. Cycle tamaño texto
        rect_texto = pygame.Rect(bx, by + gap * 2, bw, 50)
        nombre_tam = {"pequeno": "Pequeño", "mediano": "Mediano",
                      "grande": "Grande"}.get(self.ui.tam_fuente, "Mediano")
        self.ui.boton(rect_texto, f"Tamaño texto: {nombre_tam}",
                      hover=rect_texto.collidepoint(mouse))

        # 4. Ayuda
        rect_ayuda = pygame.Rect(bx, by + gap * 3, bw, 50)
        self.ui.boton(rect_ayuda, "Ver ayuda / instrucciones",
                      hover=rect_ayuda.collidepoint(mouse))

        # 5. Salir al menú principal
        rect_salir = pygame.Rect(bx, by + gap * 4, bw, 50)
        self.ui.boton(rect_salir, "Salir al menú principal",
                      hover=rect_salir.collidepoint(mouse))

        # 6. Salir del juego
        rect_quit = pygame.Rect(bx, by + gap * 5, bw, 50)
        self.ui.boton(rect_quit, "Salir del juego",
                      hover=rect_quit.collidepoint(mouse))

        # Hint inferior
        self.ui.texto("Pulsa ESC para reanudar", "xs", c["texto_sec"],
                      panel.centerx, panel.bottom - 30, centrado=True)

        # Manejo de input
        for e in eventos:
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

    # ===================== EVENTO =====================
    def pantalla_evento(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_evento" if self.recursos.cargar("fondo_evento") else "fondo_menu")
        nodo = self.nodo_evento_actual
        if nodo is None:
            self.pantalla = "mapa"; return
        arbol = self.estado.situaciones.get(nodo.id)
        if not arbol:
            self.pantalla = "mapa"; return

        panel = pygame.Rect(80, 60, settings.WIDTH - 160, settings.HEIGHT - 120)
        self.ui.panel(panel, borde=c["primario"], radio=18, alpha=230)

        # Imagen del nodo a la izquierda
        img_nodo = self.recursos.imagen_nodo(nodo.tipo, nodo.estado)
        if img_nodo:
            img_esc = pygame.transform.smoothscale(img_nodo, (140, 140))
            self.screen.blit(img_esc, (panel.x + 30, panel.y + 30))
            x_texto = panel.x + 200
        else:
            x_texto = panel.x + 30

        self.ui.texto(f"Nodo {nodo.nombre} ({nodo.tipo})", "lg",
                      c["primario"], x_texto, panel.y + 30)
        self.ui.texto(arbol.actual.texto, "md", c["texto"],
                      x_texto, panel.y + 90)

        if arbol.actual.es_hoja():
            tipo = arbol.actual.tipo_resultado
            col = {"bueno": c["exito"], "neutro": c["alerta"],
                   "malo": c["peligro"]}.get(tipo, c["texto"])
            self.ui.texto(
                {"bueno": "Excelente decisión",
                 "neutro": "Decisión aceptable",
                 "malo":  "Consecuencias negativas"}[tipo],
                "lg", col, x_texto, panel.y + 260)

            rect_cont = pygame.Rect(panel.right - 250, panel.bottom - 80, 220, 50)
            mouse = pygame.mouse.get_pos()
            self.ui.boton(rect_cont, "Continuar",
                          hover=rect_cont.collidepoint(mouse), activo=True)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_cont.collidepoint(e.pos):
                    self._aplicar_efecto_hoja(nodo, arbol.actual)
                    self.audio.play("nivel" if tipo == "bueno" else "fallo")
                    self.pantalla = "mapa"
                if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                    self._aplicar_efecto_hoja(nodo, arbol.actual)
                    self.pantalla = "mapa"
            return

        y = panel.y + 320
        mouse = pygame.mouse.get_pos()
        for i, (texto_op, _h, _ef) in enumerate(arbol.actual.opciones):
            rect = pygame.Rect(panel.x + 30, y + i * 70, panel.w - 60, 56)
            hover = rect.collidepoint(mouse)
            self.ui.boton(rect, f"{i+1}. {texto_op}", hover=hover)
            for e in eventos:
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect.collidepoint(e.pos):
                    arbol.elegir(i); self.audio.play("click")
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                    idx = e.key - pygame.K_1
                    if idx < len(arbol.actual.opciones):
                        arbol.elegir(idx); self.audio.play("click")

        rect_back = pygame.Rect(panel.x + 30, panel.bottom - 70, 180, 46)
        self.ui.boton(rect_back, "← Salir", hover=rect_back.collidepoint(mouse))
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and rect_back.collidepoint(e.pos):
                self.pantalla = "mapa"

    # ===================== FIN =====================
    def pantalla_fin(self, eventos):
        c = self.ui.col
        self._dibujar_fondo("fondo_menu")
        titulo = "¡Victoria!" if self.estado.victoria else "Fin de la partida"
        col = c["exito"] if self.estado.victoria else c["peligro"]
        self.ui.texto(titulo, "xl", col, settings.WIDTH // 2, 70,
                      centrado=True, sombra=True)

        n_res = sum(1 for n in self.estado.grafo.nodos.values() if n.estado == "resuelto")
        n_inf = sum(1 for n in self.estado.grafo.nodos.values() if n.estado == "infectado")
        tiempo = int(self.estado.tiempo_actual - self.estado.tiempo_inicio)
        lineas = [
            f"Tiempo jugado: {tiempo} s",
            f"Salud final de la red: {self.estado.salud_comunidad}",
            f"Nodos resueltos: {n_res}/{len(self.estado.grafo.nodos)}",
            f"Nodos infectados: {n_inf}",
        ]
        for jug in self.estado.jugadores:
            lineas.append(f"Jugador {jug['nombre']}: {jug['puntos']} pts")
        for i, t in enumerate(lineas):
            self.ui.texto(t, "md", c["texto"], settings.WIDTH // 2,
                          180 + i * 36, centrado=True, sombra=True)

        mensaje = ("Ayudaste a construir empatía. Tu red es más fuerte."
                   if self.estado.victoria else
                   "El odio se propagó. La empatía gana cuando actuamos a tiempo.")
        self.ui.texto(mensaje, "md", c["primario"], settings.WIDTH // 2,
                      settings.HEIGHT - 180, centrado=True, sombra=True)

        rect_re = pygame.Rect(settings.WIDTH // 2 - 220, settings.HEIGHT - 110, 200, 56)
        rect_menu = pygame.Rect(settings.WIDTH // 2 + 20, settings.HEIGHT - 110, 200, 56)
        mouse = pygame.mouse.get_pos()
        self.ui.boton(rect_re, "Jugar otra vez",
                      hover=rect_re.collidepoint(mouse), activo=True)
        self.ui.boton(rect_menu, "Menú principal",
                      hover=rect_menu.collidepoint(mouse))
        for e in eventos:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if rect_re.collidepoint(e.pos):
                    self.audio.play("click"); self._iniciar_partida_local()
                elif rect_menu.collidepoint(e.pos):
                    self.audio.play("click"); self.pantalla = "menu"

    # ===================== LÓGICA =====================
    def _iniciar_partida_local(self):
        n = random.randint(settings.NUM_NODOS_MIN, settings.NUM_NODOS_MAX)
        ancho_juego = settings.WIDTH - 300
        alto_juego = settings.HEIGHT - 40
        g = Grafo.aleatorio(n, settings.PROB_ARISTA, settings.PROB_MURO,
                            ancho_juego, alto_juego,
                            settings.PROB_BULLY, settings.PROB_VICTIMA)
        self.estado = EstadoJuego()
        self.estado.grafo = g
        for nodo in g.nodos.values():
            if nodo.tipo != "neutro" or random.random() < 0.3:
                self.estado.situaciones[nodo.id] = crear_situacion(
                    nodo.tipo, nodo.nombre)
        partida_color = settings.SKINS[self.skin_idx]["color"]
        self.estado.jugadores = [{
            "id": 0, "nombre": self.nombre_jugador, "skin": self.skin_idx,
            "pos": 0, "puntos": 0,
            "poderes": dict(settings.PODERES_INICIALES),
            "color": partida_color,
        }]
        self.estado.jugador_local = 0
        self.estado.tiempo_inicio = time.time()
        self.estado.tiempo_actual = time.time()
        self._programar_eventos_iniciales()
        self.pantalla = "mapa"
        self.audio.play("nivel")
        self.estado.msg("¡Bienvenido, Guardián!", self.ui.col["primario"])

    def _iniciar_host(self):
        if self.servidor:
            self.servidor.detener()
        self.servidor = Servidor(settings.HOST_DEFAULT, settings.PORT_DEFAULT)
        try:
            self.servidor.iniciar()
            self.pantalla = "lobby_host"
        except OSError as e:
            self.estado.msg(f"No se pudo iniciar el servidor: {e}",
                            self.ui.col["peligro"])

    def _conectar_cliente(self):
            if self.cliente:
                self.cliente.desconectar()
            # Permite "192.168.1.12" o "192.168.1.12:50007"
            host = self.config_host.strip()
            puerto = self.config_port
            if ":" in host:
                host, _, puerto_txt = host.partition(":")
                host = host.strip()
                try:
                    puerto = int(puerto_txt.strip())
                except ValueError:
                    puerto = self.config_port
            self.cliente = Cliente(host, puerto,
                                self.nombre_jugador, self.skin_idx)
            ok = self.cliente.conectar()
            if not ok:
                self.estado.msg("Error de conexión", self.ui.col["peligro"])

    def _iniciar_partida_multijugador(self):
        self._iniciar_partida_local()
        self.estado.modo = "servidor"
        for jid, nombre, skin in self.servidor.jugadores():
            self.estado.jugadores.append({
                "id": len(self.estado.jugadores),
                "nombre": nombre, "skin": skin, "pos": 0, "puntos": 0,
                "poderes": dict(settings.PODERES_INICIALES),
                "color": settings.SKINS[skin]["color"],
            })
        self._difundir_estado()
        self.audio.play("nivel")

    def _programar_eventos_iniciales(self):
        bullies = [n for n in self.estado.grafo.nodos.values() if n.tipo == "bully"]
        for b in bullies:
            tiempo = random.uniform(20, 60)
            self.estado.cola_eventos.push(tiempo, {"tipo": "propagar", "nodo": b.id})

    def _tick(self, dt):
        if self.estado.fin:
            return
        self.estado.tiempo_actual += dt
        elapsed = self.estado.tiempo_actual - self.estado.tiempo_inicio
        while not self.estado.cola_eventos.vacia():
            prox = self.estado.cola_eventos.peek()
            if prox is None:
                break
            p, dato = prox
            if elapsed >= p:
                self.estado.cola_eventos.pop()
                self._ejecutar_evento(dato)
            else:
                break

        if self.estado.salud_comunidad <= 0:
            self.estado.fin = True; self.estado.victoria = False
            self.audio.play("fallo"); self.pantalla = "fin"; return

        nodos = list(self.estado.grafo.nodos.values())
        resueltos = sum(1 for n in nodos if n.estado == "resuelto")
        central = self.estado.grafo.nodos[0]
        if resueltos >= max(1, int(len(nodos) * 0.7)) and central.estado != "infectado":
            self.estado.fin = True; self.estado.victoria = True
            self.audio.play("nivel"); self.pantalla = "fin"

    def _ejecutar_evento(self, dato):
        if dato["tipo"] == "propagar":
            nodo = self.estado.grafo.nodos.get(dato["nodo"])
            if nodo is None or nodo.estado == "resuelto":
                return
            for v in self.estado.grafo.vecinos(nodo.id):
                vn = self.estado.grafo.nodos[v]
                if vn.estado == "resuelto":
                    continue
                if random.random() < 0.4:
                    if vn.tipo not in ("bully", "central"):
                        vn.tipo = "victima"
                        if v not in self.estado.situaciones:
                            self.estado.situaciones[v] = crear_situacion("victima", vn.nombre)
                    vn.estado = "infectado"
                    self.estado.salud_comunidad -= 5
                    self.estado.msg(f"El odio se propagó a {vn.nombre}",
                                    self.ui.col["peligro"])
                    self.audio.play("evento")
                    self.estado.cola_eventos.push(
                        (self.estado.tiempo_actual - self.estado.tiempo_inicio) + random.uniform(15, 30),
                        {"tipo": "propagar", "nodo": v})

    def _mover_jugador(self, id_jug, destino):
        g = self.estado.grafo
        jl = self.estado.jugadores[id_jug]
        if destino in g.vecinos(jl["pos"]) and g.arista_transitable(jl["pos"], destino):
            jl["pos"] = destino
            self.audio.play("mover")
            self.estado.msg(f"{jl['nombre']} → {g.nodos[destino].nombre}")
            nodo = g.nodos[destino]
            if (id_jug == self.estado.jugador_local
                    and nodo.estado != "resuelto"
                    and nodo.id in self.estado.situaciones):
                self._abrir_situacion(nodo)
            self._difundir_estado()

    def _abrir_situacion(self, nodo):
        arbol = self.estado.situaciones.get(nodo.id)
        if arbol is None or nodo.estado == "resuelto":
            return
        arbol.reiniciar()
        self.nodo_evento_actual = nodo
        self.pantalla = "evento"

    def _aplicar_efecto_hoja(self, nodo, hoja):
        jl = self.estado.jugadores[self.estado.jugador_local]
        ef = hoja.efecto or {}
        pts = ef.get("puntos", 0)
        salud = ef.get("salud", 0)
        jl["puntos"] += pts
        self.estado.salud_comunidad = max(0, min(settings.SALUD_COMUNIDAD_INICIAL + 50,
                                                 self.estado.salud_comunidad + salud))
        if ef.get("resolver"):
            nodo.estado = "resuelto"
            if nodo.tipo == "bully":
                nodo.tipo = "aliado"
            self.estado.msg(f"{nodo.nombre} resuelto (+{pts})", self.ui.col["exito"])
        else:
            self.estado.msg(f"Resultado: {pts:+d} pts, salud {salud:+d}",
                            self.ui.col["alerta"])
        if ef.get("poder"):
            poder = ef["poder"]
            jl["poderes"][poder] = jl["poderes"].get(poder, 0) + 1
            self.estado.msg(f"¡Obtienes: {self._nombre_poder(poder)}!", self.ui.col["primario"])
            self.audio.play("poder")
        self._difundir_estado()

    def _nombre_poder(self, k):
        return {
            "escudo_empatia":  "Escudo de Empatía",
            "red_apoyo":       "Red de Apoyo",
            "voz_amplificada": "Voz Amplificada",
        }.get(k, k)

    def _usar_poder(self):
        jl = self.estado.jugadores[self.estado.jugador_local]
        g = self.estado.grafo
        pos = jl["pos"]
        muros = [v for v in g.vecinos(pos)
                 if g.aristas[pos][v]["muro"] and not g.aristas[pos][v]["rota"]]
        if muros and jl["poderes"].get("voz_amplificada", 0) > 0:
            g.romper_muro(pos, muros[0])
            jl["poderes"]["voz_amplificada"] -= 1
            self.estado.msg("¡Muro roto con Voz Amplificada!", self.ui.col["exito"])
            self.audio.play("poder"); self._difundir_estado(); return
        nodo = g.nodos[pos]
        if nodo.tipo == "victima" and nodo.estado != "resuelto" and jl["poderes"].get("escudo_empatia", 0) > 0:
            nodo.estado = "resuelto"
            jl["poderes"]["escudo_empatia"] -= 1
            jl["puntos"] += 10
            self.estado.msg("Escudo de Empatía: víctima protegida", self.ui.col["exito"])
            self.audio.play("poder"); self._difundir_estado(); return
        if jl["poderes"].get("red_apoyo", 0) > 0 and len(g.vecinos(pos)) >= 2:
            v1, v2 = g.vecinos(pos)[:2]
            if v2 not in g.vecinos(v1):
                g.agregar_arista(v1, v2)
                jl["poderes"]["red_apoyo"] -= 1
                self.estado.msg("Red de Apoyo: nueva conexión creada", self.ui.col["primario"])
                self.audio.play("poder"); self._difundir_estado(); return
        self.estado.msg("Sin poder aplicable aquí.", self.ui.col["alerta"])
        self.audio.play("bloqueado")

    # ===================== RED =====================
    def _procesar_acciones_servidor(self):
        if not self.servidor:
            return
        for accion in self.servidor.acciones_pendientes:
            id_j = accion["id_jugador"]
            ac = accion.get("accion")
            datos = accion.get("datos", {})
            idx = id_j + 1
            if idx >= len(self.estado.jugadores):
                continue
            if ac == "mover":
                self._mover_jugador(idx, int(datos.get("destino", 0)))
        self.servidor.acciones_pendientes.clear()

    def _difundir_estado(self):
        if not self.servidor:
            return
        self.servidor.difundir_estado(self._snapshot_estado())

    def _snapshot_estado(self):
        g = self.estado.grafo
        return {
            "salud": self.estado.salud_comunidad,
            "nodos": [
                {"id": n.id, "tipo": n.tipo, "estado": n.estado,
                 "x": n.x, "y": n.y, "nombre": n.nombre}
                for n in g.nodos.values()
            ],
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
            "fin": self.estado.fin, "victoria": self.estado.victoria,
        }

    def _sincronizar_desde_servidor(self):
        s = self.cliente.estado_juego
        if not s:
            return
        if self.estado.grafo is None:
            self.estado.grafo = Grafo()
        g = self.estado.grafo
        for n in s["nodos"]:
            if n["id"] not in g.nodos:
                g.agregar_nodo(Nodo(n["id"], n["tipo"], n["x"], n["y"], n["nombre"]))
            nodo = g.nodos[n["id"]]
            nodo.tipo = n["tipo"]; nodo.estado = n["estado"]
            nodo.x = n["x"]; nodo.y = n["y"]; nodo.nombre = n["nombre"]
        g.aristas = {nid: {} for nid in g.nodos}
        for u, v, muro, rota in s["aristas"]:
            g.aristas.setdefault(u, {})[v] = {"muro": muro, "rota": rota}
            g.aristas.setdefault(v, {})[u] = {"muro": muro, "rota": rota}
        self.estado.jugadores = []
        for j in s["jugadores"]:
            self.estado.jugadores.append({
                "id": j["id"], "nombre": j["nombre"], "skin": j["skin"],
                "pos": j["pos"], "puntos": j["puntos"],
                "poderes": dict(settings.PODERES_INICIALES),
                "color": settings.SKINS[j["skin"] % len(settings.SKINS)]["color"],
            })
        if self.cliente.id_jugador is not None:
            self.estado.jugador_local = self.cliente.id_jugador + 1
            if self.estado.jugador_local >= len(self.estado.jugadores):
                self.estado.jugador_local = 0
        self.estado.salud_comunidad = s["salud"]
        if s.get("fin"):
            self.estado.fin = True
            self.estado.victoria = s.get("victoria", False)
            self.pantalla = "fin"