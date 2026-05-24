"""
========================================================================
red.py - SISTEMA DE RED MULTIJUGADOR (cliente-servidor con sockets TCP)
========================================================================
Este modulo implementa el multijugador del juego. Es un sistema
CLIENTE-SERVIDOR clasico donde:

  - SERVIDOR (host): tiene la fuente unica de verdad del estado del
                     juego. Acepta hasta 4 jugadores conectados.
  - CLIENTES:        se conectan al servidor, mandan acciones, y
                     reciben snapshots del estado.

PROTOCOLO: usamos JSON-LINE — cada mensaje es un JSON terminado en \n.
Es sencillo (debuggeable con cualquier herramienta de texto), legible,
y maneja bien fronteras de mensajes (cualquier socket TCP puede partir
los datos arbitrariamente, pero \n nos da delimitadores claros).

TIPOS DE MENSAJES:
  Cliente -> Servidor:
    JOIN    -> "hola, soy X con skin Y"
    ACCION  -> "muevo al nodo 5" / "uso poder escudo"
    SALIR   -> "me desconecto limpiamente"
  Servidor -> Cliente:
    WELCOME -> "OK, tu id es N"
    ESTADO  -> snapshot completo del juego (grafo, jugadores, salud)
    MENSAJE -> texto plano (notificaciones, chat)

CONCURRENCIA: el servidor usa un thread aceptador en background que
hace accept() sin bloquear el loop principal. Las operaciones sobre
self._clientes estan protegidas por self._lock para evitar race
conditions.

NON-BLOCKING IO: los reads de cada cliente son no-bloqueantes
(setblocking(False)) para que el servidor pueda procesar a TODOS los
clientes en cada tick sin atorarse esperando datos.
========================================================================
"""

import json
import socket
import threading
import time


# ---------------------------------------------------------------------------
# HELPERS DE BAJO NIVEL (envio y recepcion JSON-line)
# ---------------------------------------------------------------------------
def _enviar(sock, mensaje):
    """Envia un mensaje (dict serializable a JSON) por el socket.

    Lo serializamos como JSON + \n al final (formato JSON-line) y lo
    mandamos en bytes UTF-8. Devuelve True si tuvo exito, False si la
    conexion fallo (para que el caller pueda desconectar limpio).
    """
    try:
        # json.dumps convierte el dict a string JSON.
        # Anadimos \n al final como delimitador de mensajes.
        data = (json.dumps(mensaje) + "\n").encode("utf-8")
        # sendall garantiza que se envien TODOS los bytes (puede que
        # send() solo envie una parte si el buffer esta lleno).
        sock.sendall(data)
        return True
    except (OSError, ConnectionError):
        # Socket cerrado, conexion rota, etc.
        return False


def _leer_lineas(sock, buffer_state):
    """Lee de forma NO-BLOQUEANTE todas las lineas JSON disponibles.

    Como TCP es un stream sin delimitadores, los mensajes pueden llegar
    partidos o juntos. Usamos un buffer (`buffer_state["buf"]`) donde
    acumulamos los bytes recibidos, y vamos cortando en \n.

    Devuelve (lista_mensajes_parseados, sigue_vivo):
      - mensajes: list de dicts JSON decodificados
      - sigue_vivo: False si la conexion se cerro, True en otro caso
    """
    mensajes = []
    try:
        # Modo no bloqueante: si no hay datos, lanza BlockingIOError
        # en vez de quedarse esperando.
        sock.setblocking(False)
        data = sock.recv(4096)
        # recv() devuelve "" cuando el peer cerro la conexion limpio.
        if not data:
            return mensajes, False
        # Acumulamos los nuevos bytes (decodificados) al buffer.
        # errors="ignore" descarta bytes invalidos UTF-8 sin crashear.
        buffer_state["buf"] += data.decode("utf-8", errors="ignore")
        # Mientras haya \n en el buffer, hay al menos un mensaje completo.
        while "\n" in buffer_state["buf"]:
            # split("\n", 1) parte solo en el PRIMER \n, dejando el
            # resto (que puede contener mas mensajes) en el buffer.
            linea, buffer_state["buf"] = buffer_state["buf"].split("\n", 1)
            linea = linea.strip()
            if not linea:
                continue
            try:
                mensajes.append(json.loads(linea))
            except json.JSONDecodeError:
                # Mensaje malformado: lo ignoramos en vez de crashear.
                # Esto evita ataques o bugs del cliente que tiren al servidor.
                pass
        return mensajes, True
    except BlockingIOError:
        # No hay datos disponibles ahora mismo: no es error, es normal.
        return mensajes, True
    except (OSError, ConnectionError):
        # Conexion rota.
        return mensajes, False


# ===========================================================================
# SERVIDOR
# ===========================================================================
class Servidor:
    """Servidor TCP que acepta hasta max_jugadores conexiones simultaneas.

    Uso tipico:
        srv = Servidor("0.0.0.0", 50007)
        srv.iniciar()                  # arranca el thread aceptador
        while jugando:
            srv.procesar()             # llamar cada frame
            ...
            srv.difundir_estado(...)
        srv.detener()
    """

    def __init__(self, host, port, max_jugadores=4):
        self.host = host
        self.port = port
        self.max_jugadores = max_jugadores
        self._sock = None                  # socket de escucha
        self._activo = False               # bandera para parar el thread
        self._clientes = []                # lista de dicts con info por cliente
        # Lock para proteger self._clientes (el thread aceptador y el
        # loop principal acceden a esta lista).
        self._lock = threading.Lock()
        self._proximo_id = 0               # IDs incrementales unicos
        # Cola de acciones recibidas pendientes de procesar.
        # El juego principal vacia esta lista cada tick.
        self.acciones_pendientes = []
        # Log textual de eventos para debug y mostrar en el HUD del host.
        self.eventos_log = []
        self._aceptador = None             # thread daemon de aceptacion

    def iniciar(self):
        """Crea el socket, lo pone a escuchar, y arranca el thread aceptador."""
        # SOCK_STREAM = TCP (vs SOCK_DGRAM que es UDP).
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR permite reutilizar el puerto si el server se
        # acaba de cerrar (sin esto hay que esperar el TIME_WAIT del SO).
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        # listen() arranca a aceptar conexiones (backlog = max_jugadores).
        self._sock.listen(self.max_jugadores)
        # Timeout corto para que el accept() en el thread no bloquee
        # indefinidamente; asi puede checkear self._activo y parar.
        self._sock.settimeout(0.5)
        self._activo = True
        # Thread aceptador: corre en background hasta que detenemos.
        # daemon=True asegura que muera cuando muere el programa principal.
        self._aceptador = threading.Thread(target=self._aceptar_loop, daemon=True)
        self._aceptador.start()
        self.eventos_log.append(f"Servidor en {self.host}:{self.port}")

    def detener(self):
        """Cierra el servidor y todas las conexiones."""
        self._activo = False
        # Cerramos todos los sockets de cliente.
        for c in list(self._clientes):
            try:
                c["sock"].close()
            except OSError:
                pass
        # Cerramos el socket de escucha.
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    def _aceptar_loop(self):
        """Loop interno del thread aceptador.

        Espera nuevas conexiones; cuando llega una, la agrega a la
        lista de clientes (si no esta llena) o la rechaza con un
        mensaje de "Sala llena".
        """
        while self._activo:
            try:
                # accept() bloquea hasta que llegue una conexion, pero
                # tenemos settimeout(0.5) asi que lanza timeout y nos
                # da chance de checkear self._activo.
                cs, addr = self._sock.accept()
                # Lockeamos para modificar self._clientes de forma segura.
                with self._lock:
                    if len(self._clientes) >= self.max_jugadores:
                        _enviar(cs, {"tipo": "MENSAJE", "texto": "Sala llena."})
                        cs.close()
                        continue
                    # Creamos el dict de info del cliente.
                    info = {
                        "sock": cs,                  # socket conectado
                        "addr": addr,                # (ip, puerto) del peer
                        "buf": {"buf": ""},          # buffer de lectura (dict para mutabilidad)
                        "id": self._proximo_id,      # ID unico
                        "nombre": f"Jugador{self._proximo_id}",
                        "skin": 0,
                    }
                    self._proximo_id += 1
                    self._clientes.append(info)
                    self.eventos_log.append(f"Conectado {addr[0]} como jug {info['id']}")
            except socket.timeout:
                # Normal: usamos timeout para poder checar self._activo.
                continue
            except OSError:
                # Socket cerrado desde fuera: salimos.
                break

    def procesar(self):
        """Lee mensajes pendientes de TODOS los clientes y los procesa.

        Llamala CADA FRAME desde el loop principal del juego. Es no-
        bloqueante: si nadie mando nada, retorna casi instantaneo.
        """
        with self._lock:
            # list(self._clientes) crea una copia para poder modificar
            # la lista original (con _desconectar) sin afectar la iteracion.
            for c in list(self._clientes):
                msgs, vivo = _leer_lineas(c["sock"], c["buf"])
                if not vivo:
                    self._desconectar(c)
                    continue
                for m in msgs:
                    self._procesar_mensaje(c, m)

    def _procesar_mensaje(self, cliente, mensaje):
        """Despacha un mensaje recibido al handler segun su tipo."""
        tipo = mensaje.get("tipo")
        if tipo == "JOIN":
            # Cliente nos dice su nombre y skin elegido.
            cliente["nombre"] = mensaje.get("nombre", cliente["nombre"])
            cliente["skin"] = int(mensaje.get("skin", 0))
            # Respondemos con WELCOME + su ID para que sepa quien es.
            _enviar(cliente["sock"], {"tipo": "WELCOME", "id_jugador": cliente["id"]})
            self.eventos_log.append(f"Jug {cliente['id']} ({cliente['nombre']}) listo.")
        elif tipo == "ACCION":
            # Encolamos la accion para que el juego principal la procese.
            # Marcamos quien la mando para que el server sepa a quien
            # corresponde la accion.
            mensaje["id_jugador"] = cliente["id"]
            self.acciones_pendientes.append(mensaje)
        elif tipo == "SALIR":
            # Desconexion limpia.
            self._desconectar(cliente)

    def _desconectar(self, cliente):
        """Cierra y quita un cliente de la lista."""
        try:
            cliente["sock"].close()
        except OSError:
            pass
        if cliente in self._clientes:
            self._clientes.remove(cliente)
        self.eventos_log.append(f"Jug {cliente['id']} desconectado.")

    def difundir_estado(self, estado_juego):
        """Envia el snapshot del estado del juego a TODOS los clientes.

        Llamada cada vez que algo importante cambia (movimiento,
        decision, infeccion). Si el send falla, desconectamos al cliente.
        """
        msg = {"tipo": "ESTADO", "estado_juego": estado_juego}
        with self._lock:
            for c in list(self._clientes):
                if not _enviar(c["sock"], msg):
                    self._desconectar(c)

    def enviar_mensaje(self, texto):
        """Envia un mensaje de texto a todos los clientes (notificacion)."""
        with self._lock:
            for c in list(self._clientes):
                _enviar(c["sock"], {"tipo": "MENSAJE", "texto": texto})

    def jugadores(self):
        """Devuelve la lista actual de clientes como tuplas (id, nombre, skin).

        Notar que NO incluye al host (el host no es un cliente, es el
        que corre el servidor). Esto es importante para entender el
        bug que tuvimos donde el host se autoeliminaba si se confiaba
        en esta lista.
        """
        with self._lock:
            return [(c["id"], c["nombre"], c["skin"]) for c in self._clientes]


# ===========================================================================
# CLIENTE
# ===========================================================================
class Cliente:
    """Cliente TCP que se conecta a un servidor.

    Uso tipico:
        cli = Cliente("192.168.1.10", 50007, "Mi nombre", skin=2)
        cli.conectar()
        while jugando:
            cli.procesar()           # leer mensajes pendientes
            if cli.estado_juego:     # snapshot mas reciente del server
                ...
            cli.enviar_accion("mover", {"destino": 5})
        cli.desconectar()
    """

    def __init__(self, host, port, nombre="Jugador", skin=0):
        self.host = host
        self.port = port
        self.nombre = nombre
        self.skin = skin
        self.sock = None
        # Buffer para acumular bytes parciales (igual que en servidor).
        self.buffer = {"buf": ""}
        # ID asignado por el server (lo recibimos en el WELCOME).
        self.id_jugador = None
        # Ultimo snapshot del estado del juego recibido del server.
        self.estado_juego = None
        # Mensajes textuales recibidos (para mostrar en chat/HUD).
        self.mensajes = []
        self.conectado = False

    def conectar(self, timeout=5.0):
        """Intenta conectar al servidor. Devuelve True si tuvo exito."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Timeout solo para el connect inicial; despues volvemos
            # a no-bloqueante en procesar().
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            # Inmediatamente nos presentamos con JOIN.
            _enviar(self.sock, {"tipo": "JOIN", "nombre": self.nombre, "skin": self.skin})
            self.conectado = True
            return True
        except OSError as e:
            # Cualquier error de red: lo logueamos y devolvemos False.
            self.mensajes.append(f"Error al conectar: {e}")
            self.conectado = False
            return False

    def desconectar(self):
        """Cierra la conexion enviando SALIR primero."""
        if not self.sock:
            return
        try:
            _enviar(self.sock, {"tipo": "SALIR"})
            self.sock.close()
        except OSError:
            pass
        self.conectado = False

    def enviar_accion(self, accion, datos=None):
        """Manda una accion al servidor.

        Ejemplo: cli.enviar_accion("mover", {"destino": 5})
        El server lo encolara y lo aplicara cuando procese la cola.
        """
        if not self.conectado:
            return
        _enviar(self.sock, {"tipo": "ACCION", "accion": accion, "datos": datos or {}})

    def procesar(self):
        """Lee mensajes pendientes del servidor.

        Llamala cada frame. Actualiza self.estado_juego si recibimos
        un ESTADO, y self.id_jugador si recibimos un WELCOME.
        """
        if not self.conectado:
            return
        msgs, vivo = _leer_lineas(self.sock, self.buffer)
        if not vivo:
            self.conectado = False
            return
        for m in msgs:
            t = m.get("tipo")
            if t == "WELCOME":
                # Ya sabemos quien somos.
                self.id_jugador = m.get("id_jugador")
                self.mensajes.append(f"Conectado como Jugador {self.id_jugador}")
            elif t == "ESTADO":
                # Sobrescribimos el snapshot anterior con el nuevo.
                self.estado_juego = m.get("estado_juego")
            elif t == "MENSAJE":
                self.mensajes.append(m.get("texto", ""))


# ===========================================================================
# UTILIDAD: descubrir IP local
# ===========================================================================
def descubrir_ip_local():
    """Devuelve la IP local de la maquina (la que ven otros en la LAN).

    Truco clasico: abrimos un socket UDP "conectado" a una IP externa
    (8.8.8.8, el DNS de Google) — no se envia nada realmente, pero el
    sistema operativo selecciona la interfaz de salida y podemos
    consultar su IP local con getsockname().

    Si no hay red, devolvemos 127.0.0.1 (loopback) como fallback.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect() en UDP no envia nada, solo asocia destino.
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
