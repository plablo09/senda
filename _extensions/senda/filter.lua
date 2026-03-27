-- filter.lua
-- Pandoc Lua filter for senda-live interactive exercises

local execution_url = "ws://localhost:8080/ws/ejecutar"

-- Helper: get attribute value from CodeBlock attributes list
local function get_attr(attrs, key)
  for _, pair in ipairs(attrs) do
    if pair[1] == key then return pair[2] end
  end
  return nil
end

-- Helper: escape HTML special characters
local function html_escape(s)
  s = s:gsub("&", "&amp;")
  s = s:gsub("<", "&lt;")
  s = s:gsub(">", "&gt;")
  s = s:gsub('"', "&quot;")
  return s
end

-- Process code blocks that are exercises
function CodeBlock(block)
  local exercise_id = get_attr(block.attr.attributes, "exercise")

  -- If no exercise attribute, leave the block unchanged
  if not exercise_id then
    return nil
  end

  -- Extract attributes
  local language = block.attr.classes[1] or "python"
  local caption = get_attr(block.attr.attributes, "caption") or "Ejercicio"
  local is_solution_raw = get_attr(block.attr.attributes, "solution")
  local is_hint_raw = get_attr(block.attr.attributes, "hint")
  local is_solution = is_solution_raw == "true" or is_solution_raw == "1"
  local is_hint = is_hint_raw == "true" or is_hint_raw == "1"
  local starter_code = block.text

  local html

  if is_solution then
    html = string.format(
      '<div class="senda-solution" data-exercise-id="%s" style="display:none"><pre>%s</pre></div>',
      html_escape(exercise_id),
      html_escape(starter_code)
    )
  elseif is_hint then
    html = string.format(
      '<div class="senda-hint" data-exercise-id="%s" style="display:none"><pre>%s</pre></div>',
      html_escape(exercise_id),
      html_escape(starter_code)
    )
  else
    html = string.format(
      '<div class="senda-exercise" data-exercise-id="%s" data-language="%s" data-caption="%s" data-execution-url="%s"><pre class="senda-starter-code">%s</pre></div>',
      html_escape(exercise_id),
      html_escape(language),
      html_escape(caption),
      html_escape(execution_url),
      html_escape(starter_code)
    )
  end

  return pandoc.RawBlock("html", html)
end

-- Process document metadata and inject scripts/styles into head
function Meta(meta)
  -- Read execution_url from params if available
  if meta.params and meta.params.execution_url then
    local url_val = meta.params.execution_url
    if type(url_val) == "table" and url_val.t == "MetaInlines" then
      local parts = {}
      for _, inline in ipairs(url_val) do
        if inline.t == "Str" then
          table.insert(parts, inline.text)
        elseif inline.t == "Space" then
          table.insert(parts, " ")
        end
      end
      execution_url = table.concat(parts)
    elseif type(url_val) == "string" then
      execution_url = url_val
    end
  end

  -- Build the header injection HTML
  local header_html = string.format([[
<script>window.SENDA_EXECUTION_URL = "%s";</script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@6/dist/index.min.js"></script>
<script src="senda-live.js"></script>
]], execution_url)

  -- Append to header-includes in meta
  local header_block = pandoc.RawBlock("html", header_html)

  if meta["header-includes"] then
    if meta["header-includes"].t == "MetaList" then
      table.insert(meta["header-includes"], pandoc.MetaBlocks({header_block}))
    else
      meta["header-includes"] = pandoc.MetaList({
        meta["header-includes"],
        pandoc.MetaBlocks({header_block})
      })
    end
  else
    meta["header-includes"] = pandoc.MetaList({
      pandoc.MetaBlocks({header_block})
    })
  end

  return meta
end

return {
  { Meta = Meta },
  { CodeBlock = CodeBlock }
}
