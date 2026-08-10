import os, re, time
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ============================================================
# CONFIGURAÇÃO - EDITE AQUI
# ============================================================
SHEET_ID = "1bwrJmasPZUz5F8qsITo2RhFYTHb8e2OnSHlCWLSDOIs"  # ← Cole seu SHEET_ID
SHEET_TAB = "pagina"  # ← Nome da aba

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# ============================================================
# FUNÇÕES
# ============================================================

def get_sheets_service():
    try:
        # Tenta ler do Streamlit Secrets (Streamlit Cloud)
        if hasattr(st, 'secrets') and "service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["service_account"],
                scopes=SCOPES
            )
        else:
            # Fallback para arquivo local (Render ou desenvolvimento)
            creds = service_account.Credentials.from_service_account_file(
                "service_account.json",
                scopes=SCOPES
            )
    except Exception as e:
        # Se falhar, tenta arquivo local
        creds = service_account.Credentials.from_service_account_file(
            "service_account.json",
            scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds)

    return build("sheets", "v4", credentials=creds)

def detect_time(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = re.sub(r"\s*h\s*", ":", s, flags=re.IGNORECASE)
    s = s.replace(" ", "")
    try:
        dt = parser.parse(s, fuzzy=True)
        return f"{dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        m = re.match(r"^(\d{1,2}):?(\d{2})$", s)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if 0 <= h <= 23 and 0 <= mi <= 59:
                return f"{h:02d}:{mi:02d}"
    return None

def time_to_minutes(time_str):
    if not time_str or pd.isna(time_str):
        return None
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except:
        return None

def minutes_to_time(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def format_duration(minutes):
    if minutes is None or minutes < 0:
        return "-"
    if minutes < 60:
        return f"{minutes}min"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h{m:02d}"

def get_current_time_str():
    import pytz
    brasilia = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brasilia)  # ← Força Brasília!
    return f"{now.hour:02d}:{now.minute:02d}"


def find_next_interval(intervals_df, current_time_str):
    current_mins = time_to_minutes(current_time_str)
    if current_mins is None or intervals_df.empty:
        return None
    valid = intervals_df.dropna(subset=["horario"]).copy()
    if valid.empty:
        return None
    valid["mins"] = valid["horario"].apply(time_to_minutes)
    valid = valid.dropna(subset=["mins"])
    future = valid[valid["mins"] > current_mins].sort_values("mins")
    if not future.empty:
        return future.iloc[0]
    return None

def calculate_status(current_time_str, intervals_df, shift_start="09:00", shift_end="18:00"):
    current_mins = time_to_minutes(current_time_str)
    shift_start_mins = time_to_minutes(shift_start)
    shift_end_mins = time_to_minutes(shift_end)
    if current_mins is None:
        return "⚪ Indisponível", "gray"
    if current_mins >= shift_end_mins:
        return "⚪ Jornada encerrada", "gray"
    if current_mins < shift_start_mins:
        return "⚪ Fora do expediente", "gray"
    valid = intervals_df.dropna(subset=["horario"]).copy()
    if not valid.empty:
        valid["mins"] = valid["horario"].apply(time_to_minutes)
        valid = valid.dropna(subset=["mins"])
        for idx, row in valid.iterrows():
            interval_start = row["mins"]
            interval_end = interval_start + 60
            if interval_start <= current_mins < interval_end:
                return "🔵 Em intervalo", "blue"
        next_interval = find_next_interval(valid, current_time_str)
        if next_interval is not None:
            next_mins = next_interval["mins"]
            time_until = next_mins - current_mins
            if 0 < time_until <= 30:
                return "🟡 Próximo intervalo", "orange"
    return "🟢 Em atendimento", "green"

@st.cache_data(ttl=60)
def fetch_all_names():
    service = get_sheets_service()
    rng = f"{SHEET_TAB}!A:A"
    values = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=rng
    ).execute().get("values", [])
    if not values or len(values) < 2:
        return []
    names = [row[0].strip() for row in values[1:] if row and row[0].strip()]
    return sorted(set(names))

@st.cache_data(ttl=60)
def fetch_row(row_value):
    service = get_sheets_service()
    rng = f"{SHEET_TAB}!A:Z"
    values = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=rng
    ).execute().get("values", [])
    if not values:
        raise ValueError("Aba vazia ou inexistente.")
    header = values[0]
    target = str(row_value).strip().lower()
    row = None
    for r in values[1:]:
        val = (r[0].strip().lower() if len(r) > 0 and r[0] else "")
        if val == target:
            row = r
            break
    if row is None:
        raise ValueError(f"Linha não encontrada para '{row_value}'.")
    
    # Horários de jornada
    shift_start = None
    shift_end = None
    if len(row) > 3:
        shift_start = detect_time(row[3])
    if not shift_start and len(row) > 2:
        shift_start = detect_time(row[2])
    for idx in [1, 2, 3, 4]:
        if len(row) > idx and idx != 3:
            potential_end = detect_time(row[idx])
            if potential_end:
                if shift_start:
                    start_mins = time_to_minutes(shift_start)
                    end_mins = time_to_minutes(potential_end)
                    if end_mins and end_mins > start_mins:
                        shift_end = potential_end
                        break
                else:
                    shift_end = potential_end
    if not shift_start:
        shift_start = "09:00"
    if not shift_end:
        shift_end = "18:00"
    
    # Pausas
    pausas_map = [
        {"horario_idx": 5, "motivo_idx": 4, "tipo": "Intervalo", "coluna": "F"},
        {"horario_idx": 7, "motivo_idx": 9, "tipo": "Extra", "coluna": "H"},
        {"horario_idx": 10, "motivo_idx": 12, "tipo": "Extra", "coluna": "K"}
    ]
    data = []
    for pausa_info in pausas_map:
        horario_idx = pausa_info["horario_idx"]
        motivo_idx = pausa_info["motivo_idx"]
        tipo = pausa_info["tipo"]
        coluna = pausa_info["coluna"]
        cell_horario = row[horario_idx] if len(row) > horario_idx else None
        cell_motivo = row[motivo_idx] if len(row) > motivo_idx else None
        t = detect_time(cell_horario)
        if cell_horario is not None and t:
            motivo_texto = str(cell_motivo).strip() if cell_motivo else (
                "Intervalo Intervalo" if tipo == "Intervalo" else "Pausa"
            )
            data.append({
                "coluna": coluna,
                "valor_bruto": cell_horario,
                "horario": t,
                "motivo": motivo_texto,
                "tipo": tipo
            })
    df = pd.DataFrame(data)
    if not df.empty and "horario" in df.columns:
        valid_times = df["horario"].notna()
        if valid_times.any():
            temp_split = df.loc[valid_times, "horario"].str.split(":", expand=True)
            df.loc[valid_times, "hora"] = pd.to_numeric(temp_split[0], errors="coerce")
            df.loc[valid_times, "min"] = temp_split[1]
    return header, df, shift_start, shift_end

@st.cache_data(ttl=60)
def fetch_all_analysts():
    service = get_sheets_service()
    rng = f"{SHEET_TAB}!A:K"
    values = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=rng
    ).execute().get("values", [])
    if not values:
        return pd.DataFrame()
    analysts_data = []
    for r in values[1:]:
        if len(r) > 0 and r[0].strip():
            name = r[0].strip()
            col_map = {"F":5, "H":7, "K":10}
            intervals = []
            for col_letter in ["F","H","K"]:
                idx = col_map[col_letter]
                cell = r[idx] if len(r) > idx else None
                t = detect_time(cell)
                if t:
                    intervals.append(t)
            analysts_data.append({"nome": name, "intervalos": intervals})
    return pd.DataFrame(analysts_data)

# ============================================================
# INTERFACE
# ============================================================

st.set_page_config(
    page_title="Dashboard de Pausas - Saipos",
    page_icon="⏱️",
    layout="wide"
)

st.title("⏱️ Dashboard de Pausas - Saipos")
st.caption("Gestão de intervalos e pausas da operação de suporte")

with st.sidebar:
    st.subheader("👤 Seleção")
    
    try:
        nomes = fetch_all_names()
        if not nomes:
            st.error("Nenhum analista encontrado")
            st.stop()
        row_value = st.selectbox("Escolha seu nome:", nomes, index=0)
    except Exception as e:
        st.error(f"Erro: {str(e)}")
        st.stop()
    
    st.divider()
    st.subheader("🎨 Personalização")
    
    with st.expander("🎴 Cores das Pausas"):
        cor_pausa_Intervalo = st.color_picker("Pausa Intervalo", "#4facfe", key="cor_Intervalo")
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
        cols_equipe = st.slider("Cards por linha", 1, 6, 3, 1, key="equ_c")
    
    st.divider()
    st.subheader("🔄 Atualização")
    auto_refresh = st.checkbox("Auto-refresh (1 min)", value=True)
    btn = st.button("🔄 Recarregar", use_container_width=True)

last_run = st.session_state.get("last_run", 0)
run_now = btn or (auto_refresh and time.time() - last_run > 60)
if run_now:
    st.session_state["last_run"] = time.time()
    if auto_refresh:
        time.sleep(1)
        st.rerun()

try:
    header, df, shift_start, shift_end = fetch_row(row_value)
    all_analysts = fetch_all_analysts()
    
    if df.empty:
        st.warning(f"⚠️ {row_value} sem pausas dimensionadas.")
        st.stop()
    
    current_time = get_current_time_str()
    
    st.markdown("---")
    st.subheader("📋 Suas Pausas de Hoje")
    
    cols_pausas = st.columns(len(df))
    for idx, (i, row) in enumerate(df.iterrows()):
        with cols_pausas[idx]:
            motivo = row.get("motivo", "Pausa")
            horario = row.get("horario", "-")
            tipo = row.get("tipo", "")
            cor_card = cor_pausa_Intervalo if tipo == "Intervalo" else cor_pausa_extra
            st.markdown(f"""
            <div style="padding: 1rem; border-radius: 0.5rem; background: linear-gradient(135deg, {cor_card} 0%, {cor_card}dd 100%); color: white; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 0.9rem; opacity: 0.8; margin-bottom: 0.5rem;">{tipo if tipo else "Pausa"}</div>
                <div style="font-size: 1.8rem; font-weight: bold; margin: 0.5rem 0;">{horario}</div>
                <div style="font-size: 1rem; opacity: 0.9;">{motivo}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    next_interval = find_next_interval(df, current_time)
    
    if next_interval is not None:
        next_time = next_interval["horario"]
        next_motivo = next_interval.get("motivo", "Intervalo")
        next_mins = time_to_minutes(next_time)
        current_mins = time_to_minutes(current_time)
        time_until = next_mins - current_mins
        duration_mins = 60
        end_time = minutes_to_time(next_mins + duration_mins)
        
        if time_until <= 0 and time_until > -duration_mins:
            status_text = "🔵 VOCÊ ESTÁ EM PAUSA"
            subtitle_text = next_motivo.upper()
            time_info = f"Termina às {end_time}"
        elif time_until <= 5:
            status_text = "🟢 PRÓXIMO INTERVALO"
            subtitle_text = next_motivo.upper()
            time_info = f"⏳ Começa em {time_until} minuto{'s' if time_until != 1 else ''}"
        else:
            status_text = "🕐 PRÓXIMO INTERVALO"
            subtitle_text = next_motivo.upper()
            time_info = f"⏳ Começa em {format_duration(time_until)}"
        
        card_gradient = f"linear-gradient(135deg, {cor_intervalo} 0%, {cor_intervalo}dd 100%)"
        padding = 1.5 * (tam_int_h / 100)
        f_titulo = 2 * (tam_int_f / 100)
        f_subtitulo = 1.5 * (tam_int_f / 100)
        f_horario = 2.5 * (tam_int_f / 100)
        f_duracao = 1.2 * (tam_int_f / 100)
        f_info = 1.5 * (tam_int_f / 100)
        
        st.markdown(f"""
        <div style="padding: {padding}rem; border-radius: 1rem; background: {card_gradient}; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: {tam_int_w}%; margin: 0 auto;">
            <h2 style="margin: 0; font-size: {f_titulo}rem;">{status_text}</h2>
            <div style="font-size: {f_horario}rem; font-weight: bold; margin: 1rem 0;">{next_time} → {end_time}</div>
            <div style="font-size: {f_duracao}rem; opacity: 0.9;">Duração: {format_duration(duration_mins)}</div>
            <div style="font-size: {f_info}rem; margin-top: 1rem; font-weight: bold;">{time_info}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("ℹ️ Nenhum intervalo futuro encontrado para hoje.")
    
    st.markdown("---")
    
    col_status, col_jornada = st.columns(2)
    
    with col_status:
        st.subheader("📊 MEU STATUS")
        status_text, status_color = calculate_status(current_time, df, shift_start, shift_end)
        color_map = {"green": cor_status, "orange": "#ff9800", "blue": "#2196f3", "gray": "#9e9e9e"}
        padding_sta = 1.5 * (tam_sta_h / 100)
        st.markdown(f"""
        <div style="padding: {padding_sta}rem; border-radius: 0.5rem; background-color: {color_map.get(status_color, '#eee')}; color: white; text-align: center; font-size: {1.5 * (tam_sta_f/100)}rem; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            {status_text}
        </div>
        <div style="text-align: center; margin-top: 1rem; font-size: {1.2 * (tam_sta_f/100)}rem; color: #666;">🕐 Agora: {current_time}</div>
        """, unsafe_allow_html=True)
    
    with col_jornada:
        st.subheader("📅 MINHA JORNADA HOJE")
        shift_start_mins = time_to_minutes(shift_start)
        shift_end_mins = time_to_minutes(shift_end)
        current_mins = time_to_minutes(current_time)
        total_mins = shift_end_mins - shift_start_mins
        elapsed_mins = max(0, current_mins - shift_start_mins)
        progress = min(100, (elapsed_mins / total_mins) * 100) if total_mins > 0 else 0
        bar_length = 40
        filled = int((progress / 100) * bar_length)
        timeline_str = f"{shift_start} "
        for i in range(bar_length):
            if i == filled:
                timeline_str += "🐿️"
            else:
                timeline_str += "━"
        timeline_str += f" {shift_end}"
        padding_jor = 1 * (tam_jor_h / 100)
        st.markdown(f"""
        <div style="font-family: monospace; font-size: {1 * (tam_jor_f/100)}rem; text-align: center; margin: 1rem 0; background: {cor_jornada}; padding: {padding_jor}rem; border-radius: 0.5rem;">
            {timeline_str}<br>
            <span style="margin-left: {progress}%; color: #2196f3; font-weight: bold;">AGORA</span>
        </div>
        """, unsafe_allow_html=True)
        elapsed = current_mins - shift_start_mins if current_mins >= shift_start_mins else 0
        remaining = shift_end_mins - current_mins if current_mins < shift_end_mins else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("🕘 Início", shift_start)
        c2.metric("⏱️ Decorrido", format_duration(elapsed))
        c3.metric("⏳ Restante", format_duration(remaining))
    
    st.markdown("---")
    
    with st.expander("👥 STATUS DA EQUIPE", expanded=False):
        if not all_analysts.empty:
            status_list = []
            for idx, analyst in all_analysts.iterrows():
                name = analyst["nome"]
                intervals = analyst["intervalos"]
                temp_df = pd.DataFrame([{"horario": h} for h in intervals])
                status, color = calculate_status(current_time, temp_df, shift_start, shift_end)
                status_list.append({"Nome": name, "Status": status, "Cor": color})
            status_df = pd.DataFrame(status_list)
            for i in range(0, len(status_df), cols_equipe):
                cols = st.columns(cols_equipe)
                for j, col in enumerate(cols):
                    if i + j < len(status_df):
                        row = status_df.iloc[i + j]
                        color_map_team = {"green": cor_equipe, "orange": "#ff9800", "blue": "#2196f3", "gray": "#9e9e9e"}
                        col.markdown(f"""
                        <div style="padding: 0.8rem; border-radius: 0.5rem; background-color: {color_map_team.get(row['Cor'], '#eee')}; color: white; text-align: center; margin: 0.3rem 0;">
                            <div style="font-weight: bold; font-size: {0.9 * (tam_equ_f/100)}rem;">{row['Nome']}</div>
                            <div style="font-size: {0.8 * (tam_equ_f/100)}rem; opacity: 0.9;">{row['Status']}</div>
                        </div>
                        """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ Erro: {str(e)}")
