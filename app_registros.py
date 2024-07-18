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
def registrar_evento(trabajador_id, tipo):
    # Registrar el evento de entrada/salida
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
    else:
        data = {"entradas": [], "salidas": [], "total_horas_trabajadas": timedelta()}

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
        # Calcular el tiempo trabajado en esta sesión y sumarlo al total
        tiempo_trabajado_sesion = calcular_tiempo_trabajado(data)
        data["total_horas_trabajadas"] += tiempo_trabajado_sesion

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
                salidas.remove(salida)
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
st.title("Registro de Entradas y Salidas de Trabajadores - Netsat SRL (Aplicación de prueba)")

# Mostrar tabla con todos los trabajadores registrados
st.header("Lista de Trabajadores Registrados")
trabajadores_ref = db.collection("trabajadores")
trabajadores = trabajadores_ref.stream()

trabajadores_dict = {doc.id: doc.to_dict()["nombre"] for doc in trabajadores}

if trabajadores_dict:
    trabajador_seleccionado = st.selectbox("Selecciona un trabajador", [""] + list(trabajadores_dict.values()))
else:
    trabajador_seleccionado = ""

if trabajador_seleccionado:
    trabajador_id = next(key for key, value in trabajadores_dict.items() if value == trabajador_seleccionado)
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        st.write(f"Entradas para {trabajador_seleccionado}:")
        for entrada in data.get("entradas", []):
            st.write(f"- {convertir_a_hora_peru(datetime.fromisoformat(entrada['timestamp']))}")

        st.write(f"Salidas para {trabajador_seleccionado}:")
        for salida in data.get("salidas", []):
            st.write(f"- {convertir_a_hora_peru(datetime.fromisoformat(salida['timestamp']))}")

        # Calcular y mostrar el tiempo trabajado
        tiempo_trabajado = data.get("total_horas_trabajadas", timedelta())
        st.write(f"Total de horas trabajadas: {mostrar_tiempo_trabajado(tiempo_trabajado)}")

        # Campo de entrada para registrar eventos
        st.header("Registrar Entrada/Salida")

        if st.button("Registrar Entrada"):
            registrar_evento(trabajador_id, "entrada")
            st.success("Entrada registrada para el trabajador " + trabajador_seleccionado)

        if st.button("Registrar Salida"):
            registrar_evento(trabajador_id, "salida")
            st.success("Salida registrada para el trabajador " + trabajador_seleccionado)
    else:
        st.write("No se encontraron registros para el trabajador seleccionado.")

# Registrar un nuevo usuario si no está en la lista
st.header("Registrar Nuevo Trabajador")
nuevo_trabajador_nombre = st.text_input("Nombre del Nuevo Trabajador")

if nuevo_trabajador_nombre and st.button("Registrar Trabajador"):
    trabajador_id = str(uuid.uuid4())
    trabajadores_ref.document(trabajador_id).set({"nombre": nuevo_trabajador_nombre})
    st.success("Trabajador registrado exitosamente")
    st.experimental_rerun()



