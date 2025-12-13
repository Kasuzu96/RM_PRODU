import os
import smtplib
import base64
import threading  # <--- NUEVA LIBRERÍA IMPORTANTE
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Cargar variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# 2. Configurar Supabase
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
# Validación básica
supabase: Client = create_client(url, key) if url and key else None

# 3. Configurar Gmail
MAIL_USER = os.getenv("MAIL_USERNAME")
MAIL_PASS = os.getenv("MAIL_PASSWORD")

# --- RUTAS ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/guardar', methods=['POST'])
def guardar_datos():
    try:
        data = request.json
        
        nombre = data.get('nombre')
        celular = data.get('celular')
        correo_usuario = data.get('correo')
        foto_base64 = data.get('foto')

        # --- A. Guardar en Supabase (Esto es rápido) ---
        if supabase:
            datos_usuario = {
                "nombre": nombre,
                "celular": celular,
                "correo": correo_usuario
            }
            supabase.table('usuarios').insert(datos_usuario).execute()
        
        # --- B. Procesar Imagen ---
        if "," in foto_base64:
            header, encoded = foto_base64.split(",", 1)
        else:
            encoded = foto_base64  
        binary_data = base64.b64decode(encoded)

        # --- C. Preparar el HTML del correo AQUÍ (antes del hilo) ---
        # Renderizamos el template aquí porque Flask no deja hacerlo fácil en hilos secundarios
        try:
            html_cliente = render_template('correo.html', nombre=nombre)
        except:
            html_cliente = f"<h1>Hola {nombre}</h1><p>Gracias por tu registro.</p>"

        # --- D. Enviar Correos en SEGUNDO PLANO (Threading) ---
        # Creamos un "trabajador fantasma" que hará el envío sin bloquear al usuario
        hilo = threading.Thread(
            target=tarea_enviar_correos, 
            args=(nombre, celular, correo_usuario, binary_data, html_cliente)
        )
        hilo.start() # ¡Arranca el hilo y sigue de largo!

        # Respondemos INMEDIATAMENTE al usuario "Todo ok", sin esperar a Gmail
        return jsonify({"status": "ok", "mensaje": "Guardado. Correos enviándose en segundo plano."})

    except Exception as e:
        print(f"Error en endpoint: {e}")
        return jsonify({"status": "error", "mensaje": str(e)}), 500

# --- FUNCION QUE CORRE EN SEGUNDO PLANO ---
def tarea_enviar_correos(nombre, celular, correo_usuario, binary_data, html_cliente):
    """Esta función se ejecuta en paralelo y si tarda, no afecta al usuario"""
    try:
        # 1. Enviar al Admin
        enviar_correo_admin(nombre, celular, correo_usuario, binary_data)
        # 2. Enviar al Cliente
        enviar_correo_cliente_con_html(nombre, correo_usuario, binary_data, html_cliente)
        print("--- Correos enviados con éxito en segundo plano ---")
    except Exception as e:
        print(f"ERROR ENVIANDO CORREOS EN HILO: {e}")

# --- FUNCIONES DE CORREO MODIFICADAS (Puerto 465 SSL) ---

def enviar_correo_admin(nombre, celular, correo_cliente, foto_bytes):
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = MAIL_USER
    msg['Subject'] = f"🔔 Nuevo Lead: {nombre}"

    html = f"""
    <h3>Nuevo Registro</h3>
    <ul>
        <li><b>Nombre:</b> {nombre}</li>
        <li><b>Celular:</b> {celular}</li>
        <li><b>Correo:</b> {correo_cliente}</li>
    </ul>
    """
    msg.attach(MIMEText(html, 'html'))
    image = MIMEImage(foto_bytes, name=f"registro_{nombre}.png")
    msg.attach(image)
    
    enviar_smtp_seguro(msg)

def enviar_correo_cliente_con_html(nombre, destinatario, foto_bytes, html_content):
    msg = MIMEMultipart()
    msg['From'] = MAIL_USER
    msg['To'] = destinatario 
    msg['Subject'] = f"¡Hola {nombre}, aquí tienes tu foto! 📸"

    msg.attach(MIMEText(html_content, 'html'))
    image = MIMEImage(foto_bytes, name="tu_foto.png")
    msg.attach(image)

    enviar_smtp_seguro(msg)

def enviar_smtp_seguro(mensaje):
    """
    Usamos SMTP_SSL y puerto 465.
    Es más directo y evita problemas de handshake que causan timeouts.
    """
    try:
        # CAMBIO CLAVE: SMTP_SSL en puerto 465 (No requiere starttls)
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_USER, MAIL_PASS)
            server.send_message(mensaje)
    except Exception as e:
        print(f"Error conectando a Gmail: {e}")