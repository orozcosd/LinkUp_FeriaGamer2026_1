"""
Descarga las fuentes Orbitron desde Google Fonts y las guarda en assets/fonts/.
Ejecutalo una sola vez en tu PC con: python descargar_fuente.py
"""
import os
import sys
import urllib.request

DIR_FUENTES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "assets", "fonts")
os.makedirs(DIR_FUENTES, exist_ok=True)

FUENTES = {
    "Orbitron-Regular.ttf": "https://fonts.gstatic.com/s/orbitron/v34/yMJMMIlzdpvBhQQL_SC3X9yhF25-T1nyGy6BoWg1.ttf",
    "Orbitron-Bold.ttf":    "https://fonts.gstatic.com/s/orbitron/v34/yMJMMIlzdpvBhQQL_SC3X9yhF25-T1nyMC2BoWg1.ttf",
}

def descargar(nombre, url):
    destino = os.path.join(DIR_FUENTES, nombre)
    if os.path.isfile(destino) and os.path.getsize(destino) > 50000:
        print(f"  Ya existe: {nombre}")
        return True
    print(f"  Descargando {nombre} ...")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(destino, "wb") as f:
            f.write(data)
        print(f"  OK ({len(data) // 1024} KB)")
        return True
    except Exception as e:
        print(f"  FALLO: {e}")
        return False

def main():
    print("Descargando fuentes Orbitron desde Google Fonts...")
    print(f"Destino: {DIR_FUENTES}\n")
    ok = all(descargar(n, u) for n, u in FUENTES.items())
    print()
    if ok:
        print("Listo. Ya puedes jugar con la fuente Orbitron activada.")
    else:
        print("Algo fallo. Descarga manual desde:")
        print("  https://fonts.google.com/specimen/Orbitron")
        print("Descomprime y copia Orbitron-Regular.ttf y Orbitron-Bold.ttf")
        print(f"a la carpeta: {DIR_FUENTES}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
