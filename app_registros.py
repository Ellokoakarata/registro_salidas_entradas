import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import io
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Border, Side

# ---------------------------
# INICIALIZACIÓN DE FIREBASE
# ---------------------------
import firebase_admin
from firebase_admin import credentials, firestore, storage

# Se asume que en st.secrets["firebase"] tienes el JSON de credenciales, incluyendo "storageBucket"
firebase_secrets = st.secrets["firebase"]

if not firebase_admin._apps:
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
    firebase_admin.initialize_app(cred, {
        'storageBucket': firebase_secrets["storageBucket"]
    })

db = firestore.client()
bucket = storage.bucket()

# ---------------------------
# CONFIGURACIÓN DE HORARIOS
# ---------------------------
# Horarios permitidos (hora local de Perú)
ENTRY_DEADLINE = 11    # Se permite marcar entrada solo hasta las 11:00 AM
EXIT_START = 18        # Se permite marcar salida solo hasta las 6:00 PM

# ---------------------------
# FUNCIONES AUXILIARES
# ---------------------------
def get_week_filename():
    """Genera el nombre del archivo según el año y la semana actual."""
    now = datetime.now()
    year, week, _ = now.isocalendar()
    return f"registro_{year}_W{week}.xlsx"

def utc_to_lima(utc_dt):
    """Convierte un datetime en UTC a la hora de Lima (America/Lima)."""
    lima_tz = pytz.timezone("America/Lima")
    return utc_dt.astimezone(lima_tz)

def format_datetime(dt):
    """Formatea el datetime a cadena, usando la hora de Lima."""
    return utc_to_lima(dt).strftime("%d/%m/%Y %I:%M:%S %p")

def parse_timedelta(td_str):
    """Convierte una cadena tipo 'H:MM:SS' a un objeto timedelta."""
    try:
        h, m, s = map(int, td_str.split(':'))
        return timedelta(hours=h, minutes=m, seconds=s)
    except Exception:
        return timedelta()

def create_summary_df(df):
    """Crea un DataFrame resumen con el total de horas trabajadas por cada trabajador."""
    summary = {}
    for name in df["Nombre"].unique():
        valid = df[(df["Nombre"] == name) & (df["Horas Trabajadas"].notna())]
        total = timedelta()
        for _, row in valid.iterrows():
            total += parse_timedelta(row["Horas Trabajadas"])
        summary[name] = str(total)
    summary_df = pd.DataFrame(list(summary.items()), columns=["Nombre", "Total Horas Trabajadas"])
    summary_df = summary_df.sort_values("Nombre")
    return summary_df

def save_week_data_and_upload(df, filename):
    """
    Guarda el DataFrame en un archivo Excel con dos hojas: 'Registros' y 'Resumen',
    ajusta las columnas, añade bordes a las celdas y sube el archivo directamente a Firebase Storage.
    Se utiliza un buffer en memoria, sin escribir en disco.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Registros', index=False)
        ws = writer.sheets['Registros']
        # Autoajuste de columnas para 'Registros'
        for col_cells in ws.columns:
            max_length = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            ws.column_dimensions[col_letter].width = max_length + 2

        summary_df = create_summary_df(df)
        summary_df.to_excel(writer, sheet_name='Resumen', index=False)
        ws_summary = writer.sheets['Resumen']
        # Autoajuste de columnas para 'Resumen'
        for col_cells in ws_summary.columns:
            max_length = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            ws_summary.column_dimensions[col_letter].width = max_length + 2

        # Agregar bordes a todas las celdas en ambas hojas
        thin_border = Border(
            left=Side(style="thin"), 
            right=Side(style="thin"), 
            top=Side(style="thin"), 
            bottom=Side(style="thin")
        )
        for ws in [writer.sheets['Registros'], writer.sheets['Resumen']]:
            for row in ws.iter_rows():
                for cell in row:
                    cell.border = thin_border

    output.seek(0)
    blob = bucket.blob(filename)
    blob.upload_from_string(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.write(f"Archivo {filename} subido a Firebase Storage.")

def load_week_data(filename):
    """
    Intenta cargar el DataFrame de la hoja 'Registros' desde Firebase Storage.
    Si no existe, se crea uno nuevo y se sube.
    """
    blob = bucket.blob(filename)
    if blob.exists():
        data = blob.download_as_bytes()
        df = pd.read_excel(io.BytesIO(data), sheet_name='Registros')
        return df
    else:
        df = pd.DataFrame(columns=["Nombre", "Fecha", "Entrada", "Salida", "Horas Trabajadas"])
        save_week_data_and_upload(df, filename)
        st.write(f"Nuevo archivo para la semana creado: {filename}")
        return df

def update_firestore(worker, data):
    """
    Actualiza Firestore en la colección 'registros'.
    Cada trabajador tendrá un documento cuyo ID es su nombre, y se guardan los registros.
    """
    doc_ref = db.collection("registros").document(worker)
    doc_ref.set(data)

def register_event(worker, event_type):
    """
    Registra una entrada o salida para un trabajador.
    Se actualiza Firestore y se actualiza el archivo Excel en Firebase Storage.
    Se convierte la hora de UTC a la hora de Lima.
    Se validan horarios:
      - Entrada: solo se permite hasta las 11:00 AM.
      - Salida: solo se permite hasta las 6:00 PM.
    Si no se marcó entrada, no se permite marcar salida.
    """
    filename = get_week_filename()
    df = load_week_data(filename)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    now_utc = datetime.now(pytz.utc)
    local_now = utc_to_lima(now_utc)
    now_str = format_datetime(now_utc)
    
    # Validar horario según tipo de evento
    if event_type == "entrada":
        if local_now.hour >= ENTRY_DEADLINE:
            return False, "Fuera del horario permitido para marcar entrada (hasta las 11:00 AM)."
    elif event_type == "salida":
        # Se permite salida solo hasta las 6:00 PM
        if local_now.hour > EXIT_START or (local_now.hour == EXIT_START and local_now.minute > 0):
            return False, "Fuera del horario permitido para marcar salida (hasta las 6:00 PM)."
    
    record = df[(df["Nombre"] == worker) & (df["Fecha"] == today_str)]
    
    if event_type == "entrada":
        if not record.empty and pd.notna(record.iloc[0]["Entrada"]):
            return False, "Ya se ha registrado una entrada hoy para este trabajador."
        if record.empty:
            new_row = {
                "Nombre": worker,
                "Fecha": today_str,
                "Entrada": now_str,
                "Salida": "No marcó salida",
                "Horas Trabajadas": "No marcó salida"
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            idx = record.index[0]
            df.at[idx, "Entrada"] = now_str
        save_week_data_and_upload(df, filename)
        update_firestore(worker, {"Fecha": today_str, "Evento": "entrada", "Timestamp": now_str})
        return True, f"Entrada registrada para {worker} a las {now_str}"
    
    elif event_type == "salida":
        if record.empty or pd.isna(record.iloc[0]["Entrada"]):
            return False, "No se ha registrado entrada hoy para este trabajador."
        if pd.notna(record.iloc[0]["Salida"]) and record.iloc[0]["Salida"] != "No marcó salida":
            return False, "Ya se ha registrado una salida hoy para este trabajador."
        
        idx = record.index[0]
        df.at[idx, "Salida"] = now_str
        try:
            entry_time = datetime.strptime(df.at[idx, "Entrada"], "%d/%m/%Y %I:%M:%S %p")
            exit_time = datetime.strptime(now_str, "%d/%m/%Y %I:%M:%S %p")
            worked = exit_time - entry_time
            df.at[idx, "Horas Trabajadas"] = str(worked)
        except Exception as e:
            return False, f"Error al calcular las horas trabajadas: {e}"
        save_week_data_and_upload(df, filename)
        update_firestore(worker, {"Fecha": today_str, "Evento": "salida", "Timestamp": now_str})
        return True, f"Salida registrada para {worker} a las {now_str}"
    
    return False, "Evento desconocido."

def get_worker_week_hours(worker):
    """Obtiene la suma de las horas trabajadas en la semana para un trabajador."""
    filename = get_week_filename()
    df = load_week_data(filename)
    records = df[(df["Nombre"] == worker) & (df["Horas Trabajadas"].notna())]
    total = timedelta()
    for _, row in records.iterrows():
        total += parse_timedelta(row["Horas Trabajadas"])
    return total

# ---------------------------
# INTERFAZ DE USUARIO CON STREAMLIT
# ---------------------------

# Primero, se define la lista de usuarios (nombres)
user_list = ["Hector Ruiz", "Ricardo Ruiz", "Nelida Ruiz", "Ricardo Adrian Ruiz", "Paula Lecaros"]

# Se obtienen las contraseñas desde st.secrets (almacenadas en la sección [user_passwords])
# Estas contraseñas no se muestran en la interfaz.
user_passwords = st.secrets["user_passwords"]

st.title("Registro de Entradas y Salidas (CLOUD: Firestore + Firebase Storage)")

with st.expander("Selecciona al Trabajador"):
    worker = st.selectbox("Elige tu nombre:", [""] + user_list)

if worker:
    # Solicitar contraseña sin mostrarla
    password_input = st.text_input("Ingrese su contraseña:", type="password")
    
    if password_input:
        if password_input == user_passwords.get(worker, ""):
            # Si es admin, mostrar etiqueta
            if worker == "Ricardo Adrian Ruiz":
                st.info("Bienvenido, ADMIN.")
            else:
                st.info(f"Bienvenido, {worker}.")
            
            st.header(f"Registro para: {worker}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Registrar Entrada"):
                    success, msg = register_event(worker, "entrada")
                    if success:
                        st.success(msg)
                    else:
                        st.warning(msg)
            with col2:
                if st.button("Registrar Salida"):
                    success, msg = register_event(worker, "salida")
                    if success:
                        st.success(msg)
                    else:
                        st.warning(msg)
            
            total_hours = get_worker_week_hours(worker)
            st.write("Total de horas trabajadas esta semana:", str(total_hours))
            
            # Solo el admin puede ver el resumen de todos los usuarios
            if worker == "Ricardo Adrian Ruiz":
                if st.button("Mostrar resumen de horas por trabajador"):
                    filename = get_week_filename()
                    df = load_week_data(filename)
                    resumen = create_summary_df(df)
                    st.dataframe(resumen)
            else:
                # Los demás pueden ver únicamente sus registros
                if st.button("Mostrar mis registros semanales"):
                    filename = get_week_filename()
                    df = load_week_data(filename)
                    worker_records = df[df["Nombre"] == worker]
                    st.dataframe(worker_records)
        else:
            st.error("Contraseña incorrecta. Intente nuevamente.")
