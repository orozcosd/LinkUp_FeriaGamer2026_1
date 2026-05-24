"""
========================================================================
situaciones.py - GENERADOR DE SITUACIONES DE CIBERBULLYING
========================================================================
Este archivo contiene TODAS las situaciones narrativas que el jugador
puede encontrar al visitar un nodo del grafo. Cada situacion es un
ARBOL DE DECISIONES (usando ArbolDecisiones de estructuras.py).

A diferencia de un trivia con respuestas correctas/incorrectas, aqui
NO hay respuestas perfectas: hay escenarios reales de bullying donde
el jugador escoge una accion como Guardian del Nexo, y cada eleccion
tiene consecuencias (mas o menos buenas, pero pocas veces sin coste).

CADA SITUACION es una funcion que devuelve la raiz de un arbol. La
raiz tiene varias opciones, y cada opcion lleva a:
  - una hoja directa con un resultado (caso simple)
  - otro nodo con MAS opciones (dialogo de 2+ pasos)

EFECTOS POSIBLES en una hoja:
  - puntos:    int (positivos o negativos para el jugador)
  - salud:     int (afecta salud de la comunidad)
  - resolver:  bool (marca el nodo del grafo como "resuelto")
  - liberar:   bool (libera el nodo, similar a resolver)
  - poder:     str (otorga un poder al jugador: escudo_empatia,
                    red_apoyo, voz_amplificada)

Las situaciones se asignan ALEATORIAMENTE a los nodos del grafo
segun su tipo: las victimas reciben situaciones de victima, los
bullies reciben situaciones de bully, etc. Vease PLANTILLAS_POR_TIPO
al final del archivo.
========================================================================
"""

import random
from estructuras import NodoArbol, ArbolDecisiones


# ---------------------------------------------------------------------------
# HELPER PRIVADO
# ---------------------------------------------------------------------------
# _hoja() crea un NodoArbol terminal con efecto. Esto evita repetir
# la palabra terminal=True en todas las hojas del archivo y hace que
# las definiciones de situacion sean mas legibles.
def _hoja(texto, tipo="bueno", **efecto):
    """Crea un NodoArbol terminal (hoja) con texto, tipo de resultado
    y efectos pasados como kwargs.

    Ejemplo: _hoja("Genial", tipo="bueno", puntos=20, salud=8)
    """
    return NodoArbol(texto, terminal=True, efecto=efecto, tipo_resultado=tipo)


# ===========================================================================
# SITUACIONES PARA VICTIMAS / NEUTROS / CENTRAL
# ===========================================================================
# Cada funcion recibe el `nombre` del personaje del nodo (para que el
# texto sea personalizado: "Camila esta recibiendo amenazas..." en
# lugar de un generico "Una persona esta recibiendo amenazas").

def situacion_rumor_falso(nombre):
    """Situacion clasica: un rumor falso se viraliza sobre alguien.

    3 opciones: reportar (mejor), apoyar en privado (neutro),
    ignorar (malo). La rama de reportar enseña la importancia de
    la verificacion de hechos en redes sociales.
    """
    raiz = NodoArbol(
        f"Detectas que un rumor falso sobre {nombre} se esta viralizando.\n"
        "Los mensajes acumulan likes y comentarios crueles. Que haces?"
    )

    # Las 3 hojas (resultados terminales) creadas con _hoja().
    # Notar como cada una tiene tipo (bueno/neutro/malo) y efectos
    # numericos en puntos y salud.
    op1_hijo = _hoja(
        f"Detuviste la cadena. {nombre} recupera la confianza y la comunidad\n"
        "aprende a verificar antes de compartir.",
        tipo="bueno",
        puntos=20, salud=8, resolver=True
    )
    op2_hijo = _hoja(
        f"Hablar con {nombre} la fortalece, pero el rumor sigue circulando.\n"
        "La salud de la red baja un poco.",
        tipo="neutro",
        puntos=5, salud=-3
    )
    op3_hijo = _hoja(
        "Ignorar el problema permite que el rumor llegue a mas nodos.\n"
        "La comunidad se debilita.",
        tipo="malo",
        puntos=-10, salud=-12
    )

    # Las opciones son tuplas: (texto_visible, hijo, efecto_intermedio).
    # El efecto intermedio aqui es {} porque solo aplicamos efectos en
    # las hojas, no al elegir el camino.
    raiz.opciones = [
        ("Reportar la publicacion y pedir verificacion de hechos.",
         op1_hijo, {}),
        (f"Escribir a {nombre} para apoyarla en privado.",
         op2_hijo, {}),
        ("Ignorar: no es tu problema.",
         op3_hijo, {}),
    ]
    return raiz


def situacion_acoso_directo(nombre):
    """Acoso en comentarios publicos. Incluye un sub-arbol de 2 niveles
    para la opcion buena (defender publicamente + reportar formalmente),
    mostrando que las decisiones complejas pueden tener etapas."""
    raiz = NodoArbol(
        f"{nombre} esta recibiendo mensajes ofensivos en una publicacion.\n"
        "Varios usuarios se estan sumando al ataque. Como respondes?"
    )

    # Sub-arbol: si elegimos "defender", se abre otra decision sobre
    # si ademas reportamos. Esto ensena que actuar bien tiene capas.
    sub_bueno = NodoArbol(
        "Llamaste la atencion sobre el acoso. Otros aliados aparecen.\n"
        "Quieres ademas reportar al acosador principal?"
    )
    sub_bueno.opciones = [
        ("Si, reportarlo formalmente.",
         _hoja("Acosador suspendido. Nodo liberado. Excelente trabajo!",
               tipo="bueno", puntos=30, salud=12, resolver=True,
               poder="escudo_empatia"),
         {}),
        ("No, basta con la defensa publica.",
         _hoja("Buena accion, pero el acosador podria volver.",
               tipo="neutro", puntos=15, salud=5, resolver=True),
         {}),
    ]

    raiz.opciones = [
        ("Comentar con empatia defendiendo a la victima.",
         sub_bueno, {}),
        ("Responder al acosador con insultos.",
         _hoja("El conflicto escala. Ahora hay dos focos de odio.",
               tipo="malo", puntos=-15, salud=-15),
         {}),
        ("Bloquear silenciosamente y seguir.",
         _hoja(f"{nombre} sigue sintiendose sola. Salud de la red baja.",
               tipo="neutro", puntos=-5, salud=-8),
         {}),
    ]
    return raiz


def situacion_exclusion(nombre):
    """Exclusion social en grupos digitales. La opcion buena es
    proactiva: crear un nuevo grupo inclusivo en lugar de pelear
    con el grupo excluyente."""
    raiz = NodoArbol(
        f"Un grupo del chat ha sacado a {nombre} sin razon.\n"
        f"{nombre} se entera por capturas que circulan. Que haces?"
    )
    raiz.opciones = [
        ("Crear un nuevo grupo inclusivo e invitar a aliados.",
         _hoja("Construiste un puente de empatia! Nueva red de apoyo activa.",
               tipo="bueno", puntos=25, salud=10, resolver=True,
               poder="red_apoyo"),  # Premio: poder Red de Apoyo
         {}),
        ("Confrontar al grupo en publico.",
         _hoja("Conflicto abierto. Algunos cambian de opinion, otros no.",
               tipo="neutro", puntos=8, salud=-2),
         {}),
        ("No intervenir.",
         _hoja(f"{nombre} se aisla aun mas. La red se debilita.",
               tipo="malo", puntos=-12, salud=-10),
         {}),
    ]
    return raiz


def situacion_suplantacion(nombre):
    """Suplantacion de identidad: alguien crea una cuenta falsa.
    Ensena la importancia de actuar rapido y reportar formalmente."""
    raiz = NodoArbol(
        f"Alguien creo una cuenta falsa de {nombre} publicando contenido\n"
        "ofensivo en su nombre. Como actuas?"
    )
    raiz.opciones = [
        ("Reportar la cuenta y avisar a amistades reales.",
         _hoja("La cuenta falsa fue suspendida. La identidad real protegida.",
               tipo="bueno", puntos=25, salud=8, resolver=True,
               poder="voz_amplificada"),
         {}),
        (f"Escribir un post explicando que es falso.",
         _hoja("La aclaracion funciona parcialmente; algunos siguen creyendo.",
               tipo="neutro", puntos=10, salud=2),
         {}),
        ("Esperar a ver que pasa.",
         _hoja("La cuenta falsa hace mas dano. Nodo infectado.",
               tipo="malo", puntos=-15, salud=-15),
         {}),
    ]
    return raiz


def situacion_aliado(nombre):
    """Encuentro con un aliado potencial. Las tres opciones son
    relativamente positivas: ensena que confiar puede ser bueno
    pero tambien que la precaucion tiene su lugar."""
    raiz = NodoArbol(
        f"{nombre} te ofrece ayuda como aliado/a.\n"
        "Tiene experiencia neutralizando rumores. Aceptas?"
    )
    raiz.opciones = [
        ("Si, sumarlo/a a la red de apoyo.",
         _hoja(f"{nombre} se une! Recibes el poder Red de Apoyo +1.",
               tipo="bueno", puntos=15, salud=5, resolver=True,
               poder="red_apoyo"),
         {}),
        ("Preguntar mas antes de aceptar.",
         _hoja("Buena precaucion. Se une despues de una conversacion honesta.",
               tipo="bueno", puntos=12, salud=3, resolver=True),
         {}),
        ("Rechazar la oferta.",
         _hoja("Pierdes una oportunidad de fortalecer la red.",
               tipo="neutro", puntos=-3),
         {}),
    ]
    return raiz


# ===========================================================================
# SITUACIONES PARA BULLIES
# ===========================================================================
# Estas son mas complejas y dramaticas: representan los casos mas
# graves de bullying. Las consecuencias positivas y negativas son
# tambien mas grandes (mayor riesgo, mayor recompensa).

def situacion_bully_amenazas(nombre):
    """Amenazas violentas via mensajes privados. La rama buena enseña
    a recolectar evidencia ANTES de reportar — es lo que recomiendan
    los expertos en seguridad digital."""
    raiz = NodoArbol(
        f"{nombre} esta enviando amenazas violentas por mensajes privados\n"
        "a varios miembros de la red. Las victimas tienen miedo. Que haces?"
    )
    # Sub-arbol: ya con la evidencia recolectada, segunda decision.
    sub_evidencia = NodoArbol(
        "Recolectaste capturas como evidencia. Como procedes ahora?"
    )
    sub_evidencia.opciones = [
        ("Reportar a las autoridades junto con las victimas.",
         _hoja(f"{nombre} es sancionado/a. Las victimas se sienten protegidas.",
               tipo="bueno", puntos=35, salud=18, resolver=True,
               poder="escudo_empatia"), {}),
        ("Enviar la evidencia solo a moderadores de la plataforma.",
         _hoja("La cuenta es suspendida temporalmente. Alivio parcial.",
               tipo="bueno", puntos=20, salud=10, resolver=True), {}),
    ]
    raiz.opciones = [
        ("Ayudar a las victimas a guardar evidencia antes de actuar.", sub_evidencia, {}),
        ("Confrontar publicamente a quien amenaza.",
         _hoja("La amenaza se intensifica y aparecen mas cuentas hostiles.",
               tipo="malo", puntos=-18, salud=-15), {}),
        ("Esperar a ver si se detiene solo/a.",
         _hoja("Las amenazas escalan. Una victima abandona la red.",
               tipo="malo", puntos=-25, salud=-20), {}),
    ]
    return raiz


def situacion_bully_doxxing(nombre):
    """Doxxing: publicar datos personales de la victima para incitar
    al hostigamiento. Es un crimen real. La opcion buena es actuar
    YA: pedir eliminacion masiva."""
    raiz = NodoArbol(
        f"{nombre} publico la direccion y el telefono de una victima\n"
        "para incitar a otros a hostigarla. La informacion ya se difunde."
    )
    raiz.opciones = [
        ("Reportar masivamente el post y avisar a la victima de inmediato.",
         _hoja("Eliminan la publicacion a tiempo. La victima cambia ajustes de privacidad.",
               tipo="bueno", puntos=30, salud=14, resolver=True,
               poder="voz_amplificada"), {}),
        ("Pedir a la comunidad que no comparta ni interactue con el post.",
         _hoja("Reduces el alcance, pero algunas capturas siguen circulando.",
               tipo="neutro", puntos=8, salud=-2), {}),
        ("Responder al post pidiendole que la borre.",
         _hoja(f"{nombre} se burla y sube mas datos. Situacion empeora.",
               tipo="malo", puntos=-20, salud=-18), {}),
    ]
    return raiz


def situacion_bully_grupo(nombre):
    """Bully grupal: lidera un grupo que ataca coordinadamente.
    La opcion buena ensena que organizar a la comunidad ANTES del
    ataque es mas efectivo que enfrentar al lider directamente."""
    raiz = NodoArbol(
        f"{nombre} lidera un grupo que ataca coordinadamente a un usuario\n"
        "cada semana. Hoy eligieron a su proxima victima. Como respondes?"
    )
    sub_aliados = NodoArbol(
        "Reunes aliados para una contracampana. Que enfoque eliges?"
    )
    sub_aliados.opciones = [
        ("Lanzar una campana positiva visibilizando a la victima con respeto.",
         _hoja("La narrativa cambia. El grupo pierde seguidores y se disuelve.",
               tipo="bueno", puntos=35, salud=16, resolver=True,
               poder="red_apoyo"), {}),
        ("Hablar uno a uno con miembros del grupo para que se retiren.",
         _hoja("Tres integrantes se salen. El grupo pierde fuerza.",
               tipo="bueno", puntos=22, salud=10, resolver=True), {}),
    ]
    raiz.opciones = [
        ("Organizar a la comunidad antes de que ocurra el ataque.", sub_aliados, {}),
        ("Enfrentar directamente al lider del grupo.",
         _hoja("El grupo te convierte en su nuevo objetivo.",
               tipo="malo", puntos=-22, salud=-18), {}),
        ("Avisar solo a la victima para que se proteja.",
         _hoja("La victima se protege, pero el grupo encuentra otra.",
               tipo="neutro", puntos=-5, salud=-8), {}),
    ]
    return raiz


def situacion_bully_chantaje(nombre):
    """Sextorsion / chantaje con fotos privadas. Caso muy grave que
    requiere intervencion adulta. La opcion buena recompensa
    fuertemente porque hace lo correcto (no ceder al chantaje)."""
    raiz = NodoArbol(
        f"{nombre} amenaza con publicar fotos privadas de un companero/a\n"
        "si no hace lo que pide. La victima entro en panico."
    )
    raiz.opciones = [
        ("Acompanar a la victima a hablar con un adulto de confianza y reportar.",
         _hoja("La victima recibe apoyo real. El chantaje se detiene legalmente.",
               tipo="bueno", puntos=40, salud=20, resolver=True,
               poder="escudo_empatia"), {}),
        ("Asesorarle para que no ceda y bloquee de inmediato.",
         _hoja("La victima se siente acompanada, pero la presion sigue.",
               tipo="neutro", puntos=10, salud=2), {}),
        ("Recomendar que ceda para que no publique nada.",
         _hoja(f"{nombre} pide mas cada vez. El dano se profundiza.",
               tipo="malo", puntos=-30, salud=-22), {}),
    ]
    return raiz


def situacion_bully_provocacion(nombre):
    """Provocador clasico: busca que alguien explote para victimizarse.
    La opcion buena es NO alimentar al troll (estrategia comprobada
    en moderacion de comunidades online)."""
    raiz = NodoArbol(
        f"{nombre} publica provocaciones constantes intentando que alguien\n"
        "reaccione mal y quede como agresor. Es una trampa visible."
    )
    raiz.opciones = [
        ("Educar a la comunidad: no alimentar al provocador, reportar y silenciar.",
         _hoja("Sin publico, las provocaciones pierden sentido. Nodo aislado.",
               tipo="bueno", puntos=25, salud=12, resolver=True,
               poder="voz_amplificada"), {}),
        ("Responder con humor para desactivar la provocacion.",
         _hoja(f"Funciona a medias: {nombre} cambia de tactica.",
               tipo="neutro", puntos=8, salud=2), {}),
        ("Discutir punto por punto en los comentarios.",
         _hoja("Le das visibilidad. Aparecen mas bullies imitadores.",
               tipo="malo", puntos=-15, salud=-12), {}),
    ]
    return raiz


def situacion_bully_anonimo(nombre):
    """Cuentas anonimas con patron sospechoso. La opcion buena ensena
    a investigar CON CALMA antes de exponer publicamente — los
    linchamientos digitales sin pruebas son tambien una forma de odio."""
    raiz = NodoArbol(
        f"Cuentas anonimas atacan a varios usuarios. Se sospecha que {nombre}\n"
        "esta detras de todas. Como manejas la incertidumbre?"
    )
    sub_invest = NodoArbol(
        "Investigaste con cuidado: patrones de escritura coinciden. Que haces?"
    )
    sub_invest.opciones = [
        ("Compartir evidencia con moderacion sin exponer publicamente.",
         _hoja("Las cuentas falsas caen. Se evita linchamiento injusto.",
               tipo="bueno", puntos=30, salud=14, resolver=True,
               poder="red_apoyo"), {}),
        ("Exponer a {nombre} publicamente con la evidencia.",
         _hoja("Aciertas, pero se genera una caza de brujas. La red se polariza.",
               tipo="neutro", puntos=5, salud=-5), {}),
    ]
    raiz.opciones = [
        ("Recolectar evidencia con calma antes de acusar.", sub_invest, {}),
        ("Acusar de inmediato basandote en la sospecha.",
         _hoja("La acusacion sin pruebas se vuelve en tu contra.",
               tipo="malo", puntos=-18, salud=-12), {}),
        ("Ignorar el patron: cada cuenta por separado.",
         _hoja("Los ataques continuan sin freno. Mas victimas afectadas.",
               tipo="malo", puntos=-15, salud=-15), {}),
    ]
    return raiz


def situacion_bully_arrepentido(nombre):
    """Caso especial: un acosador parece arrepentido. La situacion
    ensena que la rehabilitacion es posible pero requiere acciones
    concretas (disculpas publicas, distancia), no solo palabras."""
    raiz = NodoArbol(
        f"{nombre}, antes acosador/a, escribe que quiere cambiar.\n"
        "Pide perdon a la comunidad. Confias?"
    )

    sub_dialogo = NodoArbol(
        "Abres un dialogo. Que pides como muestra de cambio?"
    )
    sub_dialogo.opciones = [
        ("Que pida disculpas publicas a las victimas.",
         _hoja("Disculpa publica aceptada. Nodo transformado en aliado.",
               tipo="bueno", puntos=30, salud=15, resolver=True),
         {}),
        ("Que se mantenga lejos del foro un tiempo.",
         _hoja("Decision prudente. La comunidad respira tranquila.",
               tipo="bueno", puntos=18, salud=8, resolver=True),
         {}),
    ]

    raiz.opciones = [
        ("Darle una segunda oportunidad mediante dialogo.",
         sub_dialogo, {}),
        ("Rechazar: las victimas son lo primero.",
         _hoja("Proteges a las victimas. Decision valida y segura.",
               tipo="neutro", puntos=10, salud=4, resolver=True),
         {}),
        ("Confiar sin condiciones.",
         _hoja("Vuelve a acosar a los pocos dias. La red sufre.",
               tipo="malo", puntos=-20, salud=-15),
         {}),
    ]
    return raiz


# ===========================================================================
# API PUBLICA - Como otros modulos crean situaciones
# ===========================================================================

# Diccionario que mapea tipo_de_nodo -> lista de funciones-plantilla.
# Cuando un nodo necesita una situacion, sorteamos una funcion de la
# lista correspondiente. Esto permite tener variedad: dos bullies del
# mismo grafo pueden recibir situaciones distintas.
PLANTILLAS_POR_TIPO = {
    "victima": [situacion_rumor_falso, situacion_acoso_directo,
                situacion_exclusion, situacion_suplantacion],
    "bully":   [situacion_bully_arrepentido, situacion_acoso_directo,
               situacion_bully_amenazas, situacion_bully_doxxing,
               situacion_bully_grupo, situacion_bully_chantaje,
               situacion_bully_provocacion, situacion_bully_anonimo],
    "aliado":  [situacion_aliado],
    "neutro":  [situacion_rumor_falso, situacion_exclusion],
    "central": [situacion_acoso_directo],
}

# Lista de nombres para personalizar las situaciones. Mezcla de
# nombres latinoamericanos comunes para que el juego se sienta cercano
# al publico hispanoparlante.
NOMBRES_PERSONAJES = [
    "Camila", "Andres", "Sofia", "Mateo", "Valeria", "Daniel", "Isabella",
    "Sebastian", "Mariana", "Tomas", "Antonia", "Lucas", "Emilia", "Diego",
    "Luciana", "Joaquin", "Renata", "Martin", "Olivia", "Samuel",
]


def crear_situacion(tipo_nodo, nombre_nodo=None):
    """Devuelve un ArbolDecisiones listo para usar.

    Como funciona:
      1) Busca las plantillas validas para el tipo de nodo dado.
         Si el tipo no esta en el dict, usa la lista de "neutro".
      2) Sortea una plantilla al azar.
      3) Si no se dio nombre, sortea uno tambien.
      4) Llama la plantilla con el nombre y envuelve la raiz en
         un ArbolDecisiones.
    """
    plantillas = PLANTILLAS_POR_TIPO.get(tipo_nodo,
                                        PLANTILLAS_POR_TIPO["neutro"])
    plantilla = random.choice(plantillas)
    if nombre_nodo is None:
        nombre_nodo = random.choice(NOMBRES_PERSONAJES)
    raiz = plantilla(nombre_nodo)
    return ArbolDecisiones(raiz)


def nombre_aleatorio():
    """Devuelve un nombre del pool de personajes. Util si necesitas
    un nombre para algo distinto de una situacion."""
    return random.choice(NOMBRES_PERSONAJES)
