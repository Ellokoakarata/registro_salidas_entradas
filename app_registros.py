import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
from datetime import datetime

# Cargar credenciales desde streamlit secrets
firebase_credentials = json.loads(st.secrets["firebase_credentials"])
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred)

# Inicializar Firestore
db = firestore.client()

# Función para registrar entrada/salida
def registrar_evento(trabajador_id, tipo):
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
    else:
        data = {"entradas": [], "salidas": []}

    evento = {
        "timestamp": datetime.now().isoformat(),
        "tipo": tipo
    }

    if tipo == "entrada":
        data["entradas"].append(evento)
    elif tipo == "salida":
        data["salidas"].append(evento)

    doc_ref.set(data)

# Interfaz de usuario de Streamlit
st.title("Registro de Entradas y Salidas de Trabajadores")

trabajador_id = st.text_input("ID del Trabajador")

if trabajador_id:
    if st.button("Registrar Entrada"):
        registrar_evento(trabajador_id, "entrada")
        st.success("Entrada registrada para el trabajador " + trabajador_id)

    if st.button("Registrar Salida"):
        registrar_evento(trabajador_id, "salida")
        st.success("Salida registrada para el trabajador " + trabajador_id)

    # Mostrar registros del trabajador
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        st.write("Entradas:", data.get("entradas", []))
        st.write("Salidas:", data.get("salidas", []))
    else:
        st.write("No se encontraron registros para el trabajador " + trabajador_id)
