import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Acceder a las credenciales de Firebase almacenadas como secreto
firebase_secrets = st.secrets["firebase"]

# Crear un objeto de credenciales de Firebase con los secretos
cred = credentials.Certificate({
    "type": firebase_secrets["type"],
    "project_id": firebase_secrets["project_id"],
    "private_key_id": firebase_secrets["private_key_id"],
    "private_key": firebase_secrets["private_key"],
    "client_email": firebase_secrets["client_email"],
    "client_id": firebase_secrets["client_id"],
    "auth_uri": firebase_secrets["auth_uri"],
    "token_uri": firebase_secrets["token_uri"],
    "auth_provider_x509_cert_url": firebase_secrets["auth_provider_x509_cert_url"],
    "client_x509_cert_url": firebase_secrets["client_x509_cert_url"]
})

# Inicializar la aplicación de Firebase con las credenciales
if not firebase_admin._apps:
    default_app = firebase_admin.initialize_app(cred)

# Acceder a la base de datos de Firestore
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

