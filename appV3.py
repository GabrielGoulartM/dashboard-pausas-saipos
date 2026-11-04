"""Dashboard de Pausas - Saipos

Painel para o analista acompanhar suas pausas, o status da equipe e
negociar trocas de intervalo, lendo os dados de uma planilha do Google Sheets.

Estrutura do arquivo:
  1. CONFIGURAÇÃO   -> o que normalmente se edita
  2. LÓGICA         -> funções puras (sem Streamlit na regra de negócio)
  3. DADOS          -> leitura da planilha (com cache compartilhado)
  4. INTERFACE      -> telas
"""
import html
import re
from datetime import datetime
from types import SimpleNamespace

import pytz
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ============================================================
# 1. CONFIGURAÇÃO - EDITE AQUI
# ============================================================
SHEET_ID_PADRAO = "1bwrJmasPZUz5F8qsITo2RhFYTHb8e2OnSHlCWLSDOIs"
SHEET_TAB = "pagina"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
FUSO = "America/Sao_Paulo"

# Analistas que não devem mais aparecer em nenhuma lista (ex: desligados)
ANALISTAS_EXCLUIDOS = ["Carolina Bassani Duarte"]

# ------------------------------------------------------------
# MODO MANUTENÇÃO
# True  = mostra só o banner e bloqueia o resto do app
# False = app funciona normalmente
# Também dá para ligar/desligar sem deploy, definindo no painel de
# Secrets do Streamlit Cloud:  manutencao = true   (ou false)
# ------------------------------------------------------------
MANUTENCAO = False
MANUTENCAO_MSG = (
    "Caso o site esteja demorando para carregar, ou fora do ar, por favor "
    "verifique a planilha de pausas da gestão, melhorias a esse site estão a caminho 🚚"
)
MANUTENCAO_PREVISAO = ""  # ex: "Previsão de retorno: hoje às 18h" (vazio = oculta)

# Atualização
INTERVALO_ATUALIZACAO_S = 30  # a tela se atualiza sozinha a cada X segundos
CACHE_TTL_S = 30              # a planilha é lida no máx. 1x a cada X s (todos os usuários juntos)

# Regras de negócio
DURACAO_PAUSA_MIN = {"Intervalo": 60, "Extra": 60}  # duração (min) por tipo de pausa
ALERTA_PROXIMO_MIN = 30   # "🟡 Próximo intervalo" no status quando faltar até X min
IMINENTE_MIN = 5          # destaque pulsante no card quando faltar até X min
JORNADA_PADRAO = ("09:00", "18:00")

# Colunas da planilha (índice começa em 0: A=0, B=1, ... F=5, H=7, K=10)
COL_NOME = 0
COL_FILA = 1
PAUSAS_MAP = [
    {"horario_idx": 5, "motivo_idx": 4, "tipo": "Intervalo", "coluna": "F"},  # almoço/descanso CLT
    {"horario_idx": 7, "motivo_idx": 9, "tipo": "Extra", "coluna": "H"},
    {"horario_idx": 10, "motivo_idx": 12, "tipo": "Extra", "coluna": "K"},
]

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]

STATUS_COR_PADRAO = {"orange": "#ff9800", "blue": "#2196f3", "gray": "#9e9e9e"}

esc = html.escape


# ============================================================
# 2. LÓGICA (funções puras)
# ============================================================
def get_secret(key, default=None):
    """Lê um secret do Streamlit sem quebrar quando não há secrets (ex: rodando local)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


def to_bool(value):
    """Converte secrets em booleano de verdade ('false' como texto NÃO é True)."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "sim", "on", "verdadeiro")
    return bool(value)


def is_excluido(nome):
    nome_norm = str(nome).strip().lower()
    return any(nome_norm == excl.strip().lower() for excl in ANALISTAS_EXCLUIDOS)


_TEMPO_EXATO = re.compile(
    r"(\d{1,2})\s*[:hH]\s*(\d{2})?(?:\s*:\s*\d{2})?\s*([AaPp][Mm])?"
)
_TEMPO_NO_TEXTO = re.compile(r"(?<!\d)(\d{1,2})\s*[:hH]\s*(\d{2})(?!\d)")


def detect_time(val):
    """Converte '13:50', '13h50', '13h', '1:50 PM'... em 'HH:MM'. Devolve None se não for horário.

    Um número solto (ex: '5') NÃO é horário.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    m = _TEMPO_EXATO.fullmatch(s)
    if m:
        h, mi, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ampm:
            h = h % 12 + (12 if ampm.lower() == "pm" else 0)
    else:
        m = _TEMPO_NO_TEXTO.search(s)  # ex: "Almoço 13:50"
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi:02d}"
    return None


def time_to_minutes(time_str):
    if not time_str:
        return None
    try:
        h, m = map(int, str(time_str).split(":"))
        return h * 60 + m
    except (ValueError, TypeError):
        return None


def minutes_to_time(minutes):
    minutes = int(minutes) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_duration(minutes):
    if minutes is None or minutes < 0:
        return "-"
    minutes = int(minutes)
    if minutes < 60:
        return f"{minutes}min"
    h, m = divmod(minutes, 60)
    return f"{h}h" if m == 0 else f"{h}h{m:02d}"


def plural(n, singular, plural_=None):
    return singular if n == 1 else (plural_ or singular + "s")


def agora_br():
    return datetime.now(pytz.timezone(FUSO))


def minutos_do_dia(dt):
    return dt.hour * 60 + dt.minute


def cor_texto(bg_hex):
    """Texto escuro só quando o fundo escolhido for bem claro (mantém o visual padrão)."""
    h = str(bg_hex).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"

    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#1b1b1b" if lum > 0.5 else "#ffffff"


def normalize_fila(fila_text):
    """Normaliza o texto da fila para MA, IMP ou OUTROS."""
    if not fila_text:
        return "OUTROS"
    f = str(fila_text).strip().upper()
    if "MA" in f or "MAR" in f or "ABERTO" in f:
        return "MA"
    if "IMP" in f or "IMPRESS" in f:
        return "IMP"
    return "OUTROS"


def _cell(row, idx):
    if len(row) > idx and row[idx] is not None:
        return str(row[idx]).strip()
    return ""


def parse_turno(row):
    """Horário de início/fim da jornada (regra original preservada)."""
    inicio = detect_time(_cell(row, 3)) or detect_time(_cell(row, 2))
    fim = None
    for idx in (1, 2, 4):
        cand = detect_time(_cell(row, idx))
        if not cand:
            continue
        if inicio:
            a, b = time_to_minutes(inicio), time_to_minutes(cand)
            if a is not None and b is not None and b > a:
                fim = cand
                break
        else:
            fim = cand
    return inicio or JORNADA_PADRAO[0], fim or JORNADA_PADRAO[1]


def parse_pausas(row):
    pausas = []
    for cfg in PAUSAS_MAP:
        horario = detect_time(_cell(row, cfg["horario_idx"]))
        if not horario:
            continue
        tipo = cfg["tipo"]
        motivo = _cell(row, cfg["motivo_idx"]) or ("Intervalo" if tipo == "Intervalo" else "Pausa")
        inicio = time_to_minutes(horario)
        dur = DURACAO_PAUSA_MIN.get(tipo, 60)
        pausas.append({
            "coluna": cfg["coluna"], "horario": horario, "motivo": motivo,
            "tipo": tipo, "inicio": inicio, "fim": inicio + dur, "duracao": dur,
        })
    return sorted(pausas, key=lambda p: p["inicio"])


def parse_analistas(values):
    """Linhas da planilha -> lista de analistas (ignora cabeçalho, vazios, excluídos e duplicados)."""
    analistas, vistos = [], set()
    for row in values[1:]:
        nome = _cell(row, COL_NOME)
        if not nome or is_excluido(nome) or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())
        fila_raw = _cell(row, COL_FILA) or "Não definida"
        turno_ini, turno_fim = parse_turno(row)
        pausas = parse_pausas(row)
        almoco = next((p["horario"] for p in pausas if p["tipo"] == "Intervalo"), None)
        analistas.append({
            "nome": nome, "fila_raw": fila_raw, "fila": normalize_fila(fila_raw),
            "turno_ini": turno_ini, "turno_fim": turno_fim,
            "pausas": pausas, "intervalo_almoco": almoco,
        })
    return analistas


def pausa_atual(pausas, agora):
    return next((p for p in pausas if p["inicio"] <= agora < p["fim"]), None)


def proxima_pausa(pausas, agora):
    return next((p for p in pausas if p["inicio"] > agora), None)


def calcular_status(agora, turno_ini, turno_fim, pausas):
    """Devolve (texto, cor) do status do analista no minuto `agora`."""
    ini, fim = time_to_minutes(turno_ini), time_to_minutes(turno_fim)
    if agora is None or ini is None or fim is None:
        return "⚪ Indisponível", "gray"
    if agora >= fim:
        return "⚪ Jornada encerrada", "gray"
    if agora < ini:
        return "⚪ Fora do expediente", "gray"
    if not pausas:
        return "⚪ Sem pausas dimensionadas", "gray"
    if pausa_atual(pausas, agora):
        return "🔵 Em intervalo", "blue"
    prox = proxima_pausa(pausas, agora)
    if prox and 0 < prox["inicio"] - agora <= ALERTA_PROXIMO_MIN:
        return "🟡 Próximo intervalo", "orange"
    return "🟢 Em atendimento", "green"


# ============================================================
# 3. DADOS
# ============================================================
def _criar_servico_sheets():
    info = get_secret("service_account")
    if info is not None:
        creds = service_account.Credentials.from_service_account_info(dict(info), scopes=SCOPES)
    else:  # desenvolvimento local / Render
        creds = service_account.Credentials.from_service_account_file(
            "service_account.json", scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _buscar_planilha(sheet_id, tab):
    """UMA única chamada à API, compartilhada por todos os usuários (cache global)."""
    service = _criar_servico_sheets()
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!A:Z"
    ).execute()
    return resp.get("values", [])


@st.cache_resource(show_spinner=False)
def _ultimo_sucesso():
    return {}


def carregar_planilha():
    """Devolve (linhas, hora_dos_dados_se_defasado). Se a API falhar, usa o último dado bom."""
    sheet_id = get_secret("sheet_id", SHEET_ID_PADRAO)
    guardado = _ultimo_sucesso()
    try:
        values = _buscar_planilha(sheet_id, SHEET_TAB)
        guardado["values"], guardado["quando"] = values, agora_br()
        return values, None
    except Exception:
        if "values" in guardado:
            return guardado["values"], guardado["quando"]
        raise


# ============================================================
# 4. INTERFACE
# ============================================================
CSS = """
<style>
.block-container{padding-top:2.2rem;padding-bottom:3rem}
[data-testid="stSidebar"] .stButton button{width:100%}

/* ---------- card principal ---------- */
.pd-hero{margin:0 auto;border-radius:1rem;text-align:center;max-width:100%;
         box-shadow:0 4px 10px rgba(0,0,0,.18)}
.pd-hero .k{font-weight:800;letter-spacing:.02em}
.pd-hero .t{font-weight:800;margin:.7rem 0;font-variant-numeric:tabular-nums}
.pd-hero .s{opacity:.92}
.pd-hero .i{font-weight:700;margin-top:.9rem}
.pd-prog{height:.55rem;border-radius:1rem;background:rgba(127,127,127,.35);
         margin:1rem auto 0;max-width:420px;overflow:hidden}
.pd-prog>div{height:100%;background:currentColor;border-radius:1rem}
@keyframes pd-pulse{0%,100%{box-shadow:0 4px 10px rgba(0,0,0,.18)}
                    50%{box-shadow:0 0 0 .55rem rgba(255,152,0,.40)}}
.pd-hero.soon{animation:pd-pulse 2s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.pd-hero.soon{animation:none}}

/* ---------- cards das pausas ---------- */
.pd-pauses{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:.6rem}
.pd-pause{padding:.9rem .5rem;border-radius:.6rem;text-align:center;
          box-shadow:0 2px 4px rgba(0,0,0,.12)}
.pd-pause .tag{font-size:.8rem;opacity:.85;min-height:1.2em}
.pd-pause .h{font-size:1.7rem;font-weight:800;margin:.3rem 0;font-variant-numeric:tabular-nums}
.pd-pause .m{font-size:.95rem;opacity:.92;overflow-wrap:anywhere}
.pd-pause.passada{opacity:.5;filter:grayscale(.5)}
.pd-pause.agora{outline:3px solid #ffd54f;outline-offset:2px}

/* ---------- status ---------- */
.pd-status{border-radius:.6rem;text-align:center;font-weight:800;
           box-shadow:0 2px 4px rgba(0,0,0,.12)}
.pd-agora{text-align:center;margin-top:.8rem;opacity:.75}

/* ---------- jornada ---------- */
.pd-trackwrap{position:relative;margin:2rem .4rem .4rem}
.pd-track{position:relative;border-radius:1rem;overflow:hidden}
.pd-fill{position:absolute;left:0;top:0;bottom:0;background:rgba(255,255,255,.35)}
.pd-seg{position:absolute;top:0;bottom:0}
.pd-marker{position:absolute;top:-.25rem;bottom:-.25rem;width:3px;background:#fff;
           box-shadow:0 0 0 1px rgba(0,0,0,.55);transform:translateX(-50%)}
.pd-marker b{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);
             font-size:.7rem;white-space:nowrap;padding:.05rem .4rem;border-radius:.3rem;
             background:#2196f3;color:#fff;margin-bottom:.15rem}
.pd-ends{display:flex;justify-content:space-between;margin:.5rem .4rem 0;
         font-variant-numeric:tabular-nums;opacity:.8;font-size:.85rem}
.pd-legend{display:flex;gap:1rem;flex-wrap:wrap;font-size:.78rem;opacity:.75;margin:.4rem .4rem 0}
.pd-legend i{display:inline-block;width:.7rem;height:.7rem;border-radius:.2rem;margin-right:.3rem}
.pd-stats{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.8rem}
.pd-stat{flex:1 1 90px;text-align:center;padding:.5rem;border-radius:.5rem;
         border:1px solid rgba(128,128,128,.3)}
.pd-stat small{display:block;opacity:.7;font-size:.75rem}
.pd-stat b{font-size:1.15rem;font-variant-numeric:tabular-nums}

/* ---------- equipe ---------- */
.pd-fila{padding:.8rem 1rem;border-radius:.5rem;margin:1rem 0 .6rem}
.pd-fila h3{margin:0;font-size:1.1rem}
.pd-team{display:grid;grid-template-columns:repeat(var(--cols,3),minmax(0,1fr));gap:.5rem}
@media (max-width:640px){.pd-team{grid-template-columns:repeat(2,minmax(0,1fr))}}
.pd-agent{padding:.7rem .5rem;border-radius:.5rem;text-align:center;
          box-shadow:0 2px 4px rgba(0,0,0,.2);overflow-wrap:anywhere}
.pd-agent b{display:block}
.pd-agent span{font-size:.85em;opacity:.92}
.pd-agent.me{outline:3px solid #ffd54f;outline-offset:2px}

/* ---------- troca de intervalo ---------- */
.pd-swap{display:grid;grid-template-columns:repeat(var(--cols,4),minmax(0,1fr));
         gap:.6rem;align-items:start}
@media (max-width:900px){.pd-swap{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:520px){.pd-swap{grid-template-columns:minmax(0,1fr)}}
details.pd-slot{border:1px solid rgba(128,128,128,.4);border-radius:.5rem;padding:.55rem .8rem}
details.pd-slot summary{cursor:pointer;font-weight:600}
details.pd-slot[open]{background:rgba(128,128,128,.08)}
details.pd-slot.mine{border:2px solid #ff9800}
details.pd-slot.past{opacity:.5}
.pd-contatos{margin-top:.5rem}
.pd-badge{display:inline-block;margin:.2rem .4rem .2rem 0;padding:.3rem .7rem;border-radius:1rem;
          border:1px solid rgba(128,128,128,.4);background:rgba(128,128,128,.12);font-size:.9rem}
.pd-badge i{opacity:.65;font-style:normal}
</style>
"""


def html_block(content):
    st.html(content)


# ---------- manutenção ----------
def mostrar_manutencao():
    previsao = (
        f'<div style="font-size:1.1rem;margin-top:1rem;font-weight:bold">🕐 {esc(MANUTENCAO_PREVISAO)}</div>'
        if MANUTENCAO_PREVISAO else ""
    )
    html_block(f"""
    <div style="padding:3rem 2rem;margin:3rem auto;max-width:700px;border-radius:1rem;
                background:linear-gradient(135deg,#ff9800 0%,#f57c00 100%);color:#fff;
                text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.2)">
      <div style="font-size:4rem">🛠️</div>
      <h1 style="margin:.5rem 0;color:#fff">Em manutenção</h1>
      <div style="font-size:1.3rem;opacity:.95">{esc(MANUTENCAO_MSG)}</div>
      {previsao}
    </div>""")


# ---------- componentes ----------
def render_cards_pausas(meu, agora, cfg):
    prox = proxima_pausa(meu["pausas"], agora)
    cards = []
    for p in meu["pausas"]:
        cor = cfg.cor_pausa_intervalo if p["tipo"] == "Intervalo" else cfg.cor_pausa_extra
        if p["fim"] <= agora:
            estado, tag = "passada", "✓ concluída"
        elif p["inicio"] <= agora:
            estado, tag = "agora", "● AGORA"
        elif p is prox:
            estado, tag = "", "PRÓXIMA"
        else:
            estado, tag = "", "&nbsp;"
        cards.append(f"""
        <div class="pd-pause {estado}" style="background:linear-gradient(135deg,{cor} 0%,{cor}dd 100%);color:{cor_texto(cor)}">
          <div class="tag">{esc(p['tipo'])} · {tag}</div>
          <div class="h">{p['horario']}</div>
          <div class="m">{esc(p['motivo'])}</div>
        </div>""")
    html_block(f'<div class="pd-pauses">{"".join(cards)}</div>')


def render_hero(meu, agora, cfg):
    pausas = meu["pausas"]
    atual, prox = pausa_atual(pausas, agora), proxima_pausa(pausas, agora)
    classes, progresso = "pd-hero", ""

    if atual:
        p = atual
        restante = p["fim"] - agora
        pct = max(0, min(100, (agora - p["inicio"]) / p["duracao"] * 100))
        kicker = "🔵 VOCÊ ESTÁ EM PAUSA"
        info = f"Termina às {minutes_to_time(p['fim'])} · faltam {format_duration(restante)}"
        progresso = f'<div class="pd-prog"><div style="width:{pct:.0f}%"></div></div>'
    elif prox:
        p = prox
        ate = p["inicio"] - agora
        if ate <= IMINENTE_MIN:
            kicker, classes = "🟢 PRÓXIMO INTERVALO", classes + " soon"
            info = f"⏳ Começa em {ate} {plural(ate, 'minuto')}"
        else:
            kicker = "🕐 PRÓXIMO INTERVALO"
            info = f"⏳ Começa em {format_duration(ate)}"
    else:
        feitas = len(pausas)
        st.success(f"✅ Você já fez {'todas as' if feitas > 1 else 'a'} {plural(feitas, 'pausa')} de hoje.")
        return

    cor = cfg.cor_intervalo
    fg = cor_texto(cor)
    esc_h, esc_f = cfg.tam_int_h / 100, cfg.tam_int_f / 100
    html_block(f"""
    <div class="{classes}" style="padding:{1.5 * esc_h:.2f}rem;background:linear-gradient(135deg,{cor} 0%,{cor}dd 100%);
                color:{fg};width:{cfg.tam_int_w}%">
      <div class="k" style="font-size:{1.5 * esc_f:.2f}rem">{kicker}</div>
      <div class="t" style="font-size:{2.5 * esc_f:.2f}rem">{p['horario']} → {minutes_to_time(p['fim'])}</div>
      <div class="s" style="font-size:{1.1 * esc_f:.2f}rem">{esc(p['motivo'])} · Duração {format_duration(p['duracao'])}</div>
      <div class="i" style="font-size:{1.3 * esc_f:.2f}rem">{info}</div>
      {progresso}
    </div>""")


def render_status(meu, agora, cfg, agora_txt):
    texto, chave = calcular_status(agora, meu["turno_ini"], meu["turno_fim"], meu["pausas"])
    bg = {"green": cfg.cor_status, **STATUS_COR_PADRAO}.get(chave, "#eeeeee")
    html_block(f"""
    <div class="pd-status" style="padding:{1.5 * cfg.tam_sta_h / 100:.2f}rem;background:{bg};color:{cor_texto(bg)};
         font-size:{1.5 * cfg.tam_sta_f / 100:.2f}rem">{esc(texto)}</div>
    <div class="pd-agora" style="font-size:{1.1 * cfg.tam_sta_f / 100:.2f}rem">🕐 Agora: {agora_txt}</div>""")


def render_jornada(meu, agora, cfg):
    ini, fim = time_to_minutes(meu["turno_ini"]), time_to_minutes(meu["turno_fim"])
    total = (fim - ini) if (ini is not None and fim is not None) else 0
    if total <= 0:
        st.info("Não foi possível calcular a jornada (horários inválidos na planilha).")
        return
    pct = max(0, min(100, (agora - ini) / total * 100))
    decorrido = max(0, min(agora, fim) - ini)
    restante = max(0, fim - max(agora, ini))

    segmentos = []
    for p in meu["pausas"]:
        a, b = max(p["inicio"], ini), min(p["fim"], fim)
        if b > a:
            cor = cfg.cor_pausa_intervalo if p["tipo"] == "Intervalo" else cfg.cor_pausa_extra
            segmentos.append(
                f'<div class="pd-seg" title="{p["horario"]} · {esc(p["motivo"])}" '
                f'style="left:{(a - ini) / total * 100:.2f}%;width:{(b - a) / total * 100:.2f}%;background:{cor}"></div>'
            )
    altura = 1.4 * cfg.tam_jor_h / 100
    html_block(f"""
    <div class="pd-trackwrap" style="font-size:{cfg.tam_jor_f / 100:.2f}rem">
      <div class="pd-track" style="height:{altura:.2f}rem;background:{cfg.cor_jornada}">
        <div class="pd-fill" style="width:{pct:.2f}%"></div>
        {''.join(segmentos)}
      </div>
      <div class="pd-marker" style="left:{pct:.2f}%"><b>AGORA</b></div>
    </div>
    <div class="pd-ends"><span>{meu['turno_ini']}</span><span>{meu['turno_fim']}</span></div>
    <div class="pd-legend">
      <span><i style="background:{cfg.cor_pausa_intervalo}"></i>Intervalo</span>
      <span><i style="background:{cfg.cor_pausa_extra}"></i>Pausas extras</span>
    </div>
    <div class="pd-stats">
      <div class="pd-stat"><small>🕘 Início</small><b>{meu['turno_ini']}</b></div>
      <div class="pd-stat"><small>⏱️ Decorrido</small><b>{format_duration(decorrido)}</b></div>
      <div class="pd-stat"><small>⏳ Restante</small><b>{format_duration(restante)}</b></div>
    </div>""")


FILAS = [
    ("MA", "🌊 MAR ABERTO (MA)", "cor_fila_ma"),
    ("IMP", "🖨️ IMPRESSÃO (IMP)", "cor_fila_imp"),
    ("OUTROS", "📋 OUTROS", "cor_fila_outros"),
]
FILTROS_EQUIPE = {
    "Todos": None, "🔵 Em intervalo": "blue", "🟡 Próximo intervalo": "orange", "🟢 Em atendimento": "green",
}


def render_equipe(analistas, agora, cfg, meu_nome):
    if not analistas:
        st.info("Nenhum dado de equipe disponível.")
        return

    linhas = []
    for a in analistas:
        texto, chave = calcular_status(agora, a["turno_ini"], a["turno_fim"], a["pausas"])
        linhas.append({**a, "status": texto, "cor": chave})

    cont = {k: sum(1 for l in linhas if l["cor"] == k) for k in ("green", "blue", "orange")}
    html_block(f"""
    <div class="pd-stats">
      <div class="pd-stat"><small>👥 Equipe</small><b>{len(linhas)}</b></div>
      <div class="pd-stat"><small>🟢 Atendendo</small><b>{cont['green']}</b></div>
      <div class="pd-stat"><small>🔵 Em intervalo</small><b>{cont['blue']}</b></div>
      <div class="pd-stat"><small>🟡 Próximo</small><b>{cont['orange']}</b></div>
    </div>""")

    filtro = st.radio("Mostrar", list(FILTROS_EQUIPE), horizontal=True, key="filtro_equipe")
    alvo = FILTROS_EQUIPE[filtro]
    mapa = {"green": cfg.cor_equipe, **STATUS_COR_PADRAO}

    mostrou = False
    for chave_fila, titulo, attr in FILAS:
        grupo = [l for l in linhas if l["fila"] == chave_fila]
        visiveis = sorted((l for l in grupo if alvo is None or l["cor"] == alvo), key=lambda l: l["nome"])
        if not visiveis:
            continue
        mostrou = True
        cor_fila = getattr(cfg, attr)
        em_int = sum(1 for l in grupo if l["cor"] == "blue")
        resumo = f"{len(grupo)} {plural(len(grupo), 'pessoa')}" + (f" · {em_int} em intervalo" if em_int else "")
        cards = []
        for l in visiveis:
            bg = mapa.get(l["cor"], "#eeeeee")
            eu = " me" if l["nome"] == meu_nome else ""
            cards.append(
                f'<div class="pd-agent{eu}" style="background:{bg};color:{cor_texto(bg)};font-size:{cfg.tam_equ_f / 100:.2f}rem">'
                f'<b>{esc(l["nome"])}{" (você)" if eu else ""}</b><span>{esc(l["status"])}</span></div>'
            )
        html_block(f"""
        <div class="pd-fila" style="background:linear-gradient(90deg,{cor_fila}22 0%,transparent 100%);border-left:4px solid {cor_fila}">
          <h3 style="color:{cor_fila}">{titulo} <small style="opacity:.7;font-weight:400">— {resumo}</small></h3>
        </div>
        <div class="pd-team" style="--cols:{cfg.cols_equipe}">{''.join(cards)}</div>""")
    if not mostrou:
        st.info("Ninguém com esse status no momento.")


def render_troca(analistas, meu, agora, cfg):
    st.subheader("🔄 Troca de Intervalo")
    st.caption(
        "Troca apenas do intervalo de almoço/descanso (1h) previsto na CLT — coluna F da planilha. "
        "Pausas excepcionais (colunas H e K) não entram na troca."
    )
    meu_nome = meu["nome"] if meu else None
    meu_almoco = meu["intervalo_almoco"] if meu else None
    if meu_almoco:
        st.markdown(f"**Seu intervalo:** {meu_almoco}")
    elif meu:
        st.info("Você não tem intervalo de almoço cadastrado na planilha.")
    else:
        st.info("Escolha seu nome no topo da página para destacar o seu horário.")

    candidatos = [a for a in analistas if a["intervalo_almoco"] and a["nome"] != meu_nome]
    if not candidatos:
        st.info("Nenhum horário de almoço/descanso cadastrado para a equipe.")
        return

    col_filtro, _ = st.columns([1, 2])
    with col_filtro:
        filtro = st.selectbox("Filtrar por fila:", ["Todas", "MA", "IMP", "OUTROS"], key="filtro_fila_troca")
    if filtro != "Todas":
        candidatos = [a for a in candidatos if a["fila"] == filtro]
    if not candidatos:
        st.info("Nenhum horário disponível para essa fila.")
        return

    por_horario = {}
    for a in candidatos:
        por_horario.setdefault(a["intervalo_almoco"], []).append(a)

    duracao = DURACAO_PAUSA_MIN["Intervalo"]
    slots = []
    for horario in sorted(por_horario, key=time_to_minutes):
        pessoas = sorted(por_horario[horario], key=lambda a: a["nome"])
        classes = []
        extra = ""
        if horario == meu_almoco:
            classes.append("mine")
            extra = " (seu horário)"
            marcador = "🟠"
        else:
            marcador = "🟢"
        if time_to_minutes(horario) + duracao <= agora:
            classes.append("past")
            extra += " · já passou"
        badges = "".join(
            f'<span class="pd-badge">{esc(p["nome"])} <i>({esc(p["fila"])})</i></span>' for p in pessoas
        )
        slots.append(
            f'<details class="pd-slot {" ".join(classes)}">'
            f'<summary>{marcador} {horario} — {len(pessoas)} {plural(len(pessoas), "pessoa")}{extra}</summary>'
            f'<div class="pd-contatos">Contatar: {badges}</div></details>'
        )
    st.caption("Toque em um horário para ver quem contatar.")
    html_block(f'<div class="pd-swap" style="--cols:{cfg.cols_troca}">{"".join(slots)}</div>')
    st.caption("🟠 = mesmo horário do seu almoço/descanso · 🟢 = horário diferente do seu · horários já passados ficam esmaecidos")


# ---------- painel (atualiza sozinho) ----------
def render_painel(nome_sel, cfg):
    try:
        values, defasado_desde = carregar_planilha()
    except Exception as e:
        st.error("Não foi possível carregar a planilha agora. Tentaremos de novo automaticamente.")
        with st.expander("Detalhes técnicos"):
            st.code(str(e))
        return

    analistas = parse_analistas(values)
    dt = agora_br()
    agora = minutos_do_dia(dt)
    agora_txt = f"{dt.hour:02d}:{dt.minute:02d}"

    if defasado_desde:
        st.warning(
            f"⚠️ Sem conexão com a planilha. Mostrando dados de {defasado_desde.strftime('%H:%M')}. "
            "Confira a planilha de pausas da gestão se precisar de certeza."
        )

    meu = next((a for a in analistas if a["nome"] == nome_sel), None)
    if nome_sel and meu is None:
        st.warning(f"“{nome_sel}” não foi encontrado(a) na planilha. Escolha seu nome novamente.")

    tab1, tab2 = st.tabs(["📋 Painel Principal", "🔄 Troca de Intervalo"])

    with tab1:
        if meu is None and not nome_sel:
            st.info("👆 Escolha seu nome acima para ver suas pausas. O status da equipe está logo abaixo.")
        elif meu is not None and not meu["pausas"]:
            st.warning(f"⚠️ {meu['nome']} sem pausas dimensionadas.")
        elif meu is not None:
            st.subheader("📋 Suas pausas de hoje")
            render_cards_pausas(meu, agora, cfg)
            st.write("")
            render_hero(meu, agora, cfg)
            st.write("")
            col_status, col_jornada = st.columns(2)
            with col_status:
                st.subheader("📊 Meu status")
                render_status(meu, agora, cfg, agora_txt)
            with col_jornada:
                st.subheader("📅 Minha jornada hoje")
                render_jornada(meu, agora, cfg)

        with st.expander("👥 STATUS DA EQUIPE", expanded=meu is None):
            render_equipe(analistas, agora, cfg, nome_sel)

    with tab2:
        render_troca(analistas, meu, agora, cfg)

    st.caption(f"🕐 Atualizado às {dt.strftime('%H:%M:%S')} · fuso de Brasília")


# ---------- página ----------
st.set_page_config(page_title="Dashboard de Pausas - Saipos", page_icon="⏱️", layout="wide")
html_block(CSS)

MANUTENCAO = to_bool(get_secret("manutencao", MANUTENCAO))
if MANUTENCAO:
    mostrar_manutencao()
    st.stop()

hoje = agora_br()
st.title("⏱️ Dashboard de Pausas")
st.caption(f"{DIAS_SEMANA[hoje.weekday()].capitalize()}, {hoje.strftime('%d/%m/%Y')} · Saipos Suporte")

# ---- seletor de nome (na página principal: no celular a sidebar vem fechada) ----
try:
    _valores, _ = carregar_planilha()
    nomes = sorted(a["nome"] for a in parse_analistas(_valores))
except Exception as e:
    st.error("Não foi possível carregar a planilha agora. Tente novamente em instantes.")
    with st.expander("Detalhes técnicos"):
        st.code(str(e))
    if st.button("🔄 Tentar novamente"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

if not nomes:
    st.error("Nenhum analista encontrado na planilha.")
    st.stop()


def _salvar_nome():
    """Guarda o nome na URL (?analista=...): o link favoritado já abre no seu nome."""
    escolhido = st.session_state.get("analista_sel")
    if escolhido:
        st.query_params["analista"] = escolhido
    elif "analista" in st.query_params:
        del st.query_params["analista"]


_na_url = st.query_params.get("analista")
nome_sel = st.selectbox(
    "👤 Quem é você?",
    nomes,
    index=nomes.index(_na_url) if _na_url in nomes else None,
    placeholder="Selecione seu nome",
    key="analista_sel",
    on_change=_salvar_nome,
)

# ---- sidebar: personalização e atualização ----
with st.sidebar:
    st.subheader("🔄 Atualização")
    auto_refresh = st.checkbox(f"Atualizar sozinho ({INTERVALO_ATUALIZACAO_S}s)", value=True)
    if st.button("🔄 Atualizar agora"):
        st.cache_data.clear()  # força nova leitura da planilha

    st.divider()
    st.subheader("🎨 Personalização")

    with st.expander("🎴 Cores das Pausas"):
        cor_pausa_intervalo = st.color_picker("Pausa Intervalo", "#4facfe", key="cor_Intervalo")
        cor_pausa_extra = st.color_picker("Pausas Extras", "#9c27b0", key="cor_extra")

    with st.expander("🕐 Próximo Intervalo"):
        cor_intervalo = st.color_picker("Cor", "#4facfe", key="cor_int")
        tam_int_h = st.slider("Altura (%)", 50, 200, 100, 10, key="int_h")
        tam_int_w = st.slider("Largura (%)", 50, 100, 100, 5, key="int_w")
        tam_int_f = st.slider("Fonte (%)", 70, 200, 100, 10, key="int_f")

    with st.expander("📊 Meu Status"):
        cor_status = st.color_picker("Cor", "#4caf50", key="cor_sta")
        tam_sta_h = st.slider("Altura (%)", 50, 200, 100, 10, key="sta_h")
        tam_sta_f = st.slider("Fonte (%)", 70, 200, 100, 10, key="sta_f")

    with st.expander("📅 Jornada"):
        cor_jornada = st.color_picker("Fundo", "#808080", key="cor_jor")
        tam_jor_h = st.slider("Altura (%)", 50, 200, 100, 10, key="jor_h")
        tam_jor_f = st.slider("Fonte (%)", 70, 200, 100, 10, key="jor_f")

    with st.expander("👥 Equipe"):
        cor_equipe = st.color_picker("Cor", "#4caf50", key="cor_equ")
        tam_equ_f = st.slider("Fonte (%)", 70, 200, 100, 10, key="equ_f")
        cols_equipe = st.slider("Cards por linha (computador)", 1, 6, 3, 1, key="equ_c")

    with st.expander("🔄 Troca de Intervalo"):
        cols_troca = st.slider("Blocos por linha (computador)", 1, 6, 4, 1, key="troca_c")

    with st.expander("🎯 Cores das Filas"):
        cor_fila_ma = st.color_picker("Cor Fila MA", "#00BCD4", key="cor_ma")
        cor_fila_imp = st.color_picker("Cor Fila IMP", "#9C27B0", key="cor_imp")
        cor_fila_outros = st.color_picker("Cor Outros", "#607D8B", key="cor_out")

cfg = SimpleNamespace(
    cor_pausa_intervalo=cor_pausa_intervalo, cor_pausa_extra=cor_pausa_extra,
    cor_intervalo=cor_intervalo, tam_int_h=tam_int_h, tam_int_w=tam_int_w, tam_int_f=tam_int_f,
    cor_status=cor_status, tam_sta_h=tam_sta_h, tam_sta_f=tam_sta_f,
    cor_jornada=cor_jornada, tam_jor_h=tam_jor_h, tam_jor_f=tam_jor_f,
    cor_equipe=cor_equipe, tam_equ_f=tam_equ_f, cols_equipe=cols_equipe,
    cols_troca=cols_troca,
    cor_fila_ma=cor_fila_ma, cor_fila_imp=cor_fila_imp, cor_fila_outros=cor_fila_outros,
)

# O painel roda como "fragment": atualiza sozinho sem recarregar a página inteira
# (o seletor de nome e a sidebar não piscam nem perdem o estado).
painel = st.fragment(
    run_every=f"{INTERVALO_ATUALIZACAO_S}s" if auto_refresh else None
)(render_painel)
painel(nome_sel, cfg)
