"""
========================================================================
recursos.py - CARGADOR DE ASSETS GRAFICOS
========================================================================
Este modulo se encarga de cargar las imagenes desde la carpeta
`assets/` y mantenerlas cacheadas en memoria. Tiene DOS caracteristicas
clave que lo hacen util:

  1) CACHE: una vez que se carga una imagen, no se vuelve a leer del
     disco. Cargar imagenes es lento (acceso a disco + decodificacion),
     asi que cachearlas mejora muchisimo el rendimiento. Tambien
     cacheamos las versiones escaladas, porque pygame.transform.smooth-
     scale tambien es caro y se llama muchas veces por frame.

  2) FALLBACK SEGURO: si una imagen NO existe, el metodo devuelve None
     en vez de explotar. Esto es CRITICO porque el juego esta disenado
     para correr SIN ningun PNG si hace falta: en ese caso, cada parte
     del codigo que pide una imagen recibe None y cae a un dibujo
     procedural (circulos, simbolos, etc).

CONVENCION DE NOMBRES en assets/ (sin distinguir mayusculas):
    fondo_menu.png, fondo_mapa.png
    LinkUp_Logo.png   (o logo.png)
    nodo_aliado.png, nodo_bully.png, nodo_victima.png, nodo_neutro.png,
    nodo_central.png, nodo_infectado.png, nodo_resuelto.png
    nodo_<skin>.png    para el avatar circular del jugador
    skin_<skin>.png    para el cuerpo completo en el selector
    boton_<accion>.png para los botones (boton_jugar, boton_host, etc)
========================================================================
"""

import os
import pygame


# Calculamos la ruta ABSOLUTA a la carpeta assets/ relativa a este
# archivo. Usamos os.path.abspath para que funcione sin importar
# desde donde se ejecute el script (por ejemplo, desde otra carpeta).
DIR_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


class Recursos:
    """Cargador con cache. Una sola instancia por juego.

    Patron simple: dos diccionarios.
      - cache_originales: nombre -> Surface (o None si no existe)
      - cache_escalado:   (nombre, w, h) -> Surface escalada
    """

    # Extensiones de imagen que probamos al buscar un archivo.
    # Buscar por varias variantes hace el sistema robusto a errores
    # tipograficos comunes en los nombres (.png vs .PNG, .jpg, etc).
    EXTENSIONES = (".png", ".PNG", ".jpg", ".jpeg")

    def __init__(self):
        # Cache de imagenes recien cargadas del disco.
        # Si el valor es None significa "ya busque esta imagen y no
        # existe", asi no la volvemos a buscar cada frame.
        self.cache_originales = {}
        # Cache de versiones escaladas. La clave es (nombre, w, h)
        # porque la misma imagen puede pedirse a diferentes tamanos.
        self.cache_escalado = {}

    # ------------------------------------------------------------------
    # NUCLEO DE CARGA Y ESCALADO
    # ------------------------------------------------------------------
    def cargar(self, nombre):
        """Devuelve la Surface cargada o None si no existe.

        Busca el archivo en assets/ probando las extensiones definidas
        en EXTENSIONES, ignorando mayusculas (asi tanto `Logo.png`
        como `logo.PNG` funcionan).
        """
        # Si ya esta en cache (sea Surface o None), devolvemos.
        if nombre in self.cache_originales:
            return self.cache_originales[nombre]
        # Lista de nombres candidatos: "Logo.png", "Logo.PNG", "Logo.jpg"...
        candidatos = [nombre + ext for ext in self.EXTENSIONES]
        if os.path.isdir(DIR_ASSETS):
            try:
                # Construimos un dict {nombre_minusculas: nombre_real}
                # para hacer matching case-insensitive.
                listado = {f.lower(): f for f in os.listdir(DIR_ASSETS)}
            except OSError:
                # Permisos malos o algo raro: tratamos como vacio.
                listado = {}
            for cand in candidatos:
                real = listado.get(cand.lower())
                if real:
                    try:
                        ruta = os.path.join(DIR_ASSETS, real)
                        # convert_alpha() optimiza la imagen para
                        # blitting rapido con canal alpha (transparencia).
                        # Es MUCHO mas rapido que dejar la imagen "cruda".
                        img = pygame.image.load(ruta).convert_alpha()
                        self.cache_originales[nombre] = img
                        return img
                    except pygame.error:
                        # Imagen corrupta o formato no soportado: ignoramos.
                        pass
        # No la encontramos: cacheamos el None para no volver a buscar.
        self.cache_originales[nombre] = None
        return None

    def escalar(self, nombre, w, h):
        """Devuelve la imagen `nombre` escalada a (w, h).

        Si ya la habiamos escalado a ese tamano, devuelve la version
        cacheada. Esto importa porque smoothscale es caro y se llama
        cada frame para dibujar los nodos del grafo.
        """
        if w <= 0 or h <= 0:
            # Tamano invalido: nada que escalar.
            return None
        clave = (nombre, int(w), int(h))
        if clave in self.cache_escalado:
            return self.cache_escalado[clave]
        img = self.cargar(nombre)
        if img is None:
            return None
        try:
            # smoothscale usa interpolacion bilineal: mejor calidad
            # que scale() pero un pelin mas lento. Cacheado, da igual.
            escalada = pygame.transform.smoothscale(img, (int(w), int(h)))
        except pygame.error:
            return None
        self.cache_escalado[clave] = escalada
        return escalada

    # ------------------------------------------------------------------
    # HELPERS DE ALTO NIVEL
    # Estos metodos envuelven cargar/escalar con la logica especifica
    # de cada tipo de recurso (logo, nodo, skin). Hacen el codigo
    # cliente mas legible: en vez de hacer recursos.cargar("nodo_bully")
    # haces recursos.imagen_nodo("bully", "activo").
    # ------------------------------------------------------------------
    def fondo(self, nombre, w, h):
        """Atajo para cargar y escalar un fondo a las dimensiones de
        la pantalla. Solo un alias semantico."""
        return self.escalar(nombre, w, h)

    def logo(self):
        """Logo principal del juego. Acepta varios nombres comunes
        (LinkUp_Logo, linkup_logo, logo_linkup, logo) para que sea
        robusto al cambiar el archivo."""
        for n in ("LinkUp_Logo", "linkup_logo", "logo_linkup", "logo"):
            img = self.cargar(n)
            if img:
                return img
        return None

    def imagen_nodo(self, tipo, estado):
        """Selecciona la imagen del nodo segun estado y tipo.

        Prioridad: el ESTADO manda sobre el TIPO. Si un nodo esta
        infectado o resuelto, usamos esa imagen aunque el tipo sea
        bully o victima. Solo si esta "activo" volvemos a usar la
        imagen segun tipo.

        Esto permite que cualquier nodo se vea infectado/resuelto
        consistentemente, independiente de su origen.
        """
        if estado == "resuelto":
            img = self.cargar("nodo_resuelto")
            if img:
                return img
        if estado == "infectado":
            img = self.cargar("nodo_infectado")
            if img:
                return img
        # Fallback: imagen segun tipo (bully, victima, neutro, etc.)
        return self.cargar(f"nodo_{tipo}")

    def avatar_skin(self, skin_nombre):
        """Avatar circular pequeno del jugador (para el mapa)."""
        return self.cargar(f"nodo_{skin_nombre.lower()}")

    def skin_completo(self, skin_nombre):
        """Imagen de cuerpo completo del skin (para el selector
        de configuracion). Cada skin tiene su pose grande."""
        return self.cargar(f"skin_{skin_nombre.lower()}")

    # ------------------------------------------------------------------
    # DIAGNOSTICO
    # ------------------------------------------------------------------
    def listar_disponibles(self):
        """Devuelve la lista de archivos que hay en assets/.
        Util para debug ('por que no se ve mi imagen?')."""
        if not os.path.isdir(DIR_ASSETS):
            return []
        return sorted(os.listdir(DIR_ASSETS))
