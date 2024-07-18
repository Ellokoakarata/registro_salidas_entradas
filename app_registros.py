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

def convertir_a_hora_peru(timestamp):
    timezone_peru = pytz.timezone('America/Lima')
    return timestamp.astimezone(timezone_peru)

# Función para parsear la fecha y hora
def parse_datetime(datetime_str):
    try:
        return datetime.fromisoformat(datetime_str)
    except ValueError:
        # Si falla, intentamos con un formato específico
        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S.%f%z")

# Función para formatear la fecha y hora en formato de Perú
def formatear_fecha_hora_peru(datetime_str):
    fecha_hora = parse_datetime(datetime_str)
    peru_tz = pytz.timezone('America/Lima')
    fecha_hora_peru = fecha_hora.astimezone(peru_tz)
    return fecha_hora_peru.strftime("%d/%m/%Y %I:%M:%S %p")

# Función para verificar si ya se ha registrado una entrada o salida hoy
def verificar_registro_hoy(data, tipo):
    hoy = datetime.now(pytz.utc).date()
    for registro in data.get(tipo, []):
        fecha_registro = parse_datetime(registro['timestamp']).date()
        if fecha_registro == hoy:
            return True
    return False

# Función para calcular el tiempo trabajado
def calcular_tiempo_trabajado(data):
    total_tiempo = timedelta()
    entradas = sorted([parse_datetime(e["timestamp"]) for e in data.get("entradas", [])])
    salidas = sorted([parse_datetime(s["timestamp"]) for s in data.get("salidas", [])])

    # Asegurarse de que hay al menos una entrada y una salida
    if not entradas or not salidas:
        return total_tiempo

    # Si hay más entradas que salidas, añadir la hora actual como última salida
    if len(entradas) > len(salidas):
        salidas.append(datetime.now(pytz.utc))

    # Calcular el tiempo trabajado para cada par de entrada-salida
    for entrada, salida in zip(entradas, salidas):
        if salida > entrada:
            total_tiempo += salida - entrada

    return total_tiempo

# Función para mostrar el tiempo trabajado en horas, minutos y segundos
def mostrar_tiempo_trabajado(tiempo):
    if isinstance(tiempo, str):
        tiempo = timedelta(seconds=sum(float(x) * 60 ** i for i, x in enumerate(reversed(tiempo.split(':')))))
    total_seconds = int(tiempo.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours} horas, {minutes} minutos, {seconds} segundos"
    elif minutes > 0:
        return f"{minutes} minutos, {seconds} segundos"
    else:
        return f"{seconds} segundos"

# Función para crear un registro inicial para un nuevo trabajador
def crear_registro_inicial(trabajador_id):
    doc_ref = db.collection("registros").document(trabajador_id)
    doc_ref.set({
        "entradas": [],
        "salidas": [],
        "total_horas_trabajadas": "0:00:00"
    })

# Función para registrar entrada/salida
def registrar_evento(trabajador_id, tipo):
    doc_ref = db.collection("registros").document(trabajador_id)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
    else:
        data = {"entradas": [], "salidas": [], "total_horas_trabajadas": "0:00:00"}

    # Verificar si ya se ha registrado una entrada o salida hoy
    if verificar_registro_hoy(data, tipo):
        return False

    now = datetime.now(pytz.utc)
    evento = {
        "timestamp": now.isoformat(),
        "timestamp_peru": convertir_a_hora_peru(now).strftime("%Y-%m-%d %H:%M:%S")
    }

    if tipo == "entradas":
        data["entradas"].append(evento)
    elif tipo == "salidas":
        data["salidas"].append(evento)
    
    # Calcular el tiempo trabajado después de cada registro
    tiempo_trabajado = calcular_tiempo_trabajado(data)
    data["total_horas_trabajadas"] = str(tiempo_trabajado)

    doc_ref.set(data)
    return True

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
            st.write(f"- {formatear_fecha_hora_peru(entrada['timestamp'])}")

        st.write(f"Salidas para {trabajador_seleccionado}:")
        for salida in data.get("salidas", []):
            st.write(f"- {formatear_fecha_hora_peru(salida['timestamp'])}")

        # Calcular y mostrar el tiempo trabajado
        tiempo_trabajado = calcular_tiempo_trabajado(data)
        st.write(f"Total de horas trabajadas: {mostrar_tiempo_trabajado(tiempo_trabajado)}")

        # Campo de entrada para registrar eventos
        st.header("Registrar Entrada/Salida")

        if st.button("Registrar Entrada"):
            if registrar_evento(trabajador_id, "entradas"):
                st.success("Entrada registrada para el trabajador " + trabajador_seleccionado)
            else:
                st.warning("Ya se ha registrado una entrada hoy para este trabajador")

        if st.button("Registrar Salida"):
            if registrar_evento(trabajador_id, "salidas"):
                st.success("Salida registrada para el trabajador " + trabajador_seleccionado)
            else:
                st.warning("Ya se ha registrado una salida hoy para este trabajador")
    else:
        st.write("No se encontraron registros para el trabajador seleccionado.")
        if st.button("Crear registro inicial"):
            crear_registro_inicial(trabajador_id)
            st.success("Registro inicial creado. Por favor, seleccione el trabajador nuevamente.")
            st.rerun()

# Registrar un nuevo usuario si no está en la lista
st.header("Registrar Nuevo Trabajador")
nuevo_trabajador_nombre = st.text_input("Nombre del Nuevo Trabajador")

if nuevo_trabajador_nombre and st.button("Registrar Trabajador"):
    trabajador_id = str(uuid.uuid4())
    trabajadores_ref.document(trabajador_id).set({"nombre": nuevo_trabajador_nombre})
    crear_registro_inicial(trabajador_id)
    st.success("Trabajador registrado exitosamente y registro inicial creado")
    st.rerun()
