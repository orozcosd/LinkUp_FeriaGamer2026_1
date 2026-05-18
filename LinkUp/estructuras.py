"""
Estructuras de datos del juego LinkUp.

Implementa las tres estructuras requeridas por el laboratorio:
  - Grafo  : red social del juego (nodos = usuarios, aristas = conexiones)
  - Arbol  : árbol de decisiones para situaciones de bullying
  - ColaPrioridad : orden de propagación de eventos de odio
"""

import heapq
import math
import random


# ---------------------------------------------------------------------------
# 1) GRAFO
# ---------------------------------------------------------------------------
class Nodo:
    """Representa un 'usuario' de la red social."""
    TIPOS = ("neutro", "victima", "bully", "aliado", "central")

    def __init__(self, id_, tipo, x, y, nombre=""):
        self.id = id_
        self.tipo = tipo            # neutro | victima | bully | aliado | central
        self.x = x
        self.y = y
        self.nombre = nombre or f"User_{id_:02d}"
        self.estado = "activo"      # activo | resuelto | infectado
        self.salud = 100
        self.visitado = False

    def __repr__(self):
        return f"Nodo({self.id},{self.tipo},{self.estado})"


class Grafo:
    """Grafo no dirigido representado por listas de adyacencia."""

    def __init__(self):
        self.nodos = {}             # id -> Nodo
        self.aristas = {}           # id -> { id_vecino: {"muro": bool, "rota": bool} }

    # ----- API básica ------------------------------------------------------
    def agregar_nodo(self, nodo):
        self.nodos[nodo.id] = nodo
        self.aristas.setdefault(nodo.id, {})

    def agregar_arista(self, a, b, muro=False):
        if a == b:
            return
        self.aristas.setdefault(a, {})[b] = {"muro": muro, "rota": False}
        self.aristas.setdefault(b, {})[a] = {"muro": muro, "rota": False}

    def vecinos(self, id_):
        return list(self.aristas.get(id_, {}).keys())

    def arista_transitable(self, a, b):
        """¿Se puede pasar de a a b? (no es muro o el muro fue roto)."""
        info = self.aristas.get(a, {}).get(b)
        if info is None:
            return False
        return (not info["muro"]) or info["rota"]

    def romper_muro(self, a, b):
        if b in self.aristas.get(a, {}):
            self.aristas[a][b]["rota"] = True
            self.aristas[b][a]["rota"] = True

    # ----- Recorridos ------------------------------------------------------
    def bfs(self, origen):
        """BFS sólo por aristas transitables."""
        visit = {origen}
        cola = [origen]
        orden = []
        while cola:
            u = cola.pop(0)
            orden.append(u)
            for v in self.vecinos(u):
                if v not in visit and self.arista_transitable(u, v):
                    visit.add(v)
                    cola.append(v)
        return orden

    def camino_mas_corto(self, origen, destino):
        """BFS para ruta más corta entre dos nodos transitables."""
        if origen == destino:
            return [origen]
        prev = {origen: None}
        cola = [origen]
        while cola:
            u = cola.pop(0)
            if u == destino:
                break
            for v in self.vecinos(u):
                if v not in prev and self.arista_transitable(u, v):
                    prev[v] = u
                    cola.append(v)
        if destino not in prev:
            return None
        camino = []
        x = destino
        while x is not None:
            camino.append(x)
            x = prev[x]
        return list(reversed(camino))

    # ----- Generación aleatoria -------------------------------------------
    @classmethod
    def aleatorio(cls, n, prob_arista, prob_muro, ancho, alto,
                  prob_bully, prob_victima, margen=80):
        """
        Genera un grafo con disposición tipo 'fuerza' (aleatoria pero
        agradable) y garantiza conectividad mínima.
        """
        g = cls()
        cx, cy = ancho / 2, alto / 2
        radio = min(ancho, alto) / 2 - margen
        for i in range(n):
            ang = (2 * math.pi * i) / n + random.uniform(-0.2, 0.2)
            r = radio * random.uniform(0.55, 1.0)
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            # Decidir tipo
            roll = random.random()
            if i == 0:
                tipo = "central"
            elif roll < prob_bully:
                tipo = "bully"
            elif roll < prob_bully + prob_victima:
                tipo = "victima"
            elif roll < prob_bully + prob_victima + 0.15:
                tipo = "aliado"
            else:
                tipo = "neutro"
            g.agregar_nodo(Nodo(i, tipo, x, y))

        # Anillo base para asegurar conectividad
        for i in range(n):
            g.agregar_arista(i, (i + 1) % n,
                             muro=random.random() < prob_muro * 0.5)

        # Aristas adicionales aleatorias
        for i in range(n):
            for j in range(i + 2, n):
                if random.random() < prob_arista:
                    g.agregar_arista(i, j, muro=random.random() < prob_muro)
        return g


# ---------------------------------------------------------------------------
# 2) ÁRBOL DE DECISIONES
# ---------------------------------------------------------------------------
class NodoArbol:
    """
    Nodo del árbol de decisiones.
      - texto:   descripción de la situación o resultado
      - opciones: lista de tuplas (texto_opcion, hijo, efecto)
      - efecto:  dict con cambios al estado del juego (puntos, salud, etc.)
      - terminal: si es hoja (final de la situación)
    """
    def __init__(self, texto, opciones=None, efecto=None, terminal=False,
                 tipo_resultado="neutro"):
        self.texto = texto
        self.opciones = opciones or []
        self.efecto = efecto or {}
        self.terminal = terminal
        self.tipo_resultado = tipo_resultado  # bueno | neutro | malo

    def es_hoja(self):
        return self.terminal or not self.opciones


class ArbolDecisiones:
    """Contiene la raíz de un árbol de decisiones para una situación."""
    def __init__(self, raiz):
        self.raiz = raiz
        self.actual = raiz
        self.historial = []  # texto de opciones elegidas

    def elegir(self, indice):
        if self.actual.es_hoja():
            return self.actual
        if 0 <= indice < len(self.actual.opciones):
            texto_op, hijo, efecto = self.actual.opciones[indice]
            self.historial.append((texto_op, efecto))
            self.actual = hijo
        return self.actual

    def reiniciar(self):
        self.actual = self.raiz
        self.historial = []


# ---------------------------------------------------------------------------
# 3) COLA DE PRIORIDAD
# ---------------------------------------------------------------------------
class ColaPrioridad:
    """
    Cola de prioridad basada en heapq.
    Usada para propagar el 'virus del odio': los eventos con menor
    'tiempo' se ejecutan antes.
    """
    def __init__(self):
        self._heap = []
        self._contador = 0

    def push(self, prioridad, dato):
        self._contador += 1
        heapq.heappush(self._heap, (prioridad, self._contador, dato))

    def pop(self):
        if not self._heap:
            return None
        prioridad, _, dato = heapq.heappop(self._heap)
        return prioridad, dato

    def peek(self):
        if not self._heap:
            return None
        prioridad, _, dato = self._heap[0]
        return prioridad, dato

    def __len__(self):
        return len(self._heap)

    def vacia(self):
        return len(self._heap) == 0

    def listar(self):
        """Devuelve la lista ordenada (sin modificar la cola)."""
        return sorted([(p, d) for (p, _, d) in self._heap])
