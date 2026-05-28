# Dashboard de Horários (Google Sheets → Web)

Este app lê uma aba específica de uma planilha do Google Sheets, localiza a linha cujo Nome é "Gabriel Goulart da Maia" e exibe os valores (horários) das colunas F, H e K.

## Requisitos
- Python 3.10+
- Credenciais Google (Service Account)

## Instalação

### 1. Criar ambiente virtual
```bash
python -m venv .venv
```

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

## Autenticação (Service Account)

### 1. Criar Service Account no Google Cloud

1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto ou selecione um existente
3. Ative a **Google Sheets API**:
   - Menu → APIs e Serviços → Biblioteca
   - Pesquise "Google Sheets API"
   - Clique em "Ativar"

4. Crie uma conta de serviço:
   - Menu → APIs e Serviços → Credenciais
   - Clique em "Criar Credenciais" → "Conta de serviço"
   - Nome: `pausas-app` (ou outro nome)
   - Clique em "Criar e continuar"
   - Pule as permissões (clique "Continuar")
   - Clique em "Concluir"

5. Criar chave JSON:
   - Clique na conta de serviço que você criou
   - Vá na aba "Chaves"
   - Clique em "Adicionar chave" → "Criar nova chave"
   - Escolha **JSON**
   - Clique em "Criar"
   - O arquivo JSON será baixado automaticamente

6. Preparar o arquivo:
   - Renomeie o arquivo baixado para: `service_account.json`
   - **Coloque este arquivo na mesma pasta do `app.py`**

### 2. Compartilhar a planilha

1. Abra o arquivo `service_account.json` e copie o valor do campo `client_email`
   - Será algo como: `pausas-app@seu-projeto.iam.gserviceaccount.com`

2. Abra sua planilha Google Sheets

3. Clique em **"Compartilhar"**

4. Cole o e-mail da conta de serviço

5. Defina a permissão como **"Visualizador"**

6. Clique em "Enviar"

## Configuração

Os valores já estão configurados no código:
- **SHEET_ID:** `1bwrJmasPZUz5F8qsITo2RhFYTHb8e2OnSHlCWLSDOIs`
- **SHEET_TAB:** `pagina`
- **ROW_MATCH_VALUE:** `Gabriel Goulart da Maia`

## Uso

### Executar o dashboard
```bash
streamlit run app.py
```

O navegador abrirá automaticamente em `http://localhost:8501`

### Funcionalidades

- **Cards de métricas:** Exibe os valores das colunas F, H e K
- **Tabela ordenada:** Lista todos os horários em ordem cronológica
- **Gráfico de distribuição:** Histograma mostrando distribuição por hora do dia
- **Recarregar dados:** Botão manual para atualizar
- **Auto-refresh:** Opção de recarregar automaticamente a cada 5 minutos

## Segurança

⚠️ **IMPORTANTE:**
- **NUNCA** faça commit do arquivo `service_account.json` no Git/GitHub
- **NUNCA** compartilhe esse arquivo publicamente
- Adicione `service_account.json` ao `.gitignore`

### Exemplo de `.gitignore`:
```
service_account.json
*.json
.venv/
__pycache__/
.streamlit/
```

## Estrutura de Arquivos

```
dashboard-pausas/
├── app.py                    # Aplicação Streamlit principal
├── requirements.txt          # Dependências Python
├── service_account.json      # Credenciais (NÃO FAZER COMMIT!)
├── test_connection.py        # Script de teste (opcional)
└── README.md                 # Este arquivo
```

## Solução de Problemas

### Erro: "service_account.json não encontrado"
- Certifique-se de que o arquivo está na mesma pasta do `app.py`
- Verifique se o nome está correto (sem `.txt` no final)

### Erro: "Linha não encontrada"
- Verifique se o nome "Gabriel Goulart da Maia" está exatamente assim na planilha
- Confirme que está na coluna A

### Erro: "Unable to parse range"
- Verifique se o nome da aba está correto (sem acentos)
- Confirme que a aba se chama "pagina"

### Erro: "Permission denied" ou erro 403
- Verifique se compartilhou a planilha com o e-mail da conta de serviço
- Confirme que a permissão é pelo menos "Visualizador"

## Suporte

Para mais informações sobre a Google Sheets API:
- [Documentação oficial](https://developers.google.com/sheets/api)
- [Guia de autenticação](https://developers.google.com/sheets/api/guides/authorizing)
