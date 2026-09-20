"""Carrega os helpers da skill como módulos importáveis nos testes."""
import importlib.util
import sys
from pathlib import Path

HELPERS = Path(__file__).parents[1] / ".claude" / "skills" / "manciasolutions-editor-de-video" / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))


def load(name: str):
    """Importa um helper pelo nome do arquivo, sem depender de pacote."""
    spec = importlib.util.spec_from_file_location(name, HELPERS / f"{name}.py")
    assert spec and spec.loader, f"helper não encontrado: {name}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
