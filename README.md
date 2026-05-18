# LinkUp — Guardianes del Nexo

Videojuego de estrategia y aventura desarrollado en Python + pygame para la
asignatura **Estructura de Datos II** (Laboratorio 3, Universidad del Norte).
Aborda el tema del **bullying y ciberacoso** invitando al jugador a recorrer
una red social (grafo) ayudando a víctimas, neutralizando acosadores y
construyendo puentes de empatía.

---

## Instalación

```bash
pip install -r requirements.txt
python main.py
```

Requiere **Python 3.9+** y **pygame 2.5+**.

---

## Cómo jugar

Eres un **Guardián del Nexo** en CiberNexo. Tu misión:

1. Recorrer los nodos del grafo (cada nodo = un usuario de la red social).
2. Al llegar a un nodo con una situación de ciberbullying se abre un
   **árbol de decisiones**: elige la respuesta más empática.
3. Ganarás puntos, salud para la comunidad y poderes (Escudo de Empatía,
   Red de Apoyo, Voz Amplificada).
4. La **cola de prioridad** controla el orden en que se propaga el "virus
   del odio". ¡Detenlo antes de que infecte al nodo central!
5. Algunas aristas son **muros de odio**: rómpelos con Voz Amplificada (tecla **P**).

### Controles

| Tecla   | Acción                                                  |
|---------|---------------------------------------------------------|
| Click   | Mover a un nodo vecino / Seleccionar opción / Botones   |
| 1, 2, 3 | Elegir opción del árbol de decisiones                   |
| P       | Usar el poder más relevante en tu posición              |
| R       | Reiniciar partida (solo modo individual)                |
| ESC     | Volver al menú principal                                |
| F1      | Pantalla de ayuda                                       |
| F2      | Cambiar a modo daltónico / normal                       |
| F3      | Cambiar tamaño de texto (pequeño / mediano / grande)    |

---

## Modo multijugador (cliente–servidor con sockets)

LinkUp soporta partidas cooperativas de 2 a 4 jugadores en red local.

* En la computadora **host**: menú → *Hospedar partida*. Aparecerá la IP y
  el puerto. Comparte la IP con los demás jugadores.
* En las computadoras **cliente**: menú → *Unirse a partida* → escribir IP
  y *Conectar*.
* Cuando todos estén conectados, el host pulsa **Iniciar partida**.

La comunicación usa sockets TCP con un protocolo JSON-line simple. Toda la
lógica se mantiene del lado del servidor; los clientes envían acciones y
reciben el estado del juego.

---

## Estructuras de datos empleadas

| Estructura            | Archivo / Clase                | Uso en el juego                                        |
|-----------------------|--------------------------------|--------------------------------------------------------|
| **Grafo**             | `estructuras.py` → `Grafo`     | Red social (nodos = usuarios, aristas = amistades)     |
| **Árbol**             | `estructuras.py` → `ArbolDecisiones` | Árbol de decisiones de cada situación de bullying |
| **Cola de prioridad** | `estructuras.py` → `ColaPrioridad`   | Orden de propagación del odio (heap binario)      |

---

## Inclusión / accesibilidad

* **Modo daltónico** (F2): paleta alterna que evita el contraste rojo-verde.
* **Texto ajustable** (F3): tres tamaños de fuente.
* **Skins diversos**: 6 skins con colores, símbolos y nombres variados.
* **Iconos** además de colores para identificar tipos de nodos.
* **Audio descriptivo**: efectos sonoros generados proceduralmente para cada
  acción (hover, click, evento, victoria, etc.) — no requiere archivos
  externos, facilita el uso si faltan recursos.
* Texto narrativo claro, sin preguntas tipo trivia: situaciones
  contextuales con decisiones empáticas.

---

## Estructura del proyecto

```
LinkUp/
├── main.py             # Punto de entrada
├── settings.py         # Constantes, paletas, configuración
├── estructuras.py      # Grafo, ÁrbolDecisiones, ColaPrioridad
├── situaciones.py      # Plantillas de árboles de decisión (situaciones)
├── audio.py            # Sonidos generados proceduralmente
├── red.py              # Servidor / Cliente (sockets)
├── juego.py            # Lógica principal y pantallas pygame
├── requirements.txt
└── README.md
```

---

## Población objetivo

* **Principal:** Jóvenes de 12–17 años.
* **Extensión:** versión simplificada (texto grande, modo daltónico, narrador
  visual y audio) para niños de 8–11 años.

## Componente aleatorio

* Topología del grafo generada aleatoriamente en cada partida.
* Distribución de tipos de nodo (víctima, acosador, aliado, neutro) aleatoria.
* Eventos negativos cuya **prioridad temporal** y nodo objetivo son aleatorios.
* Plantillas de situaciones elegidas aleatoriamente.

## Componentes que dependen de habilidad del jugador

* Decisiones del árbol (empáticas vs. impulsivas).
* Uso estratégico de poderes (cuándo y dónde).
* Planificación de la ruta por el grafo para llegar antes que el odio.

---

## Créditos

Proyecto desarrollado como Laboratorio 3 de Estructura de Datos II.
Inspirado en las recomendaciones de juegos contra el ciberacoso del CONICET,
SENA y UCM.
