from __future__ import annotations
import re
import yaml


def _strip_newlines(s: str) -> str:
    """Remove newlines from single-line fields that are interpolated into QMD directives."""
    return s.replace("\n", " ").replace("\r", " ")


def _escape_string_literal(s: str) -> str:
    """Escape a value for safe use inside a double-quoted Python/R string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _validate_identifier(name: str, fallback: str) -> str:
    """Return name if it is a valid Python/R identifier, otherwise return fallback."""
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return name
    return fallback

DEFAULT_EXECUTION_URL = "ws://localhost:8080/ws/ejecutar"


def build_front_matter(doc: dict) -> str:
    fm = {
        "title": doc.get("titulo", "Sin título"),
        "format": "senda-html",
        "params": {
            "execution_url": doc.get("execution_url", DEFAULT_EXECUTION_URL),
        },
    }
    # allow_unicode=True preserves Spanish characters (á, é, ñ) without escaping
    return f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False)}---\n"


def serialize_text_block(node: dict) -> str:
    return node.get("text", "") + "\n"


def serialize_exercise(node: dict) -> str:
    attrs = node.get("attrs", {})
    lang = attrs.get("language", "python")
    exercise_id = _strip_newlines(attrs.get("exerciseId", "ejercicio"))
    caption = _strip_newlines(attrs.get("caption", "Ejercicio"))
    starter = attrs.get("starterCode", "")
    solution = attrs.get("solutionCode", "")
    hints = attrs.get("hints", [])

    # Use tilde fences so user code containing ``` cannot close the fence early
    fence = f"~~~~~{{{lang}}}"
    close = "~~~~~"

    parts = [fence, f"#| exercise: {exercise_id}", f'#| caption: "{caption}"', starter, close, ""]

    if solution:
        parts += [fence, f"#| exercise: {exercise_id}", "#| solution: true", solution, close, ""]

    for hint in hints:
        parts += [fence, f"#| exercise: {exercise_id}", "#| hint: true", hint, close, ""]

    return "\n".join(parts)


def serialize_nota(node: dict) -> str:
    attrs = node.get("attrs", {})
    nivel = attrs.get("nivel", "tip")
    titulo = attrs.get("titulo", "")
    contenido = attrs.get("contenido", "")

    lines = [f"::: {{.callout-{nivel}}}"]
    if titulo:
        lines.append(f"## {titulo}")
    lines.append(contenido)
    lines.append(":::")
    lines.append("")
    return "\n".join(lines)


def serialize_ecuacion(node: dict) -> str:
    attrs = node.get("attrs", {})
    modo = attrs.get("modo", "bloque")
    latex = attrs.get("latex", "")

    if modo == "linea":
        return f"${latex}$\n"
    else:
        return f"$$\n{latex}\n$$\n"


def serialize_cargador_datos(node: dict) -> str:
    attrs = node.get("attrs", {})
    language = attrs.get("language", "python")
    mimetype = attrs.get("mimetype", "text/csv")
    url = _escape_string_literal(attrs.get("url", ""))
    variable_name = _validate_identifier(attrs.get("variableName", "datos"), "datos")

    if language == "python":
        fence = "```{python}"
        if mimetype == "text/csv":
            code_line = f'{variable_name} = pd.read_csv("{url}")'
        else:
            code_line = f'{variable_name} = gpd.read_file("{url}")'
    else:
        fence = "```{r}"
        if mimetype == "text/csv":
            code_line = f'{variable_name} <- read.csv("{url}")'
        else:
            code_line = f'{variable_name} <- sf::st_read("{url}")'

    close = "```"
    parts = [fence, "#| exercise: false", code_line, close, ""]
    return "\n".join(parts)


def serialize_document(ast: dict, titulo: str = "Sin título") -> str:
    doc_meta = {
        "titulo": titulo,
        "execution_url": ast.get("execution_url", DEFAULT_EXECUTION_URL),
    }
    parts = [build_front_matter(doc_meta)]

    for node in ast.get("blocks", []):
        node_type = node.get("type")
        if node_type == "text":
            parts.append(serialize_text_block(node))
        elif node_type == "exercise":
            parts.append(serialize_exercise(node))
        elif node_type == "nota":
            parts.append(serialize_nota(node))
        elif node_type == "ecuacion":
            parts.append(serialize_ecuacion(node))
        elif node_type == "cargadorDatos":
            parts.append(serialize_cargador_datos(node))

    return "\n".join(parts)
