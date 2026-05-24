"""
========================================================================
estructuras.py - ESTRUCTURAS DE DATOS DEL JUEGO
========================================================================
Este es el archivo ACADEMICO mas importante del proyecto: contiene las
TRES estructuras de datos requeridas por el laboratorio de Estructura
de Datos II:

  1) GRAFO         -> la red social del juego (nodos = usuarios,
                      aristas = conexiones entre ellos)
  2) ARBOL         -> arbol de decisiones para situaciones de bullying
                      (cada eleccion lleva a otra rama o a una hoja)
  3) COLA DE PRIORIDAD -> ordena los eventos de "propagacion del odio"
                          por tiempo (Min-Heap implementado con heapq)

IMPORTANTE: este archivo NO usa pygame ni nada visual. Es pura
estructura de datos. Eso permite testearlo independientemente del
juego y reutilizarlo en otros contextos. Sigue el principio de
"separar la logica de la presentacion".

Los algoritmos implementados son:
  - BFS (Breadth-First Search): recorrido en anchura del grafo
  - Camino mas corto: BFS aplicado a busqueda de ruta minima
  - Insercion y extraccion en cola de prioridad O(log n)
========================================================================
"""

import heapq
import math
import random


# ===========================================================================
# 1) GRAFO - La red social del juego
# ===========================================================================
class Nodo:
    """Representa un 'usuario' de la red social.

    Cada nodo tiene:
      - id: numero unico (sirve como llave en el diccionario)
      - tipo: que rol cumple en la red (bully, victima, etc.)
      - x, y: posicion en la pantalla (para dibujarlo)
      - nombre: como se llama el personaje (para mostrar al jugador)
      - estado: como esta ahora mismo (activo/infectado/resuelto)
      - salud: cuanta resistencia tiene
      - visitado: bandera auxiliar para algoritmos de recorrido
    """
    # Tipos validos de nodo. Esto es solo documentacion; Python no
    # lo enforza, pero sirve para que cualquiera vea de un vistazo
    # los valores posibles.
    TIPOS = ("neutro", "victima", "bully", "aliado", "central")

    def __init__(self, id_, tipo, x, y, nombre=""):
        self.id = id_
        self.tipo = tipo            # neutro | victima | bully | aliado | central
        self.x = x                  # coordenada X en pixeles
        self.y = y                  # coordenada Y en pixeles
        # Si no se da nombre, lo generamos automaticamente: "User_03", etc.
        # :02d formatea con 2 digitos y zero-padding (3 -> "03").
        self.nombre = nombre or f"User_{id_:02d}"
        self.estado = "activo"      # activo | resuelto | infectado
        self.salud = 100
        self.visitado = False       # usado por BFS/DFS

    def __repr__(self):
        """Representacion para debug. Sale cuando haces print(nodo)."""
        return f"Nodo({self.id},{self.tipo},{self.estado})"


class Grafo:
    """Grafo NO DIRIGIDO representado por listas de adyacencia.

    Estructura:
      - self.nodos:   diccionario id -> Nodo
      - self.aristas: diccionario id -> diccionario id_vecino -> info_arista

    info_arista es un dict con dos campos:
      - muro: True si la arista esta bloqueada (muro de odio)
      - rota: True si el muro fue roto con poder Voz Amplificada

    Por que listas de adyacencia (y no matriz)?
      - Mas eficiente en memoria cuando el grafo es disperso (pocas
        aristas comparado al maximo posible n*(n-1)/2). Nuestro grafo
        suele tener ~15-30 aristas con 10-16 nodos, asi que es ralo.
      - Iterar vecinos es O(grado) en vez de O(n).
    """

    def __init__(self):
        self.nodos = {}             # id -> Nodo
        self.aristas = {}           # id -> { id_vecino: {"muro": bool, "rota": bool} }

    # ----- API basica -----------------------------------------------------
    def agregar_nodo(self, nodo):
        """Anade un nodo al grafo. Su lista de vecinos arranca vacia."""
        self.nodos[nodo.id] = nodo
        # setdefault crea la entrada si no existe; si ya existe, la
        # respeta. Asi no perdemos aristas si el nodo ya tenia algunas.
        self.aristas.setdefault(nodo.id, {})

    def agregar_arista(self, a, b, muro=False):
        """Anade una arista bidireccional entre los nodos a y b.

        No agrega self-loops (si a == b, no hace nada). Como es no
        dirigido, agregamos la arista en AMBAS direcciones.
        """
        if a == b:
            return
        # Agregamos en ambos sentidos porque es no dirigido.
        # Cada arista almacena un dict con su estado (muro, rota).
        self.aristas.setdefault(a, {})[b] = {"muro": muro, "rota": False}
        self.aristas.setdefault(b, {})[a] = {"muro": muro, "rota": False}

    def vecinos(self, id_):
        """Devuelve la lista de IDs de los vecinos del nodo `id_`."""
        return list(self.aristas.get(id_, {}).keys())

    def arista_transitable(self, a, b):
        """Determina si se puede pasar de a a b.

        Una arista es transitable si:
          - No es muro, O
          - Es muro PERO fue rota (con Voz Amplificada).

        Devuelve False si no existe arista entre a y b.
        """
        info = self.aristas.get(a, {}).get(b)
        if info is None:
            return False
        return (not info["muro"]) or info["rota"]

    def romper_muro(self, a, b):
        """Marca el muro entre a y b como roto. Bidireccional."""
        if b in self.aristas.get(a, {}):
            self.aristas[a][b]["rota"] = True
            self.aristas[b][a]["rota"] = True

    # ----- Algoritmos de recorrido ----------------------------------------
    def bfs(self, origen):
        """BFS (Breadth-First Search): recorrido en anchura.

        Visita primero el origen, luego todos sus vecinos a distancia 1,
        luego todos a distancia 2, etc. Solo considera aristas
        TRANSITABLES (los muros bloquean el paso).

        Devuelve la lista de nodos en el orden en que se visitaron.

        Complejidad: O(V + E) donde V=nodos y E=aristas.
        """
        # Conjunto de nodos ya visitados (lookup O(1)).
        visit = {origen}
        # Cola FIFO: extraemos del frente, agregamos al final.
        cola = [origen]
        orden = []
        while cola:
            # pop(0) saca el primero. Es O(n) en listas Python, ideal
            # seria usar collections.deque para O(1), pero para grafos
            # pequenos da igual.
            u = cola.pop(0)
            orden.append(u)
            for v in self.vecinos(u):
                if v not in visit and self.arista_transitable(u, v):
                    visit.add(v)
                    cola.append(v)
        return orden

    def camino_mas_corto(self, origen, destino):
        """Encuentra el camino mas corto entre dos nodos.

        Usa BFS porque todas las aristas tienen el mismo peso (1).
        Si las aristas tuvieran pesos diferentes, habria que usar
        Dijkstra. Pero como aqui solo importa "menos saltos", BFS
        es suficiente y mas simple.

        Devuelve la lista de IDs del camino (incluye origen y destino),
        o None si no hay camino.
        """
        # Caso trivial: ya estamos en el destino.
        if origen == destino:
            return [origen]
        # prev[v] = de que nodo llegamos a v. Sirve para reconstruir
        # el camino cuando lleguemos al destino.
        prev = {origen: None}
        cola = [origen]
        while cola:
            u = cola.pop(0)
            if u == destino:
                break
            for v in self.vecinos(u):
                # Solo seguimos por aristas transitables y nodos sin visitar.
                if v not in prev and self.arista_transitable(u, v):
                    prev[v] = u
                    cola.append(v)
        # Si nunca llegamos al destino, no hay camino.
        if destino not in prev:
            return None
        # RECONSTRUCCION del camino: desde el destino, vamos saltando
        # hacia atras por prev[] hasta llegar al origen (None).
        camino = []
        x = destino
        while x is not None:
            camino.append(x)
            x = prev[x]
        # Lo invertimos para que vaya de origen a destino.
        return list(reversed(camino))

    # ----- Generacion aleatoria -------------------------------------------
    @classmethod
    def aleatorio(cls, n, prob_arista, prob_muro, ancho, alto,
                  prob_bully, prob_victima, margen=80):
        """Genera un grafo aleatorio de n nodos con disposicion radial.

        Es un classmethod (en vez de funcion suelta) para que se llame
        como Grafo.aleatorio(...). Devuelve un nuevo Grafo listo para
        jugar.

        Algoritmo:
          1) Coloca los nodos en un circulo (con jitter aleatorio para
             que no se vea perfectamente simetrico).
          2) Asigna tipo a cada nodo segun probabilidades.
          3) Crea un anillo base que conecta i con i+1, garantizando
             que el grafo este CONEXO (todos los nodos son alcanzables).
          4) Agrega aristas adicionales aleatorias para enriquecer.
        """
        g = cls()
        # Centro del area de juego.
        cx, cy = ancho / 2, alto / 2
        # Radio maximo del circulo donde colocaremos nodos.
        radio = min(ancho, alto) / 2 - margen
        for i in range(n):
            # Angulo equiespaciado + ruido para evitar simetria perfecta.
            ang = (2 * math.pi * i) / n + random.uniform(-0.2, 0.2)
            # Radio variable (55% a 100% del max) para que no esten
            # todos a la misma distancia del centro.
            r = radio * random.uniform(0.55, 1.0)
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            # DECISION DE TIPO: el primer nodo (i=0) siempre es central
            # porque ahi empieza el jugador. Los demas se sortean segun
            # probabilidades acumuladas.
            roll = random.random()
            if i == 0:
                tipo = "central"
            elif roll < prob_bully:
                tipo = "bully"
            elif roll < prob_bully + prob_victima:
                tipo = "victima"
            elif roll < prob_bully + prob_victima + 0.15:
                # 15% extra para aliados (ayudantes potenciales).
                tipo = "aliado"
            else:
                tipo = "neutro"
            g.agregar_nodo(Nodo(i, tipo, x, y))

        # ANILLO BASE: conecta i con (i+1) % n. Esto garantiza que el
        # grafo este conexo: peor caso, sigue siendo un ciclo.
        # Multiplicamos prob_muro * 0.5 para que el anillo sea mas
        # transitable que las aristas extra (que el jugador no se
        # quede sin caminos).
        for i in range(n):
            g.agregar_arista(i, (i + 1) % n,
                             muro=random.random() < prob_muro * 0.5)

        # ARISTAS EXTRA: para cada par (i, j) con j > i+1, sorteamos
        # si se conectan. j > i+1 evita reconectar pares ya conectados
        # por el anillo base.
        for i in range(n):
            for j in range(i + 2, n):
                if random.random() < prob_arista:
                    g.agregar_arista(i, j, muro=random.random() < prob_muro)
        return g


# ===========================================================================
# 2) ARBOL DE DECISIONES
# ===========================================================================
class NodoArbol:
    """Nodo del arbol de decisiones para situaciones de bullying.

    Cada nodo representa un punto del dialogo:
      - texto: lo que dice/describe el nodo
      - opciones: lista de tuplas (texto_opcion, hijo, efecto)
                  → cada opcion es una rama del arbol
      - efecto: dict con cambios al estado del juego (puntos, salud,
                resolver, poder, etc.) — se aplica solo en hojas
      - terminal: True si es hoja (final de la situacion)
      - tipo_resultado: "bueno" | "neutro" | "malo" — color del resultado

    Si opciones esta vacia O terminal=True, es una hoja.
    """
    def __init__(self, texto, opciones=None, efecto=None, terminal=False,
                 tipo_resultado="neutro"):
        self.texto = texto
        # `or []` evita el bug clasico de Python de usar [] como default
        # mutable: si fuera opciones=[], TODAS las instancias compartirian
        # la misma lista vacia.
        self.opciones = opciones or []
        self.efecto = efecto or {}
        self.terminal = terminal
        self.tipo_resultado = tipo_resultado  # bueno | neutro | malo

    def es_hoja(self):
        """True si es nodo terminal o no tiene opciones."""
        return self.terminal or not self.opciones


class ArbolDecisiones:
    """Contenedor del arbol con estado de navegacion.

    Mantiene:
      - raiz: el nodo inicial del arbol
      - actual: en que nodo estamos parados ahora
      - historial: lista de opciones que fuimos eligiendo

    Cuando el jugador elige una opcion, `actual` avanza al hijo
    correspondiente. Si llegamos a una hoja, `actual.es_hoja()` da True
    y el juego aplica `actual.efecto`.
    """
    def __init__(self, raiz):
        self.raiz = raiz
        self.actual = raiz
        # Para mostrar al final "elegiste estas opciones".
        self.historial = []

    def elegir(self, indice):
        """Avanza al hijo correspondiente al indice elegido.

        Si ya estamos en una hoja o el indice es invalido, no hace nada.
        Devuelve el nuevo nodo actual.
        """
        if self.actual.es_hoja():
            return self.actual
        if 0 <= indice < len(self.actual.opciones):
            # Desempacamos la tupla de la opcion.
            texto_op, hijo, efecto = self.actual.opciones[indice]
            self.historial.append((texto_op, efecto))
            self.actual = hijo
        return self.actual

    def reiniciar(self):
        """Vuelve al inicio del arbol. Util al reabrir una situacion."""
        self.actual = self.raiz
        self.historial = []


# ===========================================================================
# 3) COLA DE PRIORIDAD - Min-Heap basado en heapq
# ===========================================================================
class ColaPrioridad:
    """Cola de prioridad (Min-Heap) construida sobre heapq.

    Sirve para propagar el "virus del odio" en el juego: los eventos
    con MENOR `tiempo` se ejecutan ANTES. Asi el juego sabe en que
    orden disparar las propagaciones.

    Complejidad:
      - push: O(log n)
      - pop:  O(log n)
      - peek: O(1)

    Detalle de implementacion: heapq compara tuplas elemento por
    elemento. Si dos tuplas tienen la misma prioridad (mismo tiempo),
    Python intentaria comparar el dato, que puede ser un dict y crashear.
    Por eso anadimos un CONTADOR como segundo elemento de la tupla:
    actua como tie-breaker estable, asi los datos nunca se comparan.
    """
    def __init__(self):
        # Internamente es una lista que heapq mantiene ordenada como heap.
        self._heap = []
        # Contador monotono creciente para desempate (FIFO entre empates).
        self._contador = 0

    def push(self, prioridad, dato):
        """Anade un elemento con prioridad dada. Menor prioridad = primero."""
        self._contador += 1
        # Tupla (prioridad, contador, dato). El contador asegura que
        # los datos nunca se comparen entre si.
        heapq.heappush(self._heap, (prioridad, self._contador, dato))

    def pop(self):
        """Extrae y devuelve (prioridad, dato) del elemento con MENOR prioridad."""
        if not self._heap:
            return None
        prioridad, _, dato = heapq.heappop(self._heap)
        return prioridad, dato

    def peek(self):
        """Mira el elemento con menor prioridad sin extraerlo."""
        if not self._heap:
            return None
        prioridad, _, dato = self._heap[0]
        return prioridad, dato

    def __len__(self):
        """Permite usar len(cola)."""
        return len(self._heap)

    def vacia(self):
        """True si no hay elementos pendientes."""
        return len(self._heap) == 0

    def listar(self):
        """Devuelve la lista ordenada por prioridad sin modificar la cola.

        Util para el HUD: "estos son los proximos eventos en orden".
        Notar que heap[0] es el menor, pero el resto NO esta ordenado
        en el array (es un heap, no una lista ordenada). Por eso
        hacemos sorted() para mostrarlo.
        """
        return sorted([(p, d) for (p, _, d) in self._heap])
