# 🎯 Dashboard de Pausas - Saipos

Dashboard para gestão de intervalos e pausas da operação de suporte.

## 📋 Funcionalidades

- ✅ **Próximo Intervalo em Destaque** - Card visual com countdown em tempo real
- ✅ **Status Operacional** - Identifica se está em atendimento, intervalo, etc.
- ✅ **Visão da Jornada** - Timeline mostrando progresso do dia
- ✅ **Status da Equipe** - Visão de todos os analistas simultaneamente
- ✅ **Integração Google Sheets** - Dados em tempo real da planilha

## 🚀 Como Usar

### 1. Instalar dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar credenciais Google

**OPÇÃO A - OAuth (Recomendada):**
1. Acesse: https://console.cloud.google.com/
2. Crie um projeto
3. Ative "Google Sheets API"
4. Crie OAuth Client ID (Desktop App)
5. Baixe e renomeie para `credentials.json`

**OPÇÃO B - Service Account:**
1. Crie uma Service Account no Google Cloud
2. Baixe e renomeie para `service_account.json`
3. Compartilhe a planilha com o email da service account

### 3. Executar
```bash
streamlit run app.py
```

### 4. Configurar na interface
- **SHEET_ID**: Copie da URL da planilha
- **SHEET_TAB**: Nome da aba
- **Nome do Analista**: Nome exato da planilha
- **Modo de autenticação**: OAuth ou Service Account

## 📊 Estrutura da Planilha

| A (Nome) | ... | F (Pausa 1) | ... | H (Pausa 2) | ... | K (Pausa 3) |
|----------|-----|-------------|-----|-------------|-----|-------------|
| Gabriel  | ... | 13:50       | ... | 15:30       | ... | 17:00       |

## ⚙️ Configurações

### Alterar duração do intervalo (linha ~180 do app.py):
```python
duration_mins = 60  # minutos
```

### Alterar horários de jornada (linha ~250 do app.py):
```python
shift_start = "09:00"
shift_end = "18:00"
```

## 🔒 Segurança

⚠️ **NUNCA commite arquivos de credenciais!**
- `credentials.json`
- `service_account.json`
- `token.json`

Eles já estão no `.gitignore`.

## 📞 Suporte

Para dúvidas sobre:
- Google Sheets API: https://developers.google.com/sheets
- Streamlit: https://docs.streamlit.io
