import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
import uuid

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

# Función para convertir la hora al huso horario de Perú
def convertir_a_hora_peru(timestamp):
    timezone_peru = pytz.timezone('America/Lima')
    return timestamp.astimezone(timezone_peru)

# Función para registrar entrada/salida
def registrar_evento(trabajador_nombre, tipo):
    # Verificar si el trabajador ya tiene un ID asignado
    trabajadores_ref = db.collection("trabajadores")
    query = trabajadores_ref.where("nombre", "==", trabajador_nombre).limit(1)
    results = query.stream()

    trabajador_id = None
    for doc in results:
        trabajador_id = doc.id
        break

    # Si el trabajador no tiene un ID, crear uno nuevo
    if not trabajador_id:
        trabajador_id = str(uuid.uuid4())
        trabajadores_ref.document(trabajador_id).set({"nombre": trabajador_nombre})

    # Registrar el evento de entrada/salida
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
    else:
        data = {"nombre": trabajador_nombre, "entradas": [], "salidas": []}

    evento = {
        "timestamp": datetime.now(pytz.utc).isoformat(),  # Hora actual en UTC
        "tipo": tipo
    }

    if tipo == "entrada":
        evento["timestamp_peru"] = convertir_a_hora_peru(datetime.now(pytz.utc))  # Hora actual en Perú
        data["entradas"].append(evento)
    elif tipo == "salida":
        evento["timestamp_peru"] = convertir_a_hora_peru(datetime.now(pytz.utc))  # Hora actual en Perú
        data["salidas"].append(evento)

    doc_ref.set(data)

# Función para calcular el tiempo trabajado
def calcular_tiempo_trabajado(data):
    total_tiempo = timedelta()

    entradas = data.get("entradas", [])
    salidas = data.get("salidas", [])

    for entrada in entradas:
        timestamp_entrada = datetime.fromisoformat(entrada["timestamp"])
        for salida in salidas:
            timestamp_salida = datetime.fromisoformat(salida["timestamp"])
            if timestamp_salida > timestamp_entrada:
                total_tiempo += timestamp_salida - timestamp_entrada
                break

    return total_tiempo

# Función para mostrar el tiempo trabajado en horas, minutos y segundos
def mostrar_tiempo_trabajado(tiempo):
    total_seconds = int(tiempo.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours} horas, {minutes} minutos, {seconds} segundos"
    elif minutes > 0:
        return f"{minutes} minutos, {seconds} segundos"
    else:
        return f"{seconds} segundos"

# Interfaz de usuario de Streamlit
st.title("Registro de Entradas y Salidas de Trabajadores-Netsat srl (Aplicación de prueba)")

trabajador_nombre = st.text_input("Nombre del Trabajador")

if trabajador_nombre:
    if st.button("Registrar Entrada"):
        registrar_evento(trabajador_nombre, "entrada")
        st.success("Entrada registrada para el trabajador " + trabajador_nombre)

    if st.button("Registrar Salida"):
        registrar_evento(trabajador_nombre, "salida")
        st.success("Salida registrada para el trabajador " + trabajador_nombre)

    # Mostrar registros del trabajador
    trabajadores_ref = db.collection("trabajadores")
    query = trabajadores_ref.where("nombre", "==", trabajador_nombre).limit(1)
    results = query.stream()

    trabajador_id = None
    for doc in results:
        trabajador_id = doc.id
        break

    if trabajador_id:
        doc_ref = db.collection("registros").document(trabajador_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            st.write("Entradas:")
            for entrada in data.get("entradas", []):
                st.write(f"- {convertir_a_hora_peru(datetime.fromisoformat(entrada['timestamp']))}")

            st.write("Salidas:")
            for salida in data.get("salidas", []):
                st.write(f"- {convertir_a_hora_peru(datetime.fromisoformat(salida['timestamp']))}")

            # Calcular y mostrar el tiempo trabajado
            tiempo_trabajado = calcular_tiempo_trabajado(data)
            st.write(f"Total de horas trabajadas: {mostrar_tiempo_trabajado(tiempo_trabajado)}")

        else:
            st.write("No se encontraron registros para el trabajador " + trabajador_nombre)
    else:
        st.write("No se encontraron registros para el trabajador " + trabajador_nombre)

