from __future__ import annotations

from importlib.resources import files

medievo_GRAMMAR = files("med_evo.parser").joinpath("medievo.lark").read_text(encoding="utf-8")
