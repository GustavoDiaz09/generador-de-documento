"""Entry point: abre la interfaz grafica del generador de protocolos.

Uso:
    python run_generador.py

Si se lanza con python.exe (tiene consola), se relanza silenciosamente con
pythonw.exe para que no quede ninguna ventana de cmd abierta.
"""
from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _relanzar_sin_consola() -> None:
    """Si corremos con la consola activa, nos relanzamos con pythonw.exe y salimos."""
    exe = sys.executable.lower()
    if not exe.endswith("python.exe"):
        return  # ya estamos con pythonw.exe (o distinto)
    pythonw = os.path.join(
        os.path.dirname(exe), "pythonw.exe"
    )
    subprocess.Popen([pythonw, __file__])
    sys.exit(0)


if __name__ == "__main__":
    _relanzar_sin_consola()
    from generador.gui import main  # noqa: E402

    main()