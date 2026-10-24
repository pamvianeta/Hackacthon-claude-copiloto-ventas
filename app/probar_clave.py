"""Prueba mínima de la clave de Claude (cuesta centavos). Uso: py -m app.probar_clave"""
import sys

import anthropic

from app import config


def main() -> int:
    if not config.ANTHROPIC_API_KEY:
        print("✗ No hay ANTHROPIC_API_KEY en .env")
        return 1
    cliente = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    for modelo in (config.MODELO_RAPIDO, config.MODELO_FUERTE):
        try:
            r = cliente.messages.create(
                model=modelo, max_tokens=200, output_config={"effort": "low"},
                messages=[{"role": "user", "content": "Responde solo: listo"}],
            )
            texto = next((b.text for b in r.content if b.type == "text"), "").strip()
            print(f"✓ {modelo}: «{texto}» ({r.usage.input_tokens}+{r.usage.output_tokens} tokens)")
        except anthropic.AuthenticationError:
            print("✗ La clave no es válida (revisa que esté completa en .env)")
            return 1
        except anthropic.NotFoundError:
            print(f"✗ El modelo {modelo} no existe o la cuenta no tiene acceso")
            return 1
        except anthropic.APIStatusError as e:
            print(f"✗ {modelo}: error {e.status_code}: {e.message}")
            return 1
        except anthropic.APIConnectionError:
            print("✗ No hay conexión con la API (internet). Usa el modo Repetición.")
            return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
