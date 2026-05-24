"""
========================================================================
descargar_fuente.py - HELPER PARA DESCARGAR LA FUENTE PRESS START 2P
========================================================================
Script auxiliar (NO se ejecuta automaticamente con el juego). Hay que
correrlo UNA VEZ por PC:

    python descargar_fuente.py

Descarga la fuente Press Start 2P desde Google Fonts y la guarda en
assets/fonts/. Si Google Fonts falla por alguna razon (proxy, firewall,
etc), reintenta con un mirror de GitHub.

Por que esta separado del juego?
  - El juego YA funciona sin la fuente (cae a Arial). No queremos
    que un fallo de red al arrancar mate el juego.
  - Descargar es un proceso lento y queremos mostrar progreso.
  - Solo hay que hacerlo una vez por instalacion.

Si todo falla, el script imprime instrucciones para descargar la
fuente manualmente desde fonts.google.com.
========================================================================
"""
import os
import sys
import urllib.request

# Calculamos donde guardar la fuente: assets/fonts/ relativo a este script.
# os.makedirs con exist_ok=True crea la carpeta si no existe sin error
# si ya existe.
DIR_FUENTES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "assets", "fonts")
os.makedirs(DIR_FUENTES, exist_ok=True)

# Diccionario nombre_archivo -> URL principal.
# Press Start 2P solo tiene un peso (Regular). La usamos para todo.
# Esta URL es la oficial de Google Fonts (fonts.gstatic.com).
FUENTES = {
    "PressStart2P-Regular.ttf":
        "https://fonts.gstatic.com/s/pressstart2p/v15/e3t4euO8T-267oIAQAu6jDQyK3nVivM.ttf",
}

# Mirror alternativo: si la URL principal falla, probamos esta.
# Es el repositorio oficial de Google Fonts en GitHub.
MIRRORS = {
    "PressStart2P-Regular.ttf":
        "https://github.com/google/fonts/raw/main/ofl/pressstart2p/PressStart2P-Regular.ttf",
}


def descargar(nombre, url):
    """Descarga un archivo y lo guarda en DIR_FUENTES/nombre.

    Si el archivo ya existe y pesa > 30KB (lo razonable para una
    fuente), no lo vuelve a descargar. Esto permite re-ejecutar
    el script sin gastar bandwidth de nuevo.

    Devuelve True si la descarga (o el skip) fue exitosa, False
    si fallo.
    """
    destino = os.path.join(DIR_FUENTES, nombre)
    # Verificamos si ya existe y tiene tamano razonable.
    # 30000 bytes = 30KB: si esta por debajo probablemente es una
    # descarga corrupta (un HTML de error en vez de la fuente).
    if os.path.isfile(destino) and os.path.getsize(destino) > 30000:
        print(f"  Ya existe: {nombre}")
        return True
    print(f"  Descargando {nombre} ...")
    try:
        # Usamos Request con User-Agent custom porque algunos servers
        # bloquean requests que parecen scripts (sin User-Agent).
        # Nos hacemos pasar por Firefox en Windows 10.
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        # timeout=30: si en 30s no responde, abortamos.
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        # Guardamos los bytes recibidos al archivo de destino.
        with open(destino, "wb") as f:
            f.write(data)
        print(f"  OK ({len(data) // 1024} KB)")
        return True
    except Exception as e:
        # Cualquier error (red, permisos, timeout) lo capturamos para
        # poder intentar con el mirror sin matar el script.
        print(f"  Fallo en URL principal: {e}")
        return False


def main():
    """Punto de entrada: descarga todas las fuentes con fallback."""
    print("Descargando fuente Press Start 2P (estilo arcade 8-bit)...")
    print(f"Destino: {DIR_FUENTES}\n")
    todo_ok = True
    # Intentamos cada fuente del diccionario FUENTES.
    for n, u in FUENTES.items():
        ok = descargar(n, u)
        # Si fallo Y existe un mirror para esta fuente, reintentamos.
        if not ok and n in MIRRORS:
            print(f"  Reintentando con mirror...")
            ok = descargar(n, MIRRORS[n])
        if not ok:
            todo_ok = False
    print()
    if todo_ok:
        print("Listo. Reinicia el juego para ver la fuente pixelada.")
    else:
        # Si TODO fallo, le decimos al usuario como hacerlo a mano.
        print("Algo fallo. Descarga manual desde:")
        print("  https://fonts.google.com/specimen/Press+Start+2P")
        print("Descomprime y copia PressStart2P-Regular.ttf a:")
        print(f"  {DIR_FUENTES}")
    # Codigo de salida estandar: 0 si todo ok, 1 si fallo.
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
