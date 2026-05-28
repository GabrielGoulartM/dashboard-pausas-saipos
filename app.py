import os, re, time, json
import pandas as pd
from dateutil import parser
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# ========== CONFIGURAÇÕES DE AUTENTICAÇÃO ==========
def check_password():
    """Retorna True se o usuário digitou a senha correta"""
    
    def password_entered():
        senha_correta = "suporte2024"
        
        try:
            if hasattr(st, 'secrets') and "auth_password" in st.secrets:
                senha_correta = st.secrets["auth_password"]
        except:
            pass
        
        if st.session_state["password"] == senha_correta:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    # Tela de login personalizada Saipos
    st.markdown("## 🔐 Dashboard de Pausas - Saipos")
    st.markdown("#### *Acesso exclusivo para analistas de suporte*")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.text_input(
            "Digite a senha de acesso:",
            type="password",
            key="password",
            on_change=password_entered
        )
        
        if st.session_state.get("password_correct") == False:
            st.error("❌ Senha incorreta. Tente novamente.")
        
        st.caption("💡 Entre em contato com Gabriel Goulart se não tiver acesso.")
    
    return False

# ========== RESTO DO CÓDIGO ==========

def get_sheets_service_service_account():
    try:
        if hasattr(st, 'secrets') and "service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["service_account"],
                scopes=SCOPES
            )
        else:
            creds = service_account.Credentials.from_service_account_file(
                "service_account.json",
                scopes=SCOPES
            )
    except:
        creds = service_account.Credentials.from_service_account_file(
            "service_account.json",
            scopes=SCOPES
        )
    return build("sheets", "v4", credentials=creds)

def detect_time(val):
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip()
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

@st.cache_data(ttl=21600)
def get_all_agents(sheet_id, sheet_tab):
    service = get_sheets_service_service_account()
    rng = f"{sheet_tab}!A:A"
    values = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute().get("values", [])
    
    agents = []
    for row in values:
        if row and row[0] and str(row[0]).strip():
            name = str(row[0]).strip()
            if name not in agents:
                agents.append(name)
    return sorted(agents)

@st.cache_data(ttl=21600)
def fetch_row_data(sheet_id, sheet_tab, row_value):
    service = get_sheets_service_service_account()
    rng = f"{sheet_tab}!A:M"
    values = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute().get("values", [])
    
    if not values:
        raise ValueError("Aba vazia ou inexistente.")
    
    target = str(row_value).strip().lower()
    row = None
    for r in values:
        if len(r) > 0 and str(r[0]).strip().lower() == target:
            row = r
            break
    
    if row is None:
        raise ValueError(f"Linha não encontrada para '{row_value}'.")
    
    data = {
        "intervalo_inicio": row[5] if len(row) > 5 else None,
        "intervalo_fim": row[6] if len(row) > 6 else None,
        "pausa1_inicio": row[7] if len(row) > 7 else None,
        "pausa1_fim": row[8] if len(row) > 8 else None,
        "pausa1_motivo": row[9] if len(row) > 9 else None,
        "pausa2_inicio": row[10] if len(row) > 10 else None,
        "pausa2_fim": row[11] if len(row) > 11 else None,
        "pausa2_motivo": row[12] if len(row) > 12 else None,
    }
    
    data["intervalo_inicio_norm"] = detect_time(data["intervalo_inicio"])
    data["intervalo_fim_norm"] = detect_time(data["intervalo_fim"])
    data["pausa1_inicio_norm"] = detect_time(data["pausa1_inicio"])
    data["pausa1_fim_norm"] = detect_time(data["pausa1_fim"])
    data["pausa2_inicio_norm"] = detect_time(data["pausa2_inicio"])
    data["pausa2_fim_norm"] = detect_time(data["pausa2_fim"])
    
    return data

st.set_page_config(
    page_title="Dashboard de Pausas - Saipos",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== VERIFICAÇÃO DE AUTENTICAÇÃO ==========
if not check_password():
    st.stop()

# ========== DASHBOARD ==========

# Header personalizado Saipos
st.markdown("""
    <div style='text-align: center; padding: 1rem 0 2rem 0;'>
        <h1 style='color: #1f77b4; margin-bottom: 0.5rem;'>⏱️ Dashboard de Pausas</h1>
        <p style='font-size: 1.2rem; color: #666; margin-bottom: 0.3rem;'>
            <strong>Saipos</strong> - Suporte ao Cliente
        </p>
        <p style='font-size: 0.9rem; color: #888; font-style: italic;'>
            De analista, para analista ❤️
        </p>
    </div>
""", unsafe_allow_html=True)

sheet_id = "1bwrJmasPZUz5F8qsITo2RhFYTHb8e2OnSHlCWLSDOIs"
sheet_tab = "pagina"

with st.sidebar:
    st.markdown("### ⚙️ Configurações")
    
    try:
        agents = get_all_agents(sheet_id, sheet_tab)
        
        default_index = 0
        if "Gabriel Goulart da Maia" in agents:
            default_index = agents.index("Gabriel Goulart da Maia")
        
        selected_agent = st.selectbox(
            "👤 Selecionar Agente",
            options=agents,
            index=default_index
        )
    except Exception as e:
        st.error(f"Erro ao carregar agentes: {e}")
        selected_agent = "Gabriel Goulart da Maia"
    
    st.info(f"**📄 Aba:** {sheet_tab}")
    
    st.divider()
    
    auto_refresh = st.checkbox("🔄 Auto-refresh (6 horas)", value=False)
    btn = st.button("🔄 Recarregar Dados", type="primary", use_container_width=True)
    
    st.divider()
    
    # Botão de sugestões
    st.markdown("### 💡 Sugestões")
    st.markdown("Tem alguma ideia para melhorar o dashboard?")
    
    # Link para Google Forms
    FORMS_URL = "https://forms.gle/ojyXj3iT9ypJu5zp9"
    
    if st.button("📝 Enviar Sugestão", use_container_width=True):
        st.markdown(f"[Clique aqui para abrir o formulário]({FORMS_URL})")
        st.balloons()
    
    st.caption("Sua opinião é muito importante! 🙏")
    
    st.divider()
    
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["password_correct"] = False
        st.rerun()
    
    st.caption("💡 Dados atualizados automaticamente a cada 6 horas")
    
    # Footer da sidebar
    st.divider()
    st.markdown("""
        <div style='text-align: center; font-size: 0.8rem; color: #888;'>
            <p>Desenvolvido com carinho ❤️</p>
            <p>para todos os analistas do suporte</p>
            <p style='margin-top: 0.5rem;'>
                <strong>Saipos</strong> | v1.0
            </p>
        </div>
    """, unsafe_allow_html=True)

last_run = st.session_state.get("last_run", 0)
run_now = btn or (auto_refresh and time.time() - last_run > 21600)

if run_now:
    st.session_state["last_run"] = time.time()
    st.cache_data.clear()

try:
    data = fetch_row_data(sheet_id, sheet_tab, selected_agent)
    
    st.markdown("## 🍽️ Intervalo de Almoço")
    
    col1, col2 = st.columns(2)
    
    with col1:
        inicio_display = data['intervalo_inicio_norm'] or data['intervalo_inicio'] or '--:--'
        st.metric(label="Início do Intervalo (Coluna F)", value=inicio_display)
    
    with col2:
        fim_display = data['intervalo_fim_norm'] or data['intervalo_fim'] or '--:--'
        st.metric(label="Fim do Intervalo (Coluna G)", value=fim_display)
    
    if data['intervalo_inicio_norm'] and data['intervalo_fim_norm']:
        try:
            h1, m1 = map(int, data['intervalo_inicio_norm'].split(':'))
            h2, m2 = map(int, data['intervalo_fim_norm'].split(':'))
            duracao_min = (h2 * 60 + m2) - (h1 * 60 + m1)
            st.info(f"⏰ **Duração do intervalo:** {duracao_min} minutos ({duracao_min // 60}h {duracao_min % 60}min)")
        except:
            pass
    
    st.divider()
    
    st.markdown("## ☕ Pausas Adicionais")
    
    tem_pausa1 = data['pausa1_inicio'] or data['pausa1_fim'] or data['pausa1_motivo']
    tem_pausa2 = data['pausa2_inicio'] or data['pausa2_fim'] or data['pausa2_motivo']
    
    if not tem_pausa1 and not tem_pausa2:
        st.success("✅ Nenhuma pausa adicional registrada hoje.")
    else:
        if tem_pausa1:
            st.markdown("### 🔵 Pausa 1")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                inicio_p1 = data['pausa1_inicio_norm'] or data['pausa1_inicio'] or '--:--'
                st.metric(label="Início (Coluna H)", value=inicio_p1)
            with col2:
                fim_p1 = data['pausa1_fim_norm'] or data['pausa1_fim'] or '--:--'
                st.metric(label="Fim (Coluna I)", value=fim_p1)
            with col3:
                motivo_p1 = data['pausa1_motivo'] or "Não informado"
                st.metric(label="Motivo (Coluna J)", value=motivo_p1)
            
            if data['pausa1_inicio_norm'] and data['pausa1_fim_norm']:
                try:
                    h1, m1 = map(int, data['pausa1_inicio_norm'].split(':'))
                    h2, m2 = map(int, data['pausa1_fim_norm'].split(':'))
                    duracao_min = (h2 * 60 + m2) - (h1 * 60 + m1)
                    st.caption(f"⏱️ Duração: {duracao_min} minutos")
                except:
                    pass
            st.divider()
        
        if tem_pausa2:
            st.markdown("### 🟣 Pausa 2")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                inicio_p2 = data['pausa2_inicio_norm'] or data['pausa2_inicio'] or '--:--'
                st.metric(label="Início (Coluna K)", value=inicio_p2)
            with col2:
                fim_p2 = data['pausa2_fim_norm'] or data['pausa2_fim'] or '--:--'
                st.metric(label="Fim (Coluna L)", value=fim_p2)
            with col3:
                motivo_p2 = data['pausa2_motivo'] or "Não informado"
                st.metric(label="Motivo (Coluna M)", value=motivo_p2)
            
            if data['pausa2_inicio_norm'] and data['pausa2_fim_norm']:
                try:
                    h1, m1 = map(int, data['pausa2_inicio_norm'].split(':'))
                    h2, m2 = map(int, data['pausa2_fim_norm'].split(':'))
                    duracao_min = (h2 * 60 + m2) - (h1 * 60 + m1)
                    st.caption(f"⏱️ Duração: {duracao_min} minutos")
                except:
                    pass
    
    st.divider()
    
    with st.expander("📊 Dados Brutos da Planilha"):
        st.json({
            "Intervalo": {
                "Início (F)": data['intervalo_inicio'],
                "Fim (G)": data['intervalo_fim']
            },
            "Pausa 1": {
                "Início (H)": data['pausa1_inicio'],
                "Fim (I)": data['pausa1_fim'],
                "Motivo (J)": data['pausa1_motivo']
            },
            "Pausa 2": {
                "Início (K)": data['pausa2_inicio'],
                "Fim (L)": data['pausa2_fim'],
                "Motivo (M)": data['pausa2_motivo']
            }
        })

except Exception as e:
    st.error(f"❌ Erro: {str(e)}")
    if "service_account.json" in str(e):
        st.info("💡 Certifique-se de que o arquivo `service_account.json` está na mesma pasta do app.")
    elif "não encontrada" in str(e):
        st.info(f"💡 Verifique se o nome '{selected_agent}' está correto na planilha.")

# Footer principal
st.markdown("---")
st.markdown("""
    <div style='text-align: center; padding: 2rem 0 1rem 0; color: #888;'>
        <p style='font-size: 0.9rem;'>
            Dashboard desenvolvido com ❤️ por <strong>Gabriel Goulart</strong>
        </p>
        <p style='font-size: 0.8rem; margin-top: 0.5rem;'>
            <strong>Saipos</strong> - Transformando dados em insights para o suporte
        </p>
    </div>
""", unsafe_allow_html=True)
