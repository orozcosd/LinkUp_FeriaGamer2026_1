"""
Módulo de red para LinkUp.
Implementa un esquema cliente-servidor con sockets TCP para el modo
multijugador (2-4 jugadores cooperan como Guardianes).

Protocolo simple JSON-line:
  - Cada mensaje es un dict serializado en JSON terminado con '\n'.
  - Tipos:
      JOIN   { "tipo":"JOIN",   "nombre":"...", "skin":n }       (cliente->server)
      WELCOME{ "tipo":"WELCOME","id_jugador":n, "estado_juego":{...}}
      ACCION { "tipo":"ACCION", "id_jugador":n, "accion":"...", "datos":{...}}
      ESTADO { "tipo":"ESTADO", "estado_juego":{...} }
      MENSAJE{ "tipo":"MENSAJE","texto":"..." }
      SALIR  { "tipo":"SALIR" }
"""

import json
import socket
import threading
import time


def _enviar(sock, mensaje):
    """Envía un dict como una línea JSON; tolera errores."""
    try:
        data = (json.dumps(mensaje) + "\n").encode("utf-8")
        sock.sendall(data)
        return True
    except (OSError, ConnectionError):
        return False


def _leer_lineas(sock, buffer_state):
    """Lee y devuelve mensajes completos disponibles en el socket."""
    mensajes = []
    try:
        sock.setblocking(False)
        data = sock.recv(4096)
        if not data:
            return mensajes, False  # conexión cerrada
        buffer_state["buf"] += data.decode("utf-8", errors="ignore")
        while "\n" in buffer_state["buf"]:
            linea, buffer_state["buf"] = buffer_state["buf"].split("\n", 1)
            linea = linea.strip()
            if not linea:
                continue
            try:
                mensajes.append(json.loads(linea))
            except json.JSONDecodeError:
                pass
        return mensajes, True
    except BlockingIOError:
        return mensajes, True
    except (OSError, ConnectionError):
        return mensajes, False


# ---------------------------------------------------------------------------
# SERVIDOR
# ---------------------------------------------------------------------------
class Servidor:
    """
    Servidor del juego. Mantiene una lista de clientes, recibe acciones y
    difunde el estado.
    """
    def __init__(self, host, port, max_jugadores=4):
        self.host = host
        self.port = port
        self.max_jugadores = max_jugadores

        self._sock = None
        self._activo = False
        self._clientes = []            # lista de dicts: sock, addr, buf, id, nombre, skin
        self._lock = threading.Lock()
        self._proximo_id = 0
        self.acciones_pendientes = []  # acciones recibidas que el juego debe procesar
        self.eventos_log = []          # mensajes para mostrar en UI
        self._aceptador = None

    # ---- ciclo de vida ----------------------------------------------------
    def iniciar(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(self.max_jugadores)
        self._sock.settimeout(0.5)
        self._activo = True
        self._aceptador = threading.Thread(target=self._aceptar_loop,
                                           daemon=True)
        self._aceptador.start()
        self.eventos_log.append(f"Servidor iniciado en {self.host}:{self.port}")

    def detener(self):
        self._activo = False
        for c in list(self._clientes):
            try:
                c["sock"].close()
            except OSError:
                pass
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    # ---- hilo aceptador ---------------------------------------------------
    def _aceptar_loop(self):
        while self._activo:
            try:
                cliente_sock, addr = self._sock.accept()
                with self._lock:
                    if len(self._clientes) >= self.max_jugadores:
                        _enviar(cliente_sock,
                                {"tipo": "MENSAJE", "texto": "Sala llena."})
                        cliente_sock.close()
                        continue
                    info = {
                        "sock": cliente_sock,
                        "addr": addr,
                        "buf": {"buf": ""},
                        "id": self._proximo_id,
                        "nombre": f"Jugador{self._proximo_id}",
                        "skin": 0,
                    }
                    self._proximo_id += 1
                    self._clientes.append(info)
                    self.eventos_log.append(
                        f"Conectado {addr[0]}:{addr[1]} como jugador {info['id']}")
            except socket.timeout:
                continue
            except OSError:
                break

    # ---- procesamiento por frame -----------------------------------------
    def procesar(self):
        """Llamar cada frame para leer mensajes de los clientes."""
        with self._lock:
            for c in list(self._clientes):
                mensajes, vivo = _leer_lineas(c["sock"], c["buf"])
                if not vivo:
                    self._desconectar(c)
                    continue
                for m in mensajes:
                    self._procesar_mensaje(c, m)

    def _procesar_mensaje(self, cliente, mensaje):
        tipo = mensaje.get("tipo")
        if tipo == "JOIN":
            cliente["nombre"] = mensaje.get("nombre", cliente["nombre"])
            cliente["skin"] = int(mensaje.get("skin", 0))
            _enviar(cliente["sock"],
                    {"tipo": "WELCOME", "id_jugador": cliente["id"]})
            self.eventos_log.append(
                f"Jugador {cliente['id']} ({cliente['nombre']}) listo.")
        elif tipo == "ACCION":
            mensaje["id_jugador"] = cliente["id"]
            self.acciones_pendientes.append(mensaje)
        elif tipo == "SALIR":
            self._desconectar(cliente)

    def _desconectar(self, cliente):
        try:
            cliente["sock"].close()
        except OSError:
            pass
        if cliente in self._clientes:
            self._clientes.remove(cliente)
        self.eventos_log.append(f"Jugador {cliente['id']} desconectado.")

    # ---- difusión ---------------------------------------------------------
    def difundir_estado(self, estado_juego):
        msg = {"tipo": "ESTADO", "estado_juego": estado_juego}
        with self._lock:
            for c in list(self._clientes):
                if not _enviar(c["sock"], msg):
                    self._desconectar(c)

    def enviar_mensaje(self, texto):
        with self._lock:
            for c in list(self._clientes):
                _enviar(c["sock"], {"tipo": "MENSAJE", "texto": texto})

    def jugadores(self):
        with self._lock:
            return [(c["id"], c["nombre"], c["skin"]) for c in self._clientes]


# ---------------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------------
class Cliente:
    def __init__(self, host, port, nombre="Jugador", skin=0):
        self.host = host
        self.port = port
        self.nombre = nombre
        self.skin = skin
        self.sock = None
        self.buffer = {"buf": ""}
        self.id_jugador = None
        self.estado_juego = None
        self.mensajes = []
        self.conectado = False

    def conectar(self, timeout=5.0):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            _enviar(self.sock,
                    {"tipo": "JOIN", "nombre": self.nombre, "skin": self.skin})
            self.conectado = True
            return True
        except OSError as e:
            self.mensajes.append(f"Error al conectar: {e}")
            self.conectado = False
            return False

    def desconectar(self):
        if not self.sock:
            return
        try:
            _enviar(self.sock, {"tipo": "SALIR"})
            self.sock.close()
        except OSError:
            pass
        self.conectado = False

    def enviar_accion(self, accion, datos=None):
        if not self.conectado:
            return
        _enviar(self.sock, {"tipo": "ACCION",
                            "accion": accion,
                            "datos": datos or {}})

    def procesar(self):
        if not self.conectado:
            return
        msgs, vivo = _leer_lineas(self.sock, self.buffer)
        if not vivo:
            self.conectado = False
            return
        for m in msgs:
            t = m.get("tipo")
            if t == "WELCOME":
                self.id_jugador = m.get("id_jugador")
                self.mensajes.append(f"Conectado como Jugador {self.id_jugador}")
            elif t == "ESTADO":
                self.estado_juego = m.get("estado_juego")
            elif t == "MENSAJE":
                self.mensajes.append(m.get("texto", ""))


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def descubrir_ip_local():
    """Devuelve una IP local razonable para mostrar en la pantalla del host."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    # Test rápido
    srv = Servidor("127.0.0.1", 50007)
    srv.iniciar()
    time.sleep(0.3)
    cli = Cliente("127.0.0.1", 50007, "Test", 0)
    cli.conectar()
    time.sleep(0.3)
    srv.procesar()
    cli.procesar()
    cli.enviar_accion("ping", {"x": 1})
    time.sleep(0.3)
    srv.procesar()
    print("Acciones recibidas:", srv.acciones_pendientes)
    srv.detener()
    cli.desconectar()
