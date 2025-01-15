import os
import json
import streamlit as st
import mysql.connector
import pandas as pd
from dotenv import load_dotenv

# LangChain / OpenAI importları
from langchain.chat_models import ChatOpenAI
from langchain.prompts.chat import ChatPromptTemplate
from langchain.schema import AIMessage, HumanMessage

# 1. OpenAI API KEY Yükle (.env'den)
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    st.error("OpenAI API key missing! Please check your .env file.")
    st.stop()

# 2. MySQL Bağlantı Bilgilerini JSON'dan Oku
def load_db_config(path="db_config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

db_config = load_db_config("db_config.json")

# 3. ChatOpenAI Model Ayarı
llm = ChatOpenAI(
    openai_api_key=api_key,
    model="gpt-4",  # veya "gpt-3.5-turbo"
    temperature=0
)

# 4. Streamlit Sayfa Ayarları
st.set_page_config(page_title="Assistflow.ai Chat with MySQL (JSON)", page_icon=":speech_balloon:")
st.title("Assistflow.ai Chat with MySQL (JSON-based Config)")

# 5. MySQL'e Bağlanma
try:
    connection = mysql.connector.connect(
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        port=db_config.get("port", 3306)
    )
    st.session_state.db = connection
    st.success("Connected to the database!")
except Exception as e:
    st.error(f"Connection failed: {str(e)}")
    st.stop()

# 6. Yardımcı Fonksiyonlar
def get_schema_info():
    """
    Retrieves table and column information from the connected MySQL database.
    """
    try:
        cursor = st.session_state.db.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        schema_info = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DESCRIBE {table_name}")
            columns = [col[0] for col in cursor.fetchall()]
            schema_info.append(f"{table_name} ({', '.join(columns)})")
        cursor.close()
        return "Tables: " + ", ".join(schema_info)
    except Exception as e:
        return str(e)

def generate_sql(schema_info, query):
    """
    Uses an LLM (ChatOpenAI) to convert a natural language question into an SQL query.
    """
    template_text = """
    You are an expert in MariaDB SQL. Convert the following natural language
    question into a valid SQL query. The database schema is:
    {schema_info}

    Question: {user_query}

    Return ONLY the SQL query, with no extra text or explanation.
    """

    prompt = ChatPromptTemplate.from_template(template_text)
    messages = prompt.format_messages(
        schema_info=schema_info,
        user_query=query
    )
    response = llm(messages)

    # Temizleme (backtick vb. kaldırma)
    sql_query = response.content.strip().strip("`")
    return sql_query

def execute_query(query):
    """
    Executes the given SQL query against the MySQL database.
    Returns (results, columns) or (error_message, []) if there's an error.
    """
    try:
        cursor = st.session_state.db.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        return results, columns
    except Exception as e:
        return str(e), []

# 7. Sohbet Geçmişi
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello! I'm an Assistflow.ai SQL assistant. Ask me anything about your database.")
    ]

# Mevcut mesajları göster
for msg in st.session_state.chat_history:
    if isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)
    else:
        with st.chat_message("user"):
            st.markdown(msg.content)

# 8. Kullanıcıdan Metin Girişi
user_query = st.chat_input("Ask your question here (e.g. 'How many rows in the users table?') ...")

if user_query:
    # 1. Kullanıcı mesajını ekle
    st.session_state.chat_history.append(HumanMessage(content=user_query))
    with st.chat_message("user"):
        st.markdown(user_query)

    # 2. Şema Bilgisi Al
    schema_info = get_schema_info()

    # 3. Doğal Dilden SQL'e Dönüştür
    sql_query = generate_sql(schema_info, user_query)

    # 4. SQL'i Çalıştır
    result, columns = execute_query(sql_query)

    # 5. Yanıtı Göster
    if isinstance(result, str):
        # Hata
        error_message = f"**Generated SQL**: `{sql_query}`\n\n**Error**: {result}"
        st.session_state.chat_history.append(AIMessage(content=error_message))
        with st.chat_message("assistant"):
            st.error(error_message)
    else:
        # Başarılı Sorgu
        if len(result) > 0:
            df = pd.DataFrame(result, columns=columns)
            success_message = f"**Generated SQL**: `{sql_query}`\n\n**Results**:"
            st.session_state.chat_history.append(AIMessage(content=success_message))
            with st.chat_message("assistant"):
                st.markdown(success_message)
                st.dataframe(df)
        else:
            # Kayıt yok
            success_message = f"**Generated SQL**: `{sql_query}`\n\nNo results found."
            st.session_state.chat_history.append(AIMessage(content=success_message))
            with st.chat_message("assistant"):
                st.markdown(success_message)
