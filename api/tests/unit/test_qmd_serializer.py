import pytest
import yaml
from api.services.qmd_serializer import (
    build_front_matter,
    serialize_exercise,
    serialize_text_block,
    serialize_document,
    serialize_nota,
    serialize_ecuacion,
    serialize_cargador_datos,
)


# ---------------------------------------------------------------------------
# build_front_matter
# ---------------------------------------------------------------------------

class TestBuildFrontMatter:
    def _parse_fm(self, raw: str) -> dict:
        """Strip --- delimiters and parse YAML."""
        assert raw.startswith("---\n"), "Front matter must start with ---"
        assert "---\n" in raw[4:], "Front matter must have closing ---"
        inner = raw[4:raw.index("---\n", 4)]
        return yaml.safe_load(inner)

    def test_returns_string_with_delimiters(self):
        doc = {"titulo": "Hello", "execution_url": "ws://host/ws"}
        result = build_front_matter(doc)
        assert result.startswith("---\n")
        assert result.strip().endswith("---")

    def test_includes_title(self):
        doc = {"titulo": "My Document", "execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["title"] == "My Document"

    def test_includes_format_senda_html(self):
        doc = {"titulo": "X", "execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["format"] == "senda-html"

    def test_includes_execution_url_in_params(self):
        url = "ws://localhost:9999/ws/run"
        doc = {"titulo": "X", "execution_url": url}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["params"]["execution_url"] == url

    def test_spanish_characters_not_escaped(self):
        doc = {"titulo": "Árboles y ñoñerías", "execution_url": "ws://host/ws"}
        raw = build_front_matter(doc)
        # Spanish chars must appear literally, not as escape sequences like \xc3
        assert "Árboles" in raw
        assert "ñoñerías" in raw
        # Must still parse correctly
        parsed = self._parse_fm(raw)
        assert parsed["title"] == "Árboles y ñoñerías"

    def test_title_with_colon_doesnt_break_yaml(self):
        doc = {"titulo": "Intro: parte 1", "execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["title"] == "Intro: parte 1"

    def test_title_with_double_quotes_doesnt_break_yaml(self):
        doc = {"titulo": 'Say "hello"', "execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["title"] == 'Say "hello"'

    def test_title_with_single_quotes_doesnt_break_yaml(self):
        doc = {"titulo": "L'eau", "execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["title"] == "L'eau"

    def test_missing_titulo_defaults_to_sin_titulo(self):
        doc = {"execution_url": "ws://host/ws"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["title"] == "Sin título"

    def test_missing_execution_url_uses_default(self):
        from api.services.qmd_serializer import DEFAULT_EXECUTION_URL
        doc = {"titulo": "X"}
        parsed = self._parse_fm(build_front_matter(doc))
        assert parsed["params"]["execution_url"] == DEFAULT_EXECUTION_URL


# ---------------------------------------------------------------------------
# serialize_text_block
# ---------------------------------------------------------------------------

class TestSerializeTextBlock:
    def test_returns_text_field(self):
        node = {"type": "text", "text": "## Introducción\n\nEste es un párrafo."}
        result = serialize_text_block(node)
        assert "## Introducción" in result
        assert "Este es un párrafo." in result

    def test_returns_text_with_trailing_newline(self):
        node = {"type": "text", "text": "Hello"}
        result = serialize_text_block(node)
        assert result.endswith("\n")

    def test_empty_text_graceful(self):
        node = {"type": "text", "text": ""}
        result = serialize_text_block(node)
        assert isinstance(result, str)
        assert result == "\n"

    def test_missing_text_key_graceful(self):
        node = {"type": "text"}
        result = serialize_text_block(node)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# serialize_exercise
# ---------------------------------------------------------------------------

class TestSerializeExercise:
    def _make_node(self, **kwargs):
        attrs = {
            "language": kwargs.get("language", "python"),
            "exerciseId": kwargs.get("exerciseId", "ej1"),
            "caption": kwargs.get("caption", "Ejercicio 1"),
            "starterCode": kwargs.get("starterCode", "x = ____"),
            "solutionCode": kwargs.get("solutionCode", ""),
            "hints": kwargs.get("hints", []),
        }
        return {"type": "exercise", "attrs": attrs}

    def test_starter_code_only_produces_one_fenced_block(self):
        node = self._make_node(starterCode="x = ____", solutionCode="", hints=[])
        result = serialize_exercise(node)
        assert result.count("~~~~~{python}") == 1

    def test_starter_code_has_exercise_option(self):
        node = self._make_node(exerciseId="ej1", starterCode="x = ____")
        result = serialize_exercise(node)
        assert "#| exercise: ej1" in result

    def test_starter_code_has_caption_option(self):
        node = self._make_node(caption="Mi ejercicio", starterCode="x = ____")
        result = serialize_exercise(node)
        assert '#| caption: "Mi ejercicio"' in result

    def test_with_solution_produces_two_fenced_blocks(self):
        node = self._make_node(starterCode="x = ____", solutionCode="x = 42")
        result = serialize_exercise(node)
        assert result.count("~~~~~{python}") == 2

    def test_solution_block_has_solution_option(self):
        node = self._make_node(starterCode="x = ____", solutionCode="x = 42")
        result = serialize_exercise(node)
        assert "#| solution: true" in result

    def test_with_one_hint_produces_two_fenced_blocks(self):
        node = self._make_node(starterCode="x = ____", solutionCode="", hints=["Try 42"])
        result = serialize_exercise(node)
        assert result.count("~~~~~{python}") == 2

    def test_hint_block_has_hint_option(self):
        node = self._make_node(starterCode="x = ____", hints=["Try 42"])
        result = serialize_exercise(node)
        assert "#| hint: true" in result

    def test_with_multiple_hints_produces_correct_block_count(self):
        node = self._make_node(starterCode="x = ____", hints=["Hint A", "Hint B", "Hint C"])
        result = serialize_exercise(node)
        # 1 exercise + 3 hints = 4 blocks
        assert result.count("~~~~~{python}") == 4
        assert result.count("#| hint: true") == 3

    def test_with_all_three_correct_order(self):
        node = self._make_node(
            starterCode="x = ____",
            solutionCode="x = 42",
            hints=["Hint A", "Hint B"],
        )
        result = serialize_exercise(node)
        exercise_pos = result.index("#| exercise: ej1")
        solution_pos = result.index("#| solution: true")
        hint_pos = result.index("#| hint: true")
        assert exercise_pos < solution_pos < hint_pos

    def test_language_python_uses_python_fence(self):
        node = self._make_node(language="python")
        result = serialize_exercise(node)
        assert "~~~~~{python}" in result

    def test_language_r_uses_r_fence(self):
        node = self._make_node(language="r")
        result = serialize_exercise(node)
        assert "~~~~~{r}" in result
        assert "~~~~~{python}" not in result

    def test_placeholder_preserved_as_is(self):
        node = self._make_node(starterCode="result = ____\nprint(____)")
        result = serialize_exercise(node)
        assert "result = ____" in result
        assert "print(____)" in result

    def test_multiple_hints_all_content_present(self):
        node = self._make_node(hints=["First hint", "Second hint"])
        result = serialize_exercise(node)
        assert "First hint" in result
        assert "Second hint" in result


# ---------------------------------------------------------------------------
# serialize_document
# ---------------------------------------------------------------------------

class TestSerializeDocument:
    def test_empty_ast_produces_front_matter_only(self):
        ast = {"blocks": []}
        result = serialize_document(ast, titulo="Empty Doc")
        assert result.startswith("---\n")
        # Should contain closing delimiter
        assert "---" in result

    def test_output_starts_with_front_matter(self):
        ast = {"blocks": []}
        result = serialize_document(ast, titulo="Test")
        assert result.startswith("---\n")

    def test_front_matter_contains_title(self):
        ast = {"blocks": []}
        result = serialize_document(ast, titulo="Mi Documento")
        assert "Mi Documento" in result

    def test_ast_with_text_block(self):
        ast = {
            "blocks": [
                {"type": "text", "text": "## Sección\n\nContenido aquí."},
            ]
        }
        result = serialize_document(ast, titulo="Doc")
        assert "## Sección" in result
        assert "Contenido aquí." in result

    def test_ast_with_exercise_block(self):
        ast = {
            "blocks": [
                {
                    "type": "exercise",
                    "attrs": {
                        "language": "python",
                        "exerciseId": "ej1",
                        "caption": "Ejercicio 1",
                        "starterCode": "x = ____",
                        "solutionCode": "",
                        "hints": [],
                    },
                }
            ]
        }
        result = serialize_document(ast, titulo="Doc")
        assert "~~~~~{python}" in result
        assert "#| exercise: ej1" in result

    def test_ast_with_text_and_exercise(self):
        ast = {
            "blocks": [
                {"type": "text", "text": "Intro text."},
                {
                    "type": "exercise",
                    "attrs": {
                        "language": "python",
                        "exerciseId": "ej2",
                        "caption": "Cap",
                        "starterCode": "y = ____",
                        "solutionCode": "y = 99",
                        "hints": [],
                    },
                },
            ]
        }
        result = serialize_document(ast, titulo="Full Doc")
        assert "Intro text." in result
        assert "~~~~~{python}" in result
        assert "#| exercise: ej2" in result
        assert "#| solution: true" in result

    def test_default_titulo_is_sin_titulo(self):
        ast = {"blocks": []}
        result = serialize_document(ast)
        assert "Sin título" in result


# ---------------------------------------------------------------------------
# serialize_nota
# ---------------------------------------------------------------------------

class TestSerializeNota:
    def _make_node(self, nivel="tip", titulo="Título", contenido="Texto de la nota"):
        return {
            "type": "nota",
            "attrs": {
                "nivel": nivel,
                "titulo": titulo,
                "contenido": contenido,
            },
        }

    def test_tip_callout_with_titulo_and_contenido(self):
        node = self._make_node(nivel="tip", titulo="Mi Título", contenido="Texto aquí")
        result = serialize_nota(node)
        assert "::: {.callout-tip}" in result
        assert "## Mi Título" in result
        assert "Texto aquí" in result
        assert ":::" in result

    def test_note_level_maps_to_callout_note(self):
        node = self._make_node(nivel="note")
        result = serialize_nota(node)
        assert "::: {.callout-note}" in result

    def test_warning_level_maps_to_callout_warning(self):
        node = self._make_node(nivel="warning")
        result = serialize_nota(node)
        assert "::: {.callout-warning}" in result

    def test_important_level_maps_to_callout_important(self):
        node = self._make_node(nivel="important")
        result = serialize_nota(node)
        assert "::: {.callout-important}" in result

    def test_empty_titulo_omits_title_line(self):
        node = self._make_node(titulo="", contenido="Solo contenido")
        result = serialize_nota(node)
        assert "## " not in result
        assert "Solo contenido" in result

    def test_nota_dispatch_in_serialize_document(self):
        ast = {
            "blocks": [
                {
                    "type": "nota",
                    "attrs": {
                        "nivel": "tip",
                        "titulo": "Atención",
                        "contenido": "Recuerda esto.",
                    },
                }
            ]
        }
        result = serialize_document(ast, titulo="Doc")
        assert "::: {.callout-tip}" in result
        assert "## Atención" in result
        assert "Recuerda esto." in result


# ---------------------------------------------------------------------------
# serialize_ecuacion
# ---------------------------------------------------------------------------

class TestSerializeEcuacion:
    def _make_node(self, modo="bloque", latex=r"\bar{x} = \frac{1}{n}"):
        return {
            "type": "ecuacion",
            "attrs": {
                "modo": modo,
                "latex": latex,
            },
        }

    def test_bloque_mode_wraps_in_double_dollar(self):
        node = self._make_node(modo="bloque", latex=r"\bar{x} = \frac{1}{n}")
        result = serialize_ecuacion(node)
        assert result.startswith("$$\n")
        assert result.strip().endswith("$$")
        assert r"\bar{x} = \frac{1}{n}" in result

    def test_bloque_mode_latex_on_own_line(self):
        latex = r"\sum_{i=1}^{n} x_i"
        node = self._make_node(modo="bloque", latex=latex)
        result = serialize_ecuacion(node)
        lines = result.strip().splitlines()
        assert lines[0] == "$$"
        assert lines[1] == latex
        assert lines[2] == "$$"

    def test_linea_mode_wraps_in_single_dollar(self):
        latex = r"\bar{x}"
        node = self._make_node(modo="linea", latex=latex)
        result = serialize_ecuacion(node)
        assert result.strip() == f"${latex}$"

    def test_ecuacion_dispatch_in_serialize_document(self):
        ast = {
            "blocks": [
                {
                    "type": "ecuacion",
                    "attrs": {
                        "modo": "bloque",
                        "latex": r"E = mc^2",
                    },
                }
            ]
        }
        result = serialize_document(ast, titulo="Doc")
        assert "$$" in result
        assert r"E = mc^2" in result


# ---------------------------------------------------------------------------
# serialize_cargador_datos
# ---------------------------------------------------------------------------

class TestSerializeCargadorDatos:
    def _make_node(self, language="python", mimetype="text/csv",
                   url="http://storage/datasets/uuid/datos.csv",
                   filename="datos.csv", variable_name="datos"):
        return {
            "type": "cargadorDatos",
            "attrs": {
                "language": language,
                "mimetype": mimetype,
                "url": url,
                "filename": filename,
                "variableName": variable_name,
            },
        }

    def test_python_csv_uses_pd_read_csv(self):
        node = self._make_node(language="python", mimetype="text/csv")
        result = serialize_cargador_datos(node)
        assert "pd.read_csv" in result

    def test_python_geojson_uses_gpd_read_file(self):
        node = self._make_node(language="python", mimetype="application/geo+json")
        result = serialize_cargador_datos(node)
        assert "gpd.read_file" in result

    def test_python_zip_uses_gpd_read_file(self):
        node = self._make_node(language="python", mimetype="application/zip")
        result = serialize_cargador_datos(node)
        assert "gpd.read_file" in result

    def test_python_geopackage_uses_gpd_read_file(self):
        node = self._make_node(language="python", mimetype="application/geopackage+sqlite3")
        result = serialize_cargador_datos(node)
        assert "gpd.read_file" in result

    def test_r_csv_uses_read_csv(self):
        node = self._make_node(language="r", mimetype="text/csv")
        result = serialize_cargador_datos(node)
        assert "read.csv" in result

    def test_r_geojson_uses_sf_st_read(self):
        node = self._make_node(language="r", mimetype="application/geo+json")
        result = serialize_cargador_datos(node)
        assert "sf::st_read" in result

    def test_r_zip_uses_sf_st_read(self):
        node = self._make_node(language="r", mimetype="application/zip")
        result = serialize_cargador_datos(node)
        assert "sf::st_read" in result

    def test_r_geopackage_uses_sf_st_read(self):
        node = self._make_node(language="r", mimetype="application/geopackage+sqlite3")
        result = serialize_cargador_datos(node)
        assert "sf::st_read" in result

    def test_custom_variable_name_used(self):
        node = self._make_node(language="python", mimetype="text/csv", variable_name="mi_df")
        result = serialize_cargador_datos(node)
        assert "mi_df" in result

    def test_code_block_tagged_exercise_false(self):
        node = self._make_node(language="python", mimetype="text/csv")
        result = serialize_cargador_datos(node)
        assert "#| exercise: false" in result

    def test_url_included_in_output(self):
        url = "http://storage/datasets/abc123/datos.csv"
        node = self._make_node(language="python", mimetype="text/csv", url=url)
        result = serialize_cargador_datos(node)
        assert url in result

    def test_python_uses_python_fence(self):
        node = self._make_node(language="python", mimetype="text/csv")
        result = serialize_cargador_datos(node)
        assert "```{python}" in result

    def test_r_uses_r_fence(self):
        node = self._make_node(language="r", mimetype="text/csv")
        result = serialize_cargador_datos(node)
        assert "```{r}" in result

    def test_cargador_datos_dispatch_in_serialize_document(self):
        url = "http://storage/datasets/uuid/datos.csv"
        ast = {
            "blocks": [
                {
                    "type": "cargadorDatos",
                    "attrs": {
                        "language": "python",
                        "mimetype": "text/csv",
                        "url": url,
                        "filename": "datos.csv",
                        "variableName": "datos",
                    },
                }
            ]
        }
        result = serialize_document(ast, titulo="Doc")
        assert "pd.read_csv" in result
        assert "#| exercise: false" in result
        assert url in result
