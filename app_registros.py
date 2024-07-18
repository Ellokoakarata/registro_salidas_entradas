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

    ahora = datetime.now(pytz.utc)

    # Verificar si ya hay un registro en las últimas 24 horas
    if tipo == "entrada":
        if data["entradas"] and (ahora - datetime.fromisoformat(data["entradas"][-1]["timestamp"])).total_seconds() < 86400:
            st.warning("Ya se registró una entrada en las últimas 24 horas.")
            return

    if tipo == "salida":
        if data["salidas"] and (ahora - datetime.fromisoformat(data["salidas"][-1]["timestamp"])).total_seconds() < 86400:
            st.warning("Ya se registró una salida en las últimas 24 horas.")
            return

    evento = {
        "timestamp": ahora.isoformat(),  # Hora actual en UTC
        "tipo": tipo
    }

    evento["timestamp_peru"] = convertir_a_hora_peru(ahora)  # Hora actual en Perú
    if tipo == "entrada":
        data["entradas"].append(evento)
    elif tipo == "salida":
        data["salidas"].append(evento)
        # Calcular el tiempo trabajado en esta sesión y sumarlo al total
        tiempo_trabajado_sesion = calcular_tiempo_trabajado(data)
        data["total_horas_trabajadas"] += tiempo_trabajado_sesion

    doc_ref.set(data)

# Función para calcular el tiempo trabajado
def calcular_tiempo_trabajado(data):
    total_tiempo = timedelta()

    entradas = [datetime.fromisoformat(e["timestamp"]) for e in data.get("entradas", [])]
    salidas = [datetime.fromisoformat(s["timestamp"]) for s in data.get("salidas", [])]

    for entrada, salida in zip(entradas, salidas):
        if salida > entrada:
            total_tiempo += salida - entrada

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

# Seleccionar trabajador
trabajador_seleccionado = st.selectbox("Selecciona un trabajador", [""] + list(trabajadores_dict.values()))

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
        tiempo_trabajado = calcular_tiempo_trabajado(data)
        st.write(f"Total de horas trabajadas: {mostrar_tiempo_trabajado(tiempo_trabajado)}")

        # Campo de entrada para registrar eventos
        st.header("Registrar Entrada/Salida")

        if st.button("Registrar Entrada"):
            registrar_evento(trabajador_id, "entrada")

        if st.button("Registrar Salida"):
            registrar_evento(trabajador_id, "salida")
    else:
        st.write("No se encontraron registros para el trabajador seleccionado.")

# Registrar un nuevo usuario si no está en la lista
st.header("Registrar Nuevo Trabajador")
nuevo_trabajador_nombre = st.text_input("Nombre del Nuevo Trabajador")

if nuevo_trabajador_nombre and st.button("Registrar Trabajador"):
    trabajador_id = str(uuid.uuid4())
    trabajadores_ref.document(trabajador_id).set({"nombre": nuevo_trabajador_nombre})
    
    # Crear un documento de registro inicial para el nuevo trabajador
    db.collection("registros").document(trabajador_id).set({"entradas": [], "salidas": [], "total_horas_trabajadas": timedelta()})

    st.success("Trabajador registrado exitosamente")
    
    # Seleccionar el nuevo trabajador automáticamente
    st.session_state.trabajador_seleccionado = nuevo_trabajador_nombre
    st.experimental_rerun()  # Recargar la interfaz

# Verificar si hay un trabajador seleccionado en la sesión
if 'trabajador_seleccionado' in st.session_state:
    trabajador_seleccionado = st.session_state.trabajador_seleccionado
