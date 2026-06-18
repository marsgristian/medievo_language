from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .minimal import compile_medi_evo


def main() -> int:
    parser = argparse.ArgumentParser(description="Compilador Medi Evo language")
    parser.add_argument("input", type=Path, help="Arquivo Medi Evo de entrada")
    parser.add_argument("--json", dest="json_out", type=Path, help="Caminho para salvar JSON compilado")
    parser.add_argument("--diagnostics", dest="diagnostics_out", type=Path, help="Caminho para salvar diagnostics.json")
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    compiled = compile_medi_evo(text)

    error_count = len(compiled.errors())
    warning_count = len(compiled.warnings())
    print(f"Compilacao Medi Evo concluida com {error_count} erro(s) e {warning_count} warning(s).")

    for diagnostic in compiled.diagnostics:
        location = f"linha {diagnostic.line}: " if diagnostic.line else ""
        section = f"[{diagnostic.section}] " if diagnostic.section else ""
        print(
            f"- {diagnostic.phase.upper()} "
            f"{diagnostic.severity.upper()} "
            f"{section}{location}{diagnostic.message}"
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(compiled.to_json(), encoding="utf-8")
        print(f"JSON salvo em: {args.json_out}")

    if args.diagnostics_out:
        args.diagnostics_out.parent.mkdir(parents=True, exist_ok=True)
        diagnostics_json = json.dumps([asdict(d) for d in compiled.diagnostics], indent=2, ensure_ascii=False)
        args.diagnostics_out.write_text(diagnostics_json, encoding="utf-8")
        print(f"Diagnósticos salvos em: {args.diagnostics_out}")

    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
