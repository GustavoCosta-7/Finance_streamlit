import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from datetime import datetime, date

# --- Configuração da Página ---
st.set_page_config(
    page_title="Gerenciador Financeiro Pessoal",
    page_icon="💰",
    layout="wide"
)

# --- Gerenciamento de Banco de Dados (SQLite) ---
DB_FILE = 'financeiro.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabela de Transações
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            value REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            recurring TEXT
        )
    ''')
    
    # Tabela de Metas
    c.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            target_value REAL NOT NULL,
            current_value REAL DEFAULT 0,
            deadline TEXT
        )
    ''')

    # Tabela de Dívidas
    c.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            total_value REAL NOT NULL,
            paid_value REAL DEFAULT 0,
            due_date TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    if fetch:
        data = c.fetchall()
        columns = [description[0] for description in c.description]
        df = pd.DataFrame(data, columns=columns)
        conn.close()
        return df
    conn.commit()
    conn.close()
    return None

# Inicializar DB na primeira execução
init_db()

# --- Funções Auxiliares ---
def format_currency(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

CATEGORIAS = {
    "Entrada": ["Salário", "Renda Extra", "Investimentos", "Outros"],
    "Saída": ["Alimentação", "Moradia", "Transporte", "Lazer", "Dívidas", "Saúde", "Educação", "Outros"]
}

# --- Sidebar de Navegação ---
st.sidebar.title("💰 Finanças Pessoais")
page = st.sidebar.radio("Navegação", ["Dashboard", "Lançamentos", "Extrato & Controle", "Metas", "Dívidas"])

# --- Lógica das Páginas ---

if page == "Dashboard":
    st.title("📊 Dashboard Financeiro")
    
    # Filtro de Mês/Ano
    col1, col2 = st.columns(2)
    with col1:
        mes_selecionado = st.selectbox("Mês", range(1, 13), index=datetime.now().month - 1)
    with col2:
        ano_selecionado = st.number_input("Ano", min_value=2020, max_value=2030, value=datetime.now().year)
    
    # Carregar dados - CORREÇÃO AQUI: adicionado fetch=True
    df = run_query("SELECT * FROM transactions", fetch=True)
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        
        # Filtrar pelo período selecionado
        df_filtered = df[(df['month'] == mes_selecionado) & (df['year'] == ano_selecionado)]
        
        # Cálculos
        total_entradas = df_filtered[df_filtered['type'] == 'Entrada']['value'].sum()
        total_saidas = df_filtered[df_filtered['type'] == 'Saída']['value'].sum()
        saldo = total_entradas - total_saidas
        
        # Cards de KPIs
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Entradas", format_currency(total_entradas), delta_color="normal")
        kpi2.metric("Saídas", format_currency(total_saidas), delta_color="inverse")
        kpi3.metric("Saldo do Mês", format_currency(saldo), delta=f"{saldo:.2f}")
        
        st.markdown("---")
        
        # Gráficos
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Gastos por Categoria")
            df_saidas = df_filtered[df_filtered['type'] == 'Saída']
            if not df_saidas.empty:
                fig_pizza = px.pie(df_saidas, values='value', names='category', hole=0.4)
                st.plotly_chart(fig_pizza, use_container_width=True)
            else:
                st.info("Sem saídas registradas neste mês.")
                
        with c2:
            st.subheader("Entradas vs Saídas (Anual)")
            df_anual = df[df['year'] == ano_selecionado].groupby(['month', 'type'])['value'].sum().reset_index()
            if not df_anual.empty:
                fig_bar = px.bar(df_anual, x='month', y='value', color='type', barmode='group',
                                 labels={'value': 'Valor', 'month': 'Mês', 'type': 'Tipo'},
                                 color_discrete_map={'Entrada': 'green', 'Saída': 'red'})
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Sem dados anuais.")
                
    else:
        st.warning("Nenhuma transação encontrada. Comece registrando em 'Lançamentos'.")

elif page == "Lançamentos":
    st.title("📝 Registrar Movimentação")
    
    with st.form("form_transaction", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tipo = st.selectbox("Tipo", ["Entrada", "Saída"])
            data_mov = st.date_input("Data", datetime.now())
        with col2:
            categoria = st.selectbox("Categoria", CATEGORIAS[tipo])
            valor = st.number_input("Valor (R$)", min_value=0.01, step=0.01)
            
        descricao = st.text_input("Descrição / Observação")
        recorrente = st.checkbox("É recorrente? (Marcação apenas)")
        
        submitted = st.form_submit_button("Salvar Movimentação")
        
        if submitted:
            rec_text = "Sim" if recorrente else "Não"
            # Aqui não precisa de fetch=True pois é um INSERT
            run_query('''
                INSERT INTO transactions (type, category, value, date, description, recurring)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (tipo, categoria, valor, data_mov, descricao, rec_text))
            st.success("Movimentação registrada com sucesso!")

elif page == "Extrato & Controle":
    st.title("📑 Extrato Mensal")
    
    # Filtros
    col1, col2 = st.columns(2)
    with col1:
        filtro_mes = st.selectbox("Mês", range(1, 13), index=datetime.now().month - 1, key='extrato_mes')
    with col2:
        filtro_ano = st.number_input("Ano", value=datetime.now().year, key='extrato_ano')
        
    # Carregar dados - CORREÇÃO AQUI: adicionado fetch=True
    df = run_query("SELECT * FROM transactions", fetch=True)
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df_filtered = df[(df['date'].dt.month == filtro_mes) & (df['date'].dt.year == filtro_ano)].sort_values(by='date', ascending=False)
        
        # Exibição da tabela
        st.dataframe(
            df_filtered, 
            column_config={
                "value": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                "date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "id": None # Ocultar ID
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Área de Exclusão
        st.markdown("### 🗑️ Gerenciar Registros")
        id_to_delete = st.number_input("ID para excluir (veja na tabela se necessário ativar coluna ID)", min_value=0, step=1)
        if st.button("Excluir Registro"):
            run_query("DELETE FROM transactions WHERE id = ?", (id_to_delete,))
            st.rerun() # Recarrega a página para atualizar a tabela
            
        # Exportação
        st.markdown("### 📥 Relatórios")
        csv = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button("Baixar Extrato (CSV)", data=csv, file_name=f"extrato_{filtro_mes}_{filtro_ano}.csv", mime='text/csv')
    else:
        st.info("Nenhum dado encontrado.")

elif page == "Metas":
    st.title("🎯 Metas Financeiras")
    
    # Criar Meta
    with st.expander("Nova Meta"):
        with st.form("form_meta"):
            titulo = st.text_input("Nome da Meta (ex: Viagem)")
            valor_alvo = st.number_input("Valor Alvo (R$)", min_value=1.0)
            valor_atual = st.number_input("Valor Já Guardado (R$)", min_value=0.0)
            prazo = st.date_input("Prazo")
            
            if st.form_submit_button("Criar Meta"):
                run_query("INSERT INTO goals (title, target_value, current_value, deadline) VALUES (?, ?, ?, ?)", 
                          (titulo, valor_alvo, valor_atual, prazo))
                st.success("Meta criada!")
                st.rerun()

    # Visualizar Metas
    df_metas = run_query("SELECT * FROM goals", fetch=True)
    if not df_metas.empty:
        for index, row in df_metas.iterrows():
            progresso = min(row['current_value'] / row['target_value'], 1.0)
            st.subheader(f"{row['title']} (Prazo: {row['deadline']})")
            st.progress(progresso)
            st.write(f"{format_currency(row['current_value'])} de {format_currency(row['target_value'])}")
            
            # Atualizar Meta Simples
            col1, col2 = st.columns([3, 1])
            with col2:
                novo_aporte = st.number_input(f"Aportar em {row['title']}", key=f"aporte_{row['id']}", min_value=0.0)
                if st.button("Adicionar", key=f"btn_{row['id']}"):
                    novo_total = row['current_value'] + novo_aporte
                    run_query("UPDATE goals SET current_value = ? WHERE id = ?", (novo_total, row['id']))
                    st.rerun()
            st.divider()

elif page == "Dívidas":
    st.title("💸 Controle de Dívidas")
    
    # Cadastro
    with st.expander("Cadastrar Dívida"):
        with st.form("form_divida"):
            desc = st.text_input("Descrição (ex: Cartão NuBank)")
            total = st.number_input("Valor Total da Dívida", min_value=0.01)
            pago = st.number_input("Valor Já Pago", min_value=0.0)
            vencimento = st.date_input("Próximo Vencimento")
            
            if st.form_submit_button("Salvar Dívida"):
                run_query("INSERT INTO debts (description, total_value, paid_value, due_date) VALUES (?, ?, ?, ?)", 
                          (desc, total, pago, vencimento))
                st.success("Dívida registrada.")
                st.rerun()
    
    # Visualização
    df_dividas = run_query("SELECT * FROM debts", fetch=True)
    if not df_dividas.empty:
        total_devido = df_dividas['total_value'].sum() - df_dividas['paid_value'].sum()
        st.metric("Total Restante a Pagar", format_currency(total_devido), delta_color="inverse")
        
        st.dataframe(df_dividas, use_container_width=True)
    else:
        st.info("Nenhuma dívida cadastrada. Parabéns!")

# --- Rodapé ---
st.sidebar.markdown("---")
st.sidebar.markdown("TE ORGANIZA ESCUMUNGADO(A)")
