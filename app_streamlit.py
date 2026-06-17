from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from med_evo import compile_medievo
from med_evo.models import ClinicalDocument

from med_evo.sections import DiagnosticoSection, InformacoesPacienteSection, MedicamentosSection, SectionRegistry

SECTION_REGISTRY = SectionRegistry(
    [
        InformacoesPacienteSection(),
        DiagnosticoSection(),
        MedicamentosSection(),
    ]
)


EXAMPLE_PATH = Path(__file__).parent / "examples" / "minimal_valid.medievo"

MINIMAL_EXAMPLE = EXAMPLE_PATH.read_text(encoding="utf-8") if EXAMPLE_PATH.exists() else """EVOLUÇÃO - DIURNA - 16/06/2026 10:30
# INFORMAÇÕES DO PACIENTE
Nome: Maria Silva | Idade: 2 anos 2 meses 2 dias
Data da internação: 10/06/2026
Sexo: feminino
Peso: 56,987 kg

# DIAGNOSTICO
R09 Hipoxemia a/e (cissurite em lobo inferior direito)
R13 Disfagia? (precisa de exames para saber ao certo)
> Em tratamento:
J18 Pneumonia nasocomial / bronco aspirativa

# EXAMES: laboratoriais (últimas 24h)
Hb: 10,2; Leuco: 12000; Plaquetas: 250000 | PCR: 45
> Prévio: 10/06 Hb: 9,8; PCR: 80
# MEDICAMENTOS:
Dipirona: se febre (T > 37,8°C)
"""

MINIMAL_TEST_CASES = [
    ("Seção vazia", "#\n", "empty_section_name"),
    ("Seção com subseção na mesma linha", "# MEDICAMENTOS > Antibiótico:\n", "section_contains_subsection_marker"),
    ("Seção com itens", "# CONTROLES: FC: 100 | FR: 20\n", "section_contains_item_separator"),
    ("Subseção vazia", "# MEDICAMENTOS:\n>: item\n", "empty_subsection_name"),
    ("Subseção sem ':'", "# MEDICAMENTOS:\n> Prévio\n", "subsection_missing_colon"),
    ("Key vazia", "# MEDICAMENTOS:\n: value\n", "empty_item_key"),
    ("Value vazio", "# MEDICAMENTOS:\nkey:\n", "empty_item_value"),
    ("Item livre válido", "# RESUMO:\nPaciente em bom estado geral\n", ""),
    ("Subseção com item na mesma linha", "# EXAMES:\n> Prévio: Hb: 10 | PCR: 20\n", ""),
    ("Item composto", "# EXAMES:\nHb: 10,2; Leuco: 12000; Plaquetas: 250000\n", ""),
]


def diagnostics_dataframe(compiled: ClinicalDocument) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "severity": diagnostic.severity,
                "code": diagnostic.code,
                "message": diagnostic.message,
                "phase": diagnostic.phase,
                "line": diagnostic.line,
                "section": diagnostic.section,
                "raw_text": diagnostic.raw_text,
            }
            for diagnostic in compiled.diagnostics
        ]
    )


st.set_page_config(page_title="medievo mínimo", layout="wide")
st.title("medievo mínimo")
st.caption("DSL estrutural para evoluções médicas: gramática pequena, AST genérica e seções específicas plugáveis.")

with st.sidebar:
    st.header("Regras rápidas")
    st.markdown(
        """
- `#` cria seção.
- `>` cria subseção e exige `:`.
- `|` separa itens.
- `;` separa values e pode criar children.
- `()` gera `commented_values`.
- `/* */` gera comentário ignorável.
"""
    )
    st.markdown("[Manual de escrita](manual_de_escrita.md) e [guia de seções específicas](guia_secoes_especificas.md) ficam na raiz do projeto.")

text = st.text_area("Fonte medievo", value=MINIMAL_EXAMPLE, height=520)

if st.button("Compilar", type="primary"):
    st.session_state["compiled"] = compile_medievo(text, section_registry=SECTION_REGISTRY)

compiled = st.session_state.get("compiled")
if compiled is None:
    st.info("Cole ou edite uma evolução medievo e clique em Compilar.")
    st.stop()

error_count = len(compiled.errors())
warning_count = len(compiled.warnings())
col1, col2, col3, col4 = st.columns(4)
col1.metric("Erros", error_count)
col2.metric("Warnings", warning_count)
col3.metric("Seções", len(compiled.sections))
col4.metric("Seções processadas", len(compiled.processed_sections))

tabs = st.tabs(["AST", "Seções", "Diagnostics", "JSON", "Testes da gramática", "Interface de seções"])

with tabs[0]:
    st.subheader("Python object / AST clínica genérica")
    st.json(compiled.to_dict())

with tabs[1]:
    if not compiled.sections:
        st.info("Nenhuma seção compilada.")
    else:
        section_names = [section.section_name for section in compiled.sections]
        section_name = st.selectbox("Seção", section_names)
        section = next(section for section in compiled.sections if section.section_name == section_name)
        st.markdown(f"**section_value:** {section.section_value or '-'}")
        st.markdown(f"**commented_values:** {section.commented_values or '-'}")
        st.markdown(f"**ignored_comments:** {section.ignored_comments or '-'}")
        st.json(section)
        st.code(section.raw_text, language="text")

with tabs[2]:
    df = diagnostics_dataframe(compiled)
    if df.empty:
        st.success("Sem diagnostics.")
    else:
        diag_tabs = st.tabs(["Sintáticos", "Semânticos", "Todos"])
        with diag_tabs[0]:
            st.dataframe(df[df["phase"] == "syntactic"], use_container_width=True)
        with diag_tabs[1]:
            st.dataframe(df[df["phase"] == "semantic"], use_container_width=True)
        with diag_tabs[2]:
            st.dataframe(df, use_container_width=True)

with tabs[3]:
    st.download_button("Baixar compiled.json", compiled.to_json(), file_name="compiled.json", mime="application/json")
    st.json(compiled.to_dict())

with tabs[4]:
    rows = []
    for name, source, expected_code in MINIMAL_TEST_CASES:
        result = compile_medievo(source)
        found_codes = [diagnostic.code for diagnostic in result.diagnostics]
        passed = expected_code in found_codes if expected_code else not result.errors()
        rows.append(
            {
                "teste": name,
                "esperado": expected_code or "sem erro",
                "resultado": ", ".join(found_codes) or "sem erro",
                "passou": passed,
                "fonte": source,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

with tabs[5]:
    st.markdown(
        """
A linguagem mínima não deve saber regras clínicas específicas. Para expandir, crie uma classe que herda de `BaseSpecificSectionParser`, declare seus configs e registre no `SectionRegistry`.

```python
from med_evo import compile_medievo
from med_evo.sections import (
    BaseSpecificSectionParser,
    ItemParserConfig,
    SectionParserConfig,
    SectionRegistry,
    SubsectionParserConfig,
)

class MedicamentosSection(BaseSpecificSectionParser):
    section_parser = SectionParserConfig(
        canonical_name="MEDICAMENTOS",
        accepted_names=("MEDICAMENTOS", "MEDICAÇÕES", "MEDICACOES"),
        required=False,
    )
    subsection_parser = SubsectionParserConfig(
        default_subsections=("Atual", "Prévio", "Suspenso"),
        allow_new=True,
    )
    item_parser = ItemParserConfig(require_key=False, allow_free_text=True)

registry = SectionRegistry([MedicamentosSection()])
compiled = compile_medievo(text, section_registry=registry)
```
"""
    )
