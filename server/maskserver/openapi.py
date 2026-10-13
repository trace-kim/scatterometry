"""Write the OpenAPI schema (input for the web client's generated types).

    python -m maskserver.openapi web/openapi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .app import create_app
from .settings import Settings


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = create_app(Settings(web_dist=None)).openapi()
    target.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
