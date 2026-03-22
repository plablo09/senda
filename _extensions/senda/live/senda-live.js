/* senda-live.js — Senda interactive exercise runtime */

/* ─── Inline styles ─────────────────────────────────────────────────────── */
(function injectStyles() {
  const css = `
.senda-cell {
  border: 1px solid #dee2e6;
  border-radius: 6px;
  margin: 1.5rem 0;
  overflow: hidden;
  font-family: inherit;
}
.senda-caption {
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
  padding: 0.5rem 0.75rem;
  font-weight: 600;
  font-size: 0.9rem;
  color: #495057;
}
.senda-editor {
  min-height: 80px;
}
.senda-editor textarea {
  width: 100%;
  box-sizing: border-box;
  min-height: 80px;
  padding: 0.5rem;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.875rem;
  border: none;
  border-bottom: 1px solid #dee2e6;
  resize: vertical;
  outline: none;
}
.senda-toolbar {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
  flex-wrap: wrap;
}
.senda-btn-run,
.senda-btn-hint,
.senda-btn-solution {
  padding: 0.3rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: background 0.15s;
}
.senda-btn-run {
  background: #0d6efd;
  color: #fff;
  border-color: #0d6efd;
}
.senda-btn-run:hover { background: #0b5ed7; }
.senda-btn-run:disabled { opacity: 0.65; cursor: not-allowed; }
.senda-btn-hint {
  background: #fff;
  color: #6c757d;
  border-color: #ced4da;
}
.senda-btn-hint:hover { background: #e9ecef; }
.senda-btn-solution {
  background: #fff;
  color: #6c757d;
  border-color: #ced4da;
}
.senda-btn-solution:hover { background: #e9ecef; }
.senda-output {
  padding: 0.5rem 0.75rem;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 0.875rem;
  white-space: pre-wrap;
  min-height: 0;
  max-height: 300px;
  overflow-y: auto;
  background: #1e1e1e;
  color: #d4d4d4;
}
.senda-output:empty { display: none; }
.senda-output .out-error { color: #f48771; }
.senda-output .out-success { color: #4ec9b0; }
.senda-output img { max-width: 100%; display: block; margin: 0.25rem 0; }
.senda-feedback {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  background: #fff8e1;
  border-top: 1px solid #ffe082;
  color: #5d4037;
}
.senda-feedback:empty { display: none; }
.senda-hint,
.senda-solution {
  margin: 0.5rem 0;
  padding: 0.75rem;
  background: #f1f8e9;
  border-left: 4px solid #8bc34a;
  border-radius: 0 4px 4px 0;
}
.senda-hint pre,
.senda-solution pre {
  margin: 0;
  font-size: 0.875rem;
}
`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);
})();

/* ─── Helpers ───────────────────────────────────────────────────────────── */

/**
 * Try to get the current editor value regardless of whether we used
 * CodeMirror or a plain textarea.
 */
function getEditorValue(editorContainer) {
  if (editorContainer._cmView) {
    return editorContainer._cmView.state.doc.toString();
  }
  const ta = editorContainer.querySelector('textarea');
  return ta ? ta.value : '';
}

/**
 * Attempt to mount a CodeMirror 6 editor. Returns true on success.
 * Falls back to textarea if CodeMirror is not available.
 */
function mountEditor(container, initialCode, language) {
  try {
    // CodeMirror 6 exposes itself as window.CodeMirror (the bundled index)
    // or as individual packages. The CDN bundle from codemirror@6 attaches
    // to window via the ES module shim – check common entry points.
    const CM = window.CodeMirror || (window.cm6 && window.cm6.CodeMirror);

    if (CM && CM.EditorView && CM.basicSetup !== undefined) {
      // Full basic-setup bundle available
      const extensions = [CM.basicSetup];

      // Add language support if available
      if (language === 'python' && window.codemirrorLangPython) {
        extensions.push(window.codemirrorLangPython.python());
      } else if ((language === 'r') && window.codemirrorLangR) {
        extensions.push(window.codemirrorLangR.r());
      }

      const view = new CM.EditorView({
        doc: initialCode,
        extensions,
        parent: container
      });
      container._cmView = view;
      return true;
    }
  } catch (e) {
    console.warn('senda-live: CodeMirror no disponible, usando textarea como alternativa.', e);
  }

  // Fallback: plain textarea
  const ta = document.createElement('textarea');
  ta.value = initialCode;
  ta.spellcheck = false;
  ta.autocomplete = 'off';
  ta.autocorrect = 'off';
  ta.autocapitalize = 'off';
  container.appendChild(ta);
  return false;
}

/* ─── Session identity ──────────────────────────────────────────────────── */

function getSessionId() {
  let id = sessionStorage.getItem('senda_session_id');
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    sessionStorage.setItem('senda_session_id', id);
  }
  return id;
}

/* ─── WebSocket execution ───────────────────────────────────────────────── */

function ejecutarCodigo(params) {
  const { exerciseId, language, code, executionUrl, outputDiv, feedbackDiv, runBtn } = params;

  outputDiv.innerHTML = '';
  feedbackDiv.innerHTML = '';
  outputDiv.style.display = 'block';
  runBtn.disabled = true;
  runBtn.textContent = '⏳ Ejecutando...';

  // Collect stderr across chunks; trigger feedback at "fin" if non-empty
  let stderrAccumulated = '';

  let ws;
  try {
    ws = new WebSocket(executionUrl);
  } catch (err) {
    appendOutput(outputDiv, `Error al conectar: ${err.message}`, 'out-error');
    runBtn.disabled = false;
    runBtn.textContent = '▶ Ejecutar';
    return;
  }

  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({
      exercise_id: exerciseId,
      language: language,
      code: code
    }));
  });

  ws.addEventListener('message', (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (_) {
      appendOutput(outputDiv, event.data, null);
      return;
    }

    const tipo = msg.tipo || msg.type;
    const contenido = msg.contenido !== undefined ? msg.contenido : (msg.content !== undefined ? msg.content : '');

    switch (tipo) {
      case 'stdout':
        appendOutput(outputDiv, contenido, null);
        break;
      case 'stderr':
        appendOutput(outputDiv, contenido, 'out-error');
        stderrAccumulated += contenido;
        break;
      case 'imagen':
      case 'image': {
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${contenido}`;
        img.alt = 'Resultado gráfico';
        outputDiv.appendChild(img);
        break;
      }
      case 'error': {
        // System-level error (pool exhausted, unsupported language)
        appendOutput(outputDiv, contenido, 'out-error');
        solicitarRetroalimentacion(exerciseId, contenido, getEditorValue, feedbackDiv);
        break;
      }
      case 'fin':
      case 'done': {
        // Trigger feedback if any stderr (Python/R tracebacks) was collected
        if (stderrAccumulated.trim()) {
          solicitarRetroalimentacion(exerciseId, stderrAccumulated, getEditorValue, feedbackDiv);
        }
        const span = document.createElement('span');
        span.className = 'out-success';
        span.textContent = '✓ Ejecución completada\n';
        outputDiv.appendChild(span);
        runBtn.disabled = false;
        runBtn.textContent = '▶ Ejecutar';
        ws.close();
        break;
      }
      default:
        if (contenido) appendOutput(outputDiv, contenido, null);
    }
  });

  ws.addEventListener('error', () => {
    appendOutput(outputDiv, 'Error de conexión con el servidor de ejecución.', 'out-error');
    runBtn.disabled = false;
    runBtn.textContent = '▶ Ejecutar';
  });

  ws.addEventListener('close', (event) => {
    if (!event.wasClean && runBtn.disabled) {
      runBtn.disabled = false;
      runBtn.textContent = '▶ Ejecutar';
    }
  });
}

function appendOutput(container, text, cssClass) {
  container.style.display = 'block';
  if (cssClass) {
    const span = document.createElement('span');
    span.className = cssClass;
    span.textContent = text;
    container.appendChild(span);
  } else {
    container.appendChild(document.createTextNode(text));
  }
}

/* ─── AI feedback ───────────────────────────────────────────────────────── */

async function solicitarRetroalimentacion(exerciseId, errorOutput, getCode, feedbackDiv) {
  feedbackDiv.innerHTML = '<em>Obteniendo retroalimentación...</em>';
  try {
    const codigoEstudiante = typeof getCode === 'function' ? getCode() : '';
    const resp = await fetch(`/api/retroalimentacion/${encodeURIComponent(exerciseId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        codigo_estudiante: codigoEstudiante,
        error_output: errorOutput,
        session_id: getSessionId()
      })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    // Silence window — student should try independently
    if (data.silencio && !data.limite) {
      feedbackDiv.innerHTML = '';
      return;
    }

    // Hard limit reached
    if (data.limite) {
      feedbackDiv.innerHTML = `<em>${escapeHtml(data.retroalimentacion)}</em>`;
      return;
    }

    let html = `<strong>Retroalimentación:</strong> ${escapeHtml(data.retroalimentacion)}`;
    if (data.pregunta_guia) {
      html += `<br><strong>Para reflexionar:</strong> ${escapeHtml(data.pregunta_guia)}`;
    }
    feedbackDiv.innerHTML = html;
  } catch (_) {
    feedbackDiv.textContent = 'No se pudo obtener retroalimentación en este momento.';
  }
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ─── Toggle helpers ────────────────────────────────────────────────────── */

function toggleElement(el) {
  if (!el) return;
  el.style.display = el.style.display === 'none' ? '' : 'none';
}

/* ─── Main initialisation ───────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  const executionUrl = window.SENDA_EXECUTION_URL || 'ws://localhost:8080/ws/ejecutar';

  const exercises = document.querySelectorAll('.senda-exercise');

  exercises.forEach((exerciseDiv) => {
    const exerciseId = exerciseDiv.dataset.exerciseId;
    const language = exerciseDiv.dataset.language || 'python';
    const caption = exerciseDiv.dataset.caption || 'Ejercicio';
    const execUrl = exerciseDiv.dataset.executionUrl || executionUrl;

    // Grab starter code before replacing content
    const starterPre = exerciseDiv.querySelector('.senda-starter-code');
    const starterCode = starterPre ? starterPre.textContent : '';

    // Build the cell UI
    const cell = document.createElement('div');
    cell.className = 'senda-cell';

    // Caption bar
    const captionDiv = document.createElement('div');
    captionDiv.className = 'senda-caption';
    captionDiv.textContent = caption;
    cell.appendChild(captionDiv);

    // Editor container
    const editorDiv = document.createElement('div');
    editorDiv.className = 'senda-editor';
    cell.appendChild(editorDiv);

    // Toolbar
    const toolbar = document.createElement('div');
    toolbar.className = 'senda-toolbar';

    const runBtn = document.createElement('button');
    runBtn.className = 'senda-btn-run';
    runBtn.textContent = '▶ Ejecutar';

    const hintBtn = document.createElement('button');
    hintBtn.className = 'senda-btn-hint';
    hintBtn.textContent = '💡 Ver pista';

    const solutionBtn = document.createElement('button');
    solutionBtn.className = 'senda-btn-solution';
    solutionBtn.textContent = '👁 Ver solución';

    toolbar.appendChild(runBtn);
    toolbar.appendChild(hintBtn);
    toolbar.appendChild(solutionBtn);
    cell.appendChild(toolbar);

    // Output area
    const outputDiv = document.createElement('div');
    outputDiv.className = 'senda-output';
    cell.appendChild(outputDiv);

    // Feedback area
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'senda-feedback';
    cell.appendChild(feedbackDiv);

    // Replace exercise div content with the assembled cell
    exerciseDiv.innerHTML = '';
    exerciseDiv.appendChild(cell);

    // Mount editor (CodeMirror or textarea fallback)
    mountEditor(editorDiv, starterCode, language);

    // Wire "Ejecutar" button
    runBtn.addEventListener('click', () => {
      const code = getEditorValue(editorDiv);
      ejecutarCodigo({
        exerciseId,
        language,
        code,
        executionUrl: execUrl,
        outputDiv,
        feedbackDiv,
        runBtn
      });
    });

    // Wire "Ver pista" button
    hintBtn.addEventListener('click', () => {
      const hintEl = document.querySelector(`.senda-hint[data-exercise-id="${CSS.escape(exerciseId)}"]`);
      if (hintEl) {
        toggleElement(hintEl);
      } else {
        hintBtn.disabled = true;
        hintBtn.title = 'No hay pista disponible para este ejercicio.';
      }
    });

    // Wire "Ver solución" button
    solutionBtn.addEventListener('click', () => {
      const solutionEl = document.querySelector(`.senda-solution[data-exercise-id="${CSS.escape(exerciseId)}"]`);
      if (solutionEl) {
        toggleElement(solutionEl);
      } else {
        solutionBtn.disabled = true;
        solutionBtn.title = 'No hay solución disponible para este ejercicio.';
      }
    });
  });
});
