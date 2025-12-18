import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import bcrypt
import google.generativeai as genai
import extra_streamlit_components as stx
import time
from datetime import datetime, date, timedelta

# --- Configuração da Página ---
st.set_page_config(
    page_title="Gerenciador Financeiro Pro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Configuração DB ---
DB_FILE = 'financeiro.db'

# --- Inicialização do Banco de Dados ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, name TEXT)''')
    
    # Transações
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, category TEXT NOT NULL,
        value REAL NOT NULL, date TEXT NOT NULL, description TEXT, recurring TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Metas
    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, target_value REAL NOT NULL,
        current_value REAL DEFAULT 0, deadline TEXT, FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Dívidas
    c.execute('''CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, description TEXT NOT NULL, total_value REAL NOT NULL,
        paid_value REAL DEFAULT 0, due_date TEXT, FOREIGN KEY(user_id) REFERENCES users(id))''')

    # Financiamentos e Parcelas
    c.execute('''CREATE TABLE IF NOT EXISTS financings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, total_original_value REAL NOT NULL,
        created_at TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS installments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, financing_id INTEGER NOT NULL, installment_number INTEGER NOT NULL,
        value REAL NOT NULL, is_paid INTEGER DEFAULT 0,
        FOREIGN KEY(financing_id) REFERENCES financings(id) ON DELETE CASCADE)''')
    
    conn.commit()
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetch:
            data = c.fetchall()
            columns = [description[0] for description in c.description]
            df = pd.DataFrame(data, columns=columns)
            conn.close()
            return df
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Erro BD: {e}")
    finally:
        conn.close()
    return None

# --- Autenticação e Cookies ---

def get_manager():
    return stx.CookieManager(key="auth_cookie_manager")

cookie_manager = get_manager()

def convert_to_native_types(user_row):
    """Converte tipos do Pandas para Python puro para evitar erros de JSON"""
    return {
        "id": int(user_row['id']),
        "username": str(user_row['username']),
        "name": str(user_row['name']),
        "password": str(user_row['password'])
    }

def login_check(username, password):
    df = run_query("SELECT * FROM users WHERE username = ?", (username,), fetch=True)
    if not df.empty:
        user_row = df.iloc[0]
        try:
            if bcrypt.checkpw(password.encode('utf-8'), user_row['password'].encode('utf-8') if isinstance(user_row['password'], str) else user_row['password']):
                return convert_to_native_types(user_row)
        except Exception as e:
             st.error(f"Erro na verificação: {e}")
    return None

def register_user(username, password, name):
    try:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        run_query("INSERT INTO users (username, password, name) VALUES (?, ?, ?)", (username, hashed, name))
        return True
    except:
        return False

# --- Inicialização de Estado ---
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state['db_initialized'] = True

if 'user' not in st.session_state:
    st.session_state['user'] = None

# Variável de controle para o Logout
if 'logout_just_now' not in st.session_state:
    st.session_state['logout_just_now'] = False

# --- LÓGICA DE PERSISTÊNCIA (AUTO-LOGIN) ---
cookie_username = cookie_manager.get(cookie='financeiro_user')

# Só tenta o auto-login se o usuário NÃO estiver logado E NÃO acabou de clicar em sair
if st.session_state['user'] is None and cookie_username and not st.session_state['logout_just_now']:
    user_data_df = run_query("SELECT * FROM users WHERE username = ?", (cookie_username,), fetch=True)
    if not user_data_df.empty:
        st.session_state['user'] = convert_to_native_types(user_data_df.iloc[0])
        st.rerun()

# Se a trava de logout estava ativa, desativa ela agora (para permitir login futuro)
if st.session_state['user'] is None and st.session_state['logout_just_now']:
    # Mantém a trava ativa apenas durante a renderização da página de login
    # O reset acontecerá naturalmente quando o usuário tentar logar novamente
    pass

# --- Funções Auxiliares UI ---
def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

CATEGORIAS = {
    "Entrada": ["Salário", "Renda Extra", "Investimentos", "Outros"],
    "Saída": ["Alimentação", "Moradia", "Transporte", "Lazer", "Dívidas", "Saúde", "Educação", "Outros"]
}

# --- IA Gemini ---
def consultor_financeiro_ai(api_key, context_data, user_question):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro') 
        prompt = f"Analise: {context_data}. Pergunta: {user_question}. Responda curto e em Markdown."
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro IA: {str(e)}"

# ==========================================
# PÁGINA DE LOGIN
# ==========================================
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🔐 Acesso Financeiro</h1>", unsafe_allow_html=True)
        st.markdown("---")
        
        tab_login, tab_cadastro = st.tabs(["Entrar", "Criar Conta"])
        
        with tab_login:
            with st.form("form_login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Acessar Painel", type="primary", use_container_width=True):
                    user = login_check(u, p)
                    if user is not None:
                        # Reseta a trava de logout ao logar com sucesso
                        st.session_state['logout_just_now'] = False
                        st.session_state['user'] = user
                        cookie_manager.set('financeiro_user', u, expires_at=datetime.now() + timedelta(days=5))
                        st.success("Login realizado!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
        
        with tab_cadastro:
            with st.form("form_cadastro"):
                nu = st.text_input("Novo Usuário")
                nn = st.text_input("Nome Completo")
                np = st.text_input("Senha", type="password")
                if st.form_submit_button("Cadastrar", use_container_width=True):
                    if len(np) < 3: st.error("Senha curta.")
                    elif register_user(nu, np, nn):
                        st.success("Conta criada! Vá para a aba Entrar.")
                    else: st.error("Usuário já existe.")

# ==========================================
# INTERFACE DO DASHBOARD
# ==========================================
def dashboard_interface():
    user = st.session_state['user']
    user_id = user['id']
    
    st.sidebar.title(f"Olá, {user['name']}!")
    
    menu_opts = ["Dashboard", "Lançamentos", "Extrato", "Simulação Financiamento", "Metas", "Dívidas", "Consultor IA"]
    
    default_index = 0
    if "page" in st.query_params:
        p_url = st.query_params["page"]
        if p_url in menu_opts:
            default_index = menu_opts.index(p_url)
            
    page = st.sidebar.radio("Menu", menu_opts, index=default_index)
    
    if st.query_params.get("page") != page:
        st.query_params["page"] = page
    
    st.sidebar.markdown("---")
    
    # --- LÓGICA DE LOGOUT CORRIGIDA ---
    if st.sidebar.button("🚪 Sair"):
        st.session_state['logout_just_now'] = True  # Ativa a trava
        st.session_state['user'] = None             # Remove usuário da sessão
        cookie_manager.delete('financeiro_user')    # Manda deletar cookie
        st.query_params.clear()                     # Limpa URL
        st.rerun()                                  # Recarrega a página

    # --- Páginas ---
    
    if page == "Dashboard":
        st.title("📊 Painel Geral")
        c1, c2 = st.columns(2)
        d_ini = c1.date_input("De", date(date.today().year, date.today().month, 1))
        d_fim = c2.date_input("Até", date.today())
        
        df = run_query("SELECT * FROM transactions WHERE user_id = ? AND date BETWEEN ? AND ?", (user_id, d_ini, d_fim), fetch=True)
        if not df.empty:
            ent = df[df['type']=='Entrada']['value'].sum()
            sai = df[df['type']=='Saída']['value'].sum()
            saldo = ent - sai
            k1, k2, k3 = st.columns(3)
            k1.metric("Receitas", format_currency(ent))
            k2.metric("Despesas", format_currency(sai), delta_color="inverse")
            k3.metric("Saldo", format_currency(saldo))
            
            g1, g2 = st.columns(2)
            g1.plotly_chart(px.pie(df[df['type']=='Saída'], values='value', names='category', title="Gastos"), use_container_width=True)
            g2.plotly_chart(px.bar(df, x='date', y='value', color='type', title="Fluxo"), use_container_width=True)
        else: st.info("Sem dados.")

    elif page == "Lançamentos":
        st.title("📝 Novo Lançamento")
        with st.container(border=True):
            with st.form("add_t"):
                c1, c2 = st.columns(2)
                t = c1.selectbox("Tipo", ["Saída", "Entrada"])
                c = c2.selectbox("Categoria", CATEGORIAS[t])
                v = c1.number_input("Valor (R$)", min_value=0.01)
                d = c2.date_input("Data", date.today())
                desc = st.text_input("Descrição")
                if st.form_submit_button("Confirmar", type="primary"):
                    run_query("INSERT INTO transactions (user_id, type, category, value, date, description, recurring) VALUES (?,?,?,?,?,?,?)",
                            (user_id, t, c, v, d, desc, "Não"))
                    st.success("Salvo!")

    elif page == "Extrato":
        st.title("📑 Extrato")
        df = run_query("SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC", (user_id,), fetch=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        with st.expander("Excluir"):
            did = st.number_input("ID", min_value=0)
            if st.button("Apagar"):
                run_query("DELETE FROM transactions WHERE id=? AND user_id=?", (did, user_id))
                st.rerun()

    elif page == "Simulação Financiamento":
        st.title("🏗️ Simulador")
        with st.expander("Nova Simulação"):
            with st.form("new_sim"):
                nm = st.text_input("Nome")
                vt = st.number_input("Valor Total", min_value=1.0)
                qp = st.number_input("Parcelas", min_value=1, value=12)
                if st.form_submit_button("Gerar"):
                    c = sqlite3.connect(DB_FILE)
                    cur = c.cursor()
                    cur.execute("INSERT INTO financings (user_id, name, total_original_value, created_at) VALUES (?,?,?,?)", (user_id, nm, vt, date.today()))
                    fid = cur.lastrowid
                    vp = vt/qp
                    for i in range(1, int(qp)+1):
                        cur.execute("INSERT INTO installments (financing_id, installment_number, value) VALUES (?,?,?)", (fid, i, vp))
                    c.commit()
                    c.close()
                    st.rerun()
        
        st.divider()
        fins = run_query("SELECT * FROM financings WHERE user_id=?", (user_id,), fetch=True)
        if not fins.empty:
            dic = fins.set_index('id')['name'].to_dict()
            sel = st.selectbox("Simulação", list(dic.keys()), format_func=lambda x: dic[x])
            parcs = run_query("SELECT * FROM installments WHERE financing_id=? ORDER BY installment_number", (sel,), fetch=True)
            
            pago = parcs[parcs['is_paid']==1]['value'].sum()
            total = parcs['value'].sum()
            
            c1, c2 = st.columns([1, 2])
            c1.plotly_chart(px.pie(names=['Pago', 'Falta'], values=[pago, total-pago], color_discrete_sequence=['#2E8B57', '#FFD700'], hole=0.6), use_container_width=True)
            
            with c2:
                with st.container(height=400):
                    for _, r in parcs.iterrows():
                        cc1, cc2, cc3 = st.columns([0.5, 2, 1.5])
                        chk = cc1.checkbox("", value=bool(r['is_paid']), key=f"c{r['id']}")
                        color = "green" if r['is_paid'] else "orange"
                        cc2.markdown(f":{color}[**{r['installment_number']}ª**]")
                        nv = cc3.number_input("R$", value=float(r['value']), key=f"v{r['id']}", label_visibility="collapsed")
                        
                        if chk != bool(r['is_paid']) or nv != r['value']:
                            run_query("UPDATE installments SET is_paid=?, value=? WHERE id=?", (1 if chk else 0, nv, r['id']))
                            st.rerun()
            
            if st.button("🗑️ Excluir"):
                run_query("DELETE FROM financings WHERE id=?", (sel,))
                st.rerun()

    elif page == "Metas":
        st.title("🎯 Metas")
        with st.form("m_add"):
            ti = st.text_input("Meta")
            va = st.number_input("Alvo", min_value=1.0)
            if st.form_submit_button("Criar"):
                run_query("INSERT INTO goals (user_id, title, target_value) VALUES (?,?,?)", (user_id, ti, va))
                st.rerun()
        goals = run_query("SELECT * FROM goals WHERE user_id=?", (user_id,), fetch=True)
        for _, g in goals.iterrows():
            st.write(f"{g['title']}: {format_currency(g['current_value'])} / {format_currency(g['target_value'])}")
            st.progress(min(g['current_value']/g['target_value'], 1.0))
            c1, c2 = st.columns([3,1])
            nv = c1.number_input("Aporte", key=f"g{g['id']}", label_visibility="collapsed")
            if c2.button("Add", key=f"b{g['id']}"):
                 run_query("UPDATE goals SET current_value = current_value + ? WHERE id=?", (nv, g['id']))
                 st.rerun()

    elif page == "Dívidas":
        st.title("💸 Dívidas")
        with st.form("d_add"):
            de = st.text_input("Descrição")
            vt = st.number_input("Total", min_value=1.0)
            if st.form_submit_button("Registrar"):
                run_query("INSERT INTO debts (user_id, description, total_value) VALUES (?,?,?)", (user_id, de, vt))
                st.rerun()
        st.dataframe(run_query("SELECT * FROM debts WHERE user_id=?", (user_id,), fetch=True), use_container_width=True)

    elif page == "Consultor IA":
        st.title("🤖 Consultor Gemini")
        api = st.text_input("API Key", type="password")
        if api:
            msg = st.chat_input("Dúvida?")
            if msg:
                d = run_query("SELECT * FROM transactions WHERE user_id=? LIMIT 15", (user_id,), fetch=True).to_string()
                with st.spinner("Analisando..."):
                    st.write(consultor_financeiro_ai(api, d, msg))

# ==========================================
# ROTEAMENTO
# ==========================================
if st.session_state['user'] is None:
    login_page()
else:
    dashboard_interface()
