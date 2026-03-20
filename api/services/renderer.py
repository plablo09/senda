from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path

class RenderError(Exception):
    """Raised when quarto render exits non-zero."""

def render_qmd(qmd_source: str, documento_id: str) -> bytes:
    """
    Write qmd_source to a temp file, run quarto render, return rendered HTML bytes.
    Raises RenderError with stderr on failure.
    """
    with tempfile.TemporaryDirectory(prefix=f"senda_{documento_id}_") as tmpdir:
        tmp = Path(tmpdir)
        qmd_path = tmp / "documento.qmd"
        qmd_path.write_text(qmd_source, encoding="utf-8")

        # Copy the senda-live extension into the temp dir
        # The worker container has the repo at /app so extensions are at /app/_extensions
        import shutil
        extensions_src = Path("/app/_extensions")
        if extensions_src.exists():
            shutil.copytree(extensions_src, tmp / "_extensions")

        result = subprocess.run(
            ["quarto", "render", str(qmd_path), "--to", "html", "--quiet"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=120,
        )
        if result.returncode != 0:
            raise RenderError(result.stderr or result.stdout or "Quarto render failed")

        html_path = tmp / "documento.html"
        if not html_path.exists():
            # Quarto might put it in a _files dir or with different name
            html_files = list(tmp.glob("*.html"))
            if not html_files:
                raise RenderError("No HTML output found after quarto render")
            html_path = html_files[0]

        return html_path.read_bytes()
