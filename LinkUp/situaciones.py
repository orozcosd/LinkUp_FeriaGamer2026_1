"""
Generador de situaciones de ciberbullying.
Cada situación es un árbol de decisiones (estructura: ArbolDecisiones).

Las situaciones NO son preguntas tipo trivia: son escenarios narrativos
donde el jugador escoge cómo actuar como Guardián del Nexo.
"""

import random
from estructuras import NodoArbol, ArbolDecisiones


# ---------------------------------------------------------------------------
# Plantillas de situaciones
# Cada plantilla devuelve la raíz del árbol de decisiones.
# Efectos posibles:
#   puntos:    int (positivos o negativos)
#   salud:     int (afecta salud de la comunidad)
#   resolver:  bool (marca el nodo como resuelto si True)
#   liberar:   bool (libera el nodo)
#   poder:     str (otorga un poder)
# ---------------------------------------------------------------------------

def _hoja(texto, tipo="bueno", **efecto):
    return NodoArbol(texto, terminal=True, efecto=efecto, tipo_resultado=tipo)


def situacion_rumor_falso(nombre):
    """Situación: se está propagando un rumor falso sobre 'nombre'."""
    raiz = NodoArbol(
        f"Detectas que un rumor falso sobre {nombre} se está viralizando.\n"
        "Los mensajes acumulan likes y comentarios crueles. ¿Qué haces?"
    )

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
        "Ignorar el problema permite que el rumor llegue a más nodos.\n"
        "La comunidad se debilita.",
        tipo="malo",
        puntos=-10, salud=-12
    )

    raiz.opciones = [
        ("Reportar la publicación y pedir verificación de hechos.",
         op1_hijo, {}),
        (f"Escribir a {nombre} para apoyarla en privado.",
         op2_hijo, {}),
        ("Ignorar: no es tu problema.",
         op3_hijo, {}),
    ]
    return raiz


def situacion_acoso_directo(nombre):
    """Un usuario está siendo atacado en comentarios."""
    raiz = NodoArbol(
        f"{nombre} está recibiendo mensajes ofensivos en una publicación.\n"
        "Varios usuarios se están sumando al ataque. ¿Cómo respondes?"
    )

    sub_bueno = NodoArbol(
        "Llamaste la atención sobre el acoso. Otros aliados aparecen.\n"
        "¿Quieres además reportar al acosador principal?"
    )
    sub_bueno.opciones = [
        ("Sí, reportarlo formalmente.",
         _hoja("Acosador suspendido. Nodo liberado. ¡Excelente trabajo!",
               tipo="bueno", puntos=30, salud=12, resolver=True,
               poder="escudo_empatia"),
         {}),
        ("No, basta con la defensa pública.",
         _hoja("Buena acción, pero el acosador podría volver.",
               tipo="neutro", puntos=15, salud=5, resolver=True),
         {}),
    ]

    raiz.opciones = [
        ("Comentar con empatía defendiendo a la víctima.",
         sub_bueno, {}),
        ("Responder al acosador con insultos.",
         _hoja("El conflicto escala. Ahora hay dos focos de odio.",
               tipo="malo", puntos=-15, salud=-15),
         {}),
        ("Bloquear silenciosamente y seguir.",
         _hoja(f"{nombre} sigue sintiéndose sola. Salud de la red baja.",
               tipo="neutro", puntos=-5, salud=-8),
         {}),
    ]
    return raiz


def situacion_exclusion(nombre):
    """Un grupo está excluyendo a alguien."""
    raiz = NodoArbol(
        f"Un grupo del chat ha sacado a {nombre} sin razón.\n"
        f"{nombre} se entera por capturas que circulan. ¿Qué haces?"
    )
    raiz.opciones = [
        ("Crear un nuevo grupo inclusivo e invitar a aliados.",
         _hoja("¡Construiste un puente de empatía! Nueva red de apoyo activa.",
               tipo="bueno", puntos=25, salud=10, resolver=True,
               poder="red_apoyo"),
         {}),
        ("Confrontar al grupo en público.",
         _hoja("Conflicto abierto. Algunos cambian de opinión, otros no.",
               tipo="neutro", puntos=8, salud=-2),
         {}),
        ("No intervenir.",
         _hoja(f"{nombre} se aísla aún más. La red se debilita.",
               tipo="malo", puntos=-12, salud=-10),
         {}),
    ]
    return raiz


def situacion_suplantacion(nombre):
    """Suplantación de identidad."""
    raiz = NodoArbol(
        f"Alguien creó una cuenta falsa de {nombre} publicando contenido\n"
        "ofensivo en su nombre. ¿Cómo actúas?"
    )
    raiz.opciones = [
        ("Reportar la cuenta y avisar a amistades reales.",
         _hoja("La cuenta falsa fue suspendida. La identidad real protegida.",
               tipo="bueno", puntos=25, salud=8, resolver=True,
               poder="voz_amplificada"),
         {}),
        (f"Escribir un post explicando que es falso.",
         _hoja("La aclaración funciona parcialmente; algunos siguen creyendo.",
               tipo="neutro", puntos=10, salud=2),
         {}),
        ("Esperar a ver qué pasa.",
         _hoja("La cuenta falsa hace más daño. Nodo infectado.",
               tipo="malo", puntos=-15, salud=-15),
         {}),
    ]
    return raiz


def situacion_aliado(nombre):
    """Un aliado quiere unirse al equipo."""
    raiz = NodoArbol(
        f"{nombre} te ofrece ayuda como aliado/a.\n"
        "Tiene experiencia neutralizando rumores. ¿Aceptas?"
    )
    raiz.opciones = [
        ("Sí, sumarlo/a a la red de apoyo.",
         _hoja(f"¡{nombre} se une! Recibes el poder Red de Apoyo +1.",
               tipo="bueno", puntos=15, salud=5, resolver=True,
               poder="red_apoyo"),
         {}),
        ("Preguntar más antes de aceptar.",
         _hoja("Buena precaución. Se une después de una conversación honesta.",
               tipo="bueno", puntos=12, salud=3, resolver=True),
         {}),
        ("Rechazar la oferta.",
         _hoja("Pierdes una oportunidad de fortalecer la red.",
               tipo="neutro", puntos=-3),
         {}),
    ]
    return raiz

def situacion_bully_amenazas(nombre):
    raiz = NodoArbol(
        f"{nombre} está enviando amenazas violentas por mensajes privados\n"
        "a varios miembros de la red. Las víctimas tienen miedo. ¿Qué haces?"
    )
    sub_evidencia = NodoArbol(
        "Recolectaste capturas como evidencia. ¿Cómo procedes ahora?"
    )
    sub_evidencia.opciones = [
        ("Reportar a las autoridades junto con las víctimas.",
         _hoja(f"{nombre} es sancionado/a. Las víctimas se sienten protegidas.",
               tipo="bueno", puntos=35, salud=18, resolver=True,
               poder="escudo_empatia"), {}),
        ("Enviar la evidencia solo a moderadores de la plataforma.",
         _hoja("La cuenta es suspendida temporalmente. Alivio parcial.",
               tipo="bueno", puntos=20, salud=10, resolver=True), {}),
    ]
    raiz.opciones = [
        ("Ayudar a las víctimas a guardar evidencia antes de actuar.", sub_evidencia, {}),
        ("Confrontar públicamente a quien amenaza.",
         _hoja("La amenaza se intensifica y aparecen más cuentas hostiles.",
               tipo="malo", puntos=-18, salud=-15), {}),
        ("Esperar a ver si se detiene solo/a.",
         _hoja("Las amenazas escalan. Una víctima abandona la red.",
               tipo="malo", puntos=-25, salud=-20), {}),
    ]
    return raiz


def situacion_bully_doxxing(nombre):
    raiz = NodoArbol(
        f"{nombre} publicó la dirección y el teléfono de una víctima\n"
        "para incitar a otros a hostigarla. La información ya se difunde."
    )
    raiz.opciones = [
        ("Reportar masivamente el post y avisar a la víctima de inmediato.",
         _hoja("Eliminan la publicación a tiempo. La víctima cambia ajustes de privacidad.",
               tipo="bueno", puntos=30, salud=14, resolver=True,
               poder="voz_amplificada"), {}),
        ("Pedir a la comunidad que no comparta ni interactúe con el post.",
         _hoja("Reduces el alcance, pero algunas capturas siguen circulando.",
               tipo="neutro", puntos=8, salud=-2), {}),
        ("Responder al post pidiéndole que la borre.",
         _hoja(f"{nombre} se burla y sube más datos. Situación empeora.",
               tipo="malo", puntos=-20, salud=-18), {}),
    ]
    return raiz


def situacion_bully_grupo(nombre):
    raiz = NodoArbol(
        f"{nombre} lidera un grupo que ataca coordinadamente a un usuario\n"
        "cada semana. Hoy eligieron a su próxima víctima. ¿Cómo respondes?"
    )
    sub_aliados = NodoArbol(
        "Reúnes aliados para una contracampaña. ¿Qué enfoque eliges?"
    )
    sub_aliados.opciones = [
        ("Lanzar una campaña positiva visibilizando a la víctima con respeto.",
         _hoja("La narrativa cambia. El grupo pierde seguidores y se disuelve.",
               tipo="bueno", puntos=35, salud=16, resolver=True,
               poder="red_apoyo"), {}),
        ("Hablar uno a uno con miembros del grupo para que se retiren.",
         _hoja("Tres integrantes se salen. El grupo pierde fuerza.",
               tipo="bueno", puntos=22, salud=10, resolver=True), {}),
    ]
    raiz.opciones = [
        ("Organizar a la comunidad antes de que ocurra el ataque.", sub_aliados, {}),
        ("Enfrentar directamente al líder del grupo.",
         _hoja("El grupo te convierte en su nuevo objetivo.",
               tipo="malo", puntos=-22, salud=-18), {}),
        ("Avisar solo a la víctima para que se proteja.",
         _hoja("La víctima se protege, pero el grupo encuentra otra.",
               tipo="neutro", puntos=-5, salud=-8), {}),
    ]
    return raiz


def situacion_bully_chantaje(nombre):
    raiz = NodoArbol(
        f"{nombre} amenaza con publicar fotos privadas de un compañero/a\n"
        "si no hace lo que pide. La víctima entró en pánico."
    )
    raiz.opciones = [
        ("Acompañar a la víctima a hablar con un adulto de confianza y reportar.",
         _hoja("La víctima recibe apoyo real. El chantaje se detiene legalmente.",
               tipo="bueno", puntos=40, salud=20, resolver=True,
               poder="escudo_empatia"), {}),
        ("Asesorarle para que no ceda y bloquee de inmediato.",
         _hoja("La víctima se siente acompañada, pero la presión sigue.",
               tipo="neutro", puntos=10, salud=2), {}),
        ("Recomendar que ceda para que no publique nada.",
         _hoja(f"{nombre} pide más cada vez. El daño se profundiza.",
               tipo="malo", puntos=-30, salud=-22), {}),
    ]
    return raiz


def situacion_bully_provocacion(nombre):
    raiz = NodoArbol(
        f"{nombre} publica provocaciones constantes intentando que alguien\n"
        "reaccione mal y quede como agresor. Es una trampa visible."
    )
    raiz.opciones = [
        ("Educar a la comunidad: no alimentar al provocador, reportar y silenciar.",
         _hoja("Sin público, las provocaciones pierden sentido. Nodo aislado.",
               tipo="bueno", puntos=25, salud=12, resolver=True,
               poder="voz_amplificada"), {}),
        ("Responder con humor para desactivar la provocación.",
         _hoja(f"Funciona a medias: {nombre} cambia de táctica.",
               tipo="neutro", puntos=8, salud=2), {}),
        ("Discutir punto por punto en los comentarios.",
         _hoja("Le das visibilidad. Aparecen más bullies imitadores.",
               tipo="malo", puntos=-15, salud=-12), {}),
    ]
    return raiz


def situacion_bully_anonimo(nombre):
    raiz = NodoArbol(
        f"Cuentas anónimas atacan a varios usuarios. Se sospecha que {nombre}\n"
        "está detrás de todas. ¿Cómo manejas la incertidumbre?"
    )
    sub_invest = NodoArbol(
        "Investigaste con cuidado: patrones de escritura coinciden. ¿Qué haces?"
    )
    sub_invest.opciones = [
        ("Compartir evidencia con moderación sin exponer públicamente.",
         _hoja("Las cuentas falsas caen. Se evita linchamiento injusto.",
               tipo="bueno", puntos=30, salud=14, resolver=True,
               poder="red_apoyo"), {}),
        ("Exponer a {nombre} públicamente con la evidencia.",
         _hoja("Aciertas, pero se genera una caza de brujas. La red se polariza.",
               tipo="neutro", puntos=5, salud=-5), {}),
    ]
    raiz.opciones = [
        ("Recolectar evidencia con calma antes de acusar.", sub_invest, {}),
        ("Acusar de inmediato basándote en la sospecha.",
         _hoja("La acusación sin pruebas se vuelve en tu contra.",
               tipo="malo", puntos=-18, salud=-12), {}),
        ("Ignorar el patrón: cada cuenta por separado.",
         _hoja("Los ataques continúan sin freno. Más víctimas afectadas.",
               tipo="malo", puntos=-15, salud=-15), {}),
    ]
    return raiz

def situacion_bully_arrepentido(nombre):
    """Un acosador parece arrepentido."""
    raiz = NodoArbol(
        f"{nombre}, antes acosador/a, escribe que quiere cambiar.\n"
        "Pide perdón a la comunidad. ¿Confías?"
    )

    sub_dialogo = NodoArbol(
        "Abres un diálogo. ¿Qué pides como muestra de cambio?"
    )
    sub_dialogo.opciones = [
        ("Que pida disculpas públicas a las víctimas.",
         _hoja("Disculpa pública aceptada. Nodo transformado en aliado.",
               tipo="bueno", puntos=30, salud=15, resolver=True),
         {}),
        ("Que se mantenga lejos del foro un tiempo.",
         _hoja("Decisión prudente. La comunidad respira tranquila.",
               tipo="bueno", puntos=18, salud=8, resolver=True),
         {}),
    ]

    raiz.opciones = [
        ("Darle una segunda oportunidad mediante diálogo.",
         sub_dialogo, {}),
        ("Rechazar: las víctimas son lo primero.",
         _hoja("Proteges a las víctimas. Decisión válida y segura.",
               tipo="neutro", puntos=10, salud=4, resolver=True),
         {}),
        ("Confiar sin condiciones.",
         _hoja("Vuelve a acosar a los pocos días. La red sufre.",
               tipo="malo", puntos=-20, salud=-15),
         {}),
    ]
    return raiz


# ---------------------------------------------------------------------------
# API PÚBLICA
# ---------------------------------------------------------------------------
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

NOMBRES_PERSONAJES = [
    "Camila", "Andrés", "Sofía", "Mateo", "Valeria", "Daniel", "Isabella",
    "Sebastián", "Mariana", "Tomás", "Antonia", "Lucas", "Emilia", "Diego",
    "Luciana", "Joaquín", "Renata", "Martín", "Olivia", "Samuel",
]


def crear_situacion(tipo_nodo, nombre_nodo=None):
    """Devuelve un ArbolDecisiones para el tipo de nodo dado."""
    plantillas = PLANTILLAS_POR_TIPO.get(tipo_nodo,
                                        PLANTILLAS_POR_TIPO["neutro"])
    plantilla = random.choice(plantillas)
    if nombre_nodo is None:
        nombre_nodo = random.choice(NOMBRES_PERSONAJES)
    raiz = plantilla(nombre_nodo)
    return ArbolDecisiones(raiz)


def nombre_aleatorio():
    return random.choice(NOMBRES_PERSONAJES)
