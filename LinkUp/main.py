"""
========================================================================
LinkUp - Guardianes del Nexo
========================================================================
PUNTO DE ENTRADA del juego. Este es el archivo que se ejecuta para
arrancar el programa: `python main.py`.

Su única responsabilidad es:
  1) Crear una instancia de la clase Juego (definida en juego.py).
  2) Llamar al método correr() que arranca el bucle principal.
  3) Capturar cualquier error inesperado y cerrar de forma limpia
     (sin dejar la ventana de pygame colgada ni el socket abierto).

Todo lo demás (gráficos, lógica, red, etc.) vive en otros módulos.
Esto sigue el principio de separar el "arranque" de la "lógica" para
que sea fácil de leer y de probar.
========================================================================
"""

import sys
from juego import Juego


def main():
    """Crea el juego y lo ejecuta, capturando errores para cerrar bien."""
    juego = Juego()
    try:
        # correr() es el bucle infinito de pygame: procesa eventos,
        # actualiza estado, dibuja, y repite a 60 FPS.
        juego.correr()
    except KeyboardInterrupt:
        # El usuario presiono Ctrl+C en la terminal: cerramos limpio.
        juego.salir()
    except Exception:
        # Cualquier otro error inesperado: imprimimos la traza completa
        # para poder depurar, intentamos cerrar el juego, y devolvemos
        # codigo de error 1 al sistema operativo.
        import traceback
        traceback.print_exc()
        try:
            juego.salir()
        except Exception:
            # Si hasta el cierre falla, no hay mucho que hacer:
            # al menos no queremos un error encima de otro.
            pass
        sys.exit(1)


# Idiom de Python: este bloque solo se ejecuta cuando el archivo se corre
# directamente (`python main.py`), no cuando alguien lo importa.
if __name__ == "__main__":
    main()
