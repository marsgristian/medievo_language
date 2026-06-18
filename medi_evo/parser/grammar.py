from __future__ import annotations

from importlib.resources import files

medi_evo_GRAMMAR = files("medi_evo.parser").joinpath("medi_evo.lark").read_text(encoding="utf-8")
