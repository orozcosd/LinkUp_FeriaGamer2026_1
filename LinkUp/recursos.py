"""
Cargador de recursos gráficos para LinkUp.
 
Lee imágenes desde la carpeta `assets/` y las cachea (incluido el
escalado). Si una imagen no existe, devuelve None y el juego usa
el dibujo procedural de respaldo: nada se rompe.
 
Convención de nombres en assets/ (sin distinguir mayúsculas):
    fondo_menu.png, fondo_mapa.png
    LinkUp_Logo.png   (o logo.png)
    nodo_aliado.png, nodo_bully.png, nodo_victima.png, nodo_neutro.png,
    nodo_central.png, nodo_infectado.png, nodo_resuelto.png
    nodo_<skin>.png    para el avatar circular del jugador
    skin_<skin>.png    para el cuerpo completo en el selector
"""
 
import os
import pygame
 
 
DIR_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
 
 
class Recursos:
    """Cargador con caché. Una sola instancia por juego."""
 
    EXTENSIONES = (".png", ".PNG", ".jpg", ".jpeg")
 
    def __init__(self):
        self.cache_originales = {}     # nombre -> Surface (o None)
        self.cache_escalado = {}       # (nombre, w, h) -> Surface
 
    # ------------------------------------------------------------------
    # Núcleo
    # ------------------------------------------------------------------
    def cargar(self, nombre):
        """Devuelve la Surface cargada o None si no existe."""
        if nombre in self.cache_originales:
            return self.cache_originales[nombre]
        # Buscar el archivo en varias extensiones e ignorando mayúsculas
        candidatos = [nombre + ext for ext in self.EXTENSIONES]
        if os.path.isdir(DIR_ASSETS):
            try:
                listado = {f.lower(): f for f in os.listdir(DIR_ASSETS)}
            except OSError:
                listado = {}
            for cand in candidatos:
                real = listado.get(cand.lower())
                if real:
                    try:
                        ruta = os.path.join(DIR_ASSETS, real)
                        img = pygame.image.load(ruta).convert_alpha()
                        self.cache_originales[nombre] = img
                        return img
                    except pygame.error:
                        pass
        self.cache_originales[nombre] = None
        return None
 
    def escalar(self, nombre, w, h):
        """Devuelve la imagen `nombre` escalada a (w, h)."""
        if w <= 0 or h <= 0:
            return None
        clave = (nombre, int(w), int(h))
        if clave in self.cache_escalado:
            return self.cache_escalado[clave]
        img = self.cargar(nombre)
        if img is None:
            return None
        try:
            escalada = pygame.transform.smoothscale(img, (int(w), int(h)))
        except pygame.error:
            return None
        self.cache_escalado[clave] = escalada
        return escalada
 
    # ------------------------------------------------------------------
    # Helpers de alto nivel
    # ------------------------------------------------------------------
    def fondo(self, nombre, w, h):
        return self.escalar(nombre, w, h)
 
    def logo(self):
        """Logo principal. Acepta varios nombres comunes."""
        for n in ("LinkUp_Logo", "linkup_logo", "logo_linkup", "logo"):
            img = self.cargar(n)
            if img:
                return img
        return None
 
    def imagen_nodo(self, tipo, estado):
        """Selecciona la imagen del nodo según estado y tipo."""
        if estado == "resuelto":
            img = self.cargar("nodo_resuelto")
            if img:
                return img
        if estado == "infectado":
            img = self.cargar("nodo_infectado")
            if img:
                return img
        return self.cargar(f"nodo_{tipo}")
 
    def avatar_skin(self, skin_nombre):
        """Avatar circular del jugador (versión pequeña)."""
        return self.cargar(f"nodo_{skin_nombre.lower()}")
 
    def skin_completo(self, skin_nombre):
        """Imagen de cuerpo completo (selector de skin)."""
        return self.cargar(f"skin_{skin_nombre.lower()}")
 
    # ------------------------------------------------------------------
    # Utilidades de diagnóstico
    # ------------------------------------------------------------------
    def listar_disponibles(self):
        if not os.path.isdir(DIR_ASSETS):
            return []
        return sorted(os.listdir(DIR_ASSETS))
 