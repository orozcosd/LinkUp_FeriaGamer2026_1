"""
LinkUp - Guardianes del Nexo
Punto de entrada del juego.

Ejecutar:
    python main.py
"""

import sys
from juego import Juego


def main():
    juego = Juego()
    try:
        juego.correr()
    except KeyboardInterrupt:
        juego.salir()
    except Exception as exc:
        # Cierre seguro ante errores inesperados
        import traceback
        traceback.print_exc()
        try:
            juego.salir()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
