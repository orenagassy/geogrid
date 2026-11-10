"""Patch conservador do frontend GeoGrid ZURI. Execute na raiz do repositorio.
Nao altera main.py, metrics.py ou banco de dados.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv)>1 else '.') / 'app' / 'static'
paths = {n: root/n for n in ('app.js','index.html','style.css')}
original = {n:p.read_text(encoding='utf-8') for n,p in paths.items()}
js,html,css = (original[n] for n in ('app.js','index.html','style.css'))
if 'ZURI_PANEL_V1' in js:
    raise SystemExit('Painel ZURI ja instalado. Nenhum arquivo alterado.')

def replace_once(src,old,new,name):
    count=src.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: esperado 1 trecho, encontrado {count}: {old[:80]!r}')
    return src.replace(old,new,1)

html=replace_once(html,'<button data-mode="rank" class="on">Ranks</button>', '<button data-mode="rank" class="on">Ranks</button>\n      <button data-mode="difficulty" id="difficultyBtn" title="Dificuldade experimental da area">Dificuldade</button>', 'index.html')
html=replace_once(html,'<div id="viewing" class="small"></div>', '<div id="analysisInfo" class="small muted"></div>\n    <div id="viewing" class="small"></div>', 'index.html')
html=replace_once(html,'<div class="legend card">','<div class="legend card" id="rankLegend">','index.html')
html=replace_once(html,'</div>\n</main>\n\n<script src="/static/app.js"></script>', '''</div>
  <div class="legend card hidden" id="difficultyLegend">
    <span><i class="sw ida-easy"></i>0–34,9</span>
    <span><i class="sw ida-medium"></i>35–69,9</span>
    <span><i class="sw ida-hard"></i>70–100</span>
    <span><i class="sw rx"></i>sem dados/erro</span>
  </div>
</main>

<script src="/static/app.js"></script>''','index.html')
css+='''
/* ZURI_PANEL_V1: indicadores e mapa de dificuldade */
#scanCard { width: min(520px, calc(100% - 24px)); }
#metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
#metrics .metric .v { font-size: 19px; }
#analysisInfo { margin: 4px 0 8px; }
.pin.ida-easy, .sw.ida-easy { background: #16a34a; }
.pin.ida-medium, .sw.ida-medium { background: #eab308; color: #302500; }
.pin.ida-hard, .sw.ida-hard { background: #dc2626; }
.pin.ida-missing { background: #9ca3af; }
@media (max-width: 800px) { #scanCard { width: calc(100% - 24px); } }
'''
js=replace_once(js,'  center: null, mode: "rank", competitor: null, pollTimer: null,','  center: null, mode: "rank", competitor: null, pollTimer: null, analysis: null, analysisScanId: null,', 'app.js')
js=replace_once(js,'  S.scan = scan;\n  if (switched', '  S.scan = scan;\n  if (switched) { S.analysis = null; S.analysisScanId = null; }\n  if (switched','app.js')
js=replace_once(js,'  renderScan(switched);\n  document.querySelectorAll', '  renderScan(switched);\n  if (scan.status === "done" && (switched || !S.analysis)) loadZuriAnalysis(id);\n  document.querySelectorAll','app.js')
js=replace_once(js,'  stopPolling(); S.scan = null; S.competitor = null;', '  stopPolling(); S.scan = null; S.competitor = null; S.analysis = null; S.analysisScanId = null;','app.js')
js=replace_once(js,'  if (!cmp && S.mode === "delta") S.mode = "rank";', '  if (!cmp && S.mode === "delta") S.mode = "rank";\n  if (S.mode === "difficulty" && !S.analysis) S.mode = "rank";\n  $("#difficultyBtn").disabled = !S.analysis || !!S.competitor;\n  $("#rankLegend").classList.toggle("hidden", S.mode === "difficulty");\n  $("#difficultyLegend").classList.toggle("hidden", S.mode !== "difficulty");','app.js')
js=replace_once(js,'  renderMetrics();\n  const cmp', '  renderMetrics();\n  const info = $("#analysisInfo");\n  info.textContent = S.analysis ? `IDA experimental · ${S.analysis.ida_evaluated_points ?? 0} pontos avaliados · ${fmt(S.analysis.ida_coverage_pct, "%")} de cobertura` : (s.status === "done" ? "Carregando análise IVL/IDA…" : "");\n  const cmp','app.js')
js=replace_once(js,'    ["Found", fmt(m.found_pct, "%"), "points in top 20", delta("found_pct", false)],', '''    ["Found", fmt(m.found_pct, "%"), "points in top 20", delta("found_pct", false)],
    ["IVL", S.competitor ? "–" : fmt(S.analysis?.metrics?.ivl, "%"), "Indice de visibilidade local (pontos validos)", ""],
    ["IDA", S.competitor ? "–" : fmt(S.analysis?.ida_average), "Indice experimental de dificuldade (0 a 100)", ""],''','app.js')
js=replace_once(js,'      if (S.mode === "delta" && s.comparison) {','''      if (S.mode === "difficulty" && S.analysis && !S.competitor) {
        const a = (S.analysis.points || []).find((x) => x.row === row && x.col === col);
        const ida = a?.difficulty?.ida;
        if (ida === null || ida === undefined) { cls = "ida-missing"; label = "?"; }
        else { cls = ida < 35 ? "ida-easy" : ida < 70 ? "ida-medium" : "ida-hard"; label = String(Math.round(ida)); }
      } else if (S.mode === "delta" && s.comparison) {''','app.js')
js=replace_once(js,'  const items = p.results.map((r) =>', '''  const a = S.analysis?.points?.find((x) => x.row === p.row && x.col === p.col);
  const ida = a?.difficulty?.ida;
  const difficultyText = ida == null ? "IDA: dados insuficientes" : `IDA experimental: ${ida} / 100 (${esc(a.difficulty.level)})`;
  const items = p.results.map((r) =>''','app.js')
js=replace_once(js,'    <div class="muted">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}</div><ol>', '    <div class="muted">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}</div><div>${difficultyText}</div><ol>','app.js')
js=replace_once(js,'  S.mode = b.dataset.mode; if (S.mode === "delta") S.competitor = null;', '  S.mode = b.dataset.mode; if (S.mode === "delta" || S.mode === "difficulty") S.competitor = null;','app.js')
js+='''
// ZURI_PANEL_V1: read-only analysis API, never launches a scan.
function zuriCategoryTerms() {
  const cat = (S.business?.category || "").toLowerCase();
  if (cat.includes("advertis") || cat.includes("market") || cat.includes("publicidade")) {
    return ["Marketing agency", "Advertising agency", "Internet marketing service", "Agência de marketing", "Agência de publicidade"];
  }
  return S.business?.category ? [S.business.category] : [];
}
async function loadZuriAnalysis(id) {
  try {
    const params = new URLSearchParams();
    zuriCategoryTerms().forEach((term) => params.append("category", term));
    const query = params.toString();
    const analysis = await api(`/api/scans/${id}/analysis${query ? "?" + query : ""}`);
    if (!S.scan || S.scan.id !== id) return;
    S.analysis = analysis;
    S.analysisScanId = id;
    renderScan(false);
  } catch (err) {
    if (!S.scan || S.scan.id !== id) return;
    $("#analysisInfo").textContent = `Análise IVL/IDA indisponível: ${err.message}`;
  }
}
'''
# no write until every assertion passed
for name,body in [('app.js',js),('index.html',html),('style.css',css)]:
    paths[name].write_text(body,encoding='utf-8')
print('OK: frontend atualizado (app.js, index.html, style.css). Backend e banco preservados.')
