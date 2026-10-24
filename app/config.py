"""Configuración leída del archivo .env. La clave nunca sale del servidor."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODELO_RAPIDO = os.getenv("MODELO_RAPIDO", "claude-haiku-5-5")
MODELO_FUERTE = os.getenv("MODELO_FUERTE", "claude-sonnet-5-5")
MODO_POR_DEFECTO = os.getenv("MODO_POR_DEFECTO", "simulacion")
PUERTO = int(os.getenv("PUERTO", "8000"))
SEGUNDOS_POR_LINEA = float(os.getenv("SEGUNDOS_POR_LINEA", "3"))
GENERAR_PDF = os.getenv("GENERAR_PDF", "1") == "1"  # usa Microsoft Word si está instalado
DB_PATH = RAIZ / os.getenv("DB_PATH", "data/copiloto.db")

CATALOGO_JSON = RAIZ / "catalogo-simulado" / "catalogo-simulado.json"
WEB_DIR = RAIZ / "web"
SALIDAS_DIR = RAIZ / "salidas"
