import os
import base64
import threading
import sys
import requests # <--- Usaremos requests para hablar con Brevo
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

print("--- ARRANQUE V9: API BREVO (HTTPS) ---", file=sys.stdout)

# 1. Configuración Supabase
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key) if url and key else None

# 2. Configuración Brevo
BREVO_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_NAME = os.getenv("SENDER_NAME", "Fiesta App")

# 3. Configuración Cloudinary
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET"),
  secure = True
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test-email')
def test_email():
    # ... (Existing test_email code - no major changes needed unless we want to test video link too) ...
    print(">>> Iniciando Test Brevo...", file=sys.stdout)
    try:
        if not BREVO_KEY or not SENDER_EMAIL:
            return "ERROR: Faltan credenciales BREVO en Render."

        # Enviar prueba simple
        respuesta = enviar_brevo(
            SENDER_EMAIL, 
            "Prueba de Conexión Brevo 🚀",
            "<h1>¡Funciona!</h1><p>Si lees esto, Render ya no bloquea tus correos.</p>",
            None 
        )
        
        return f"<h1>¡RESULTADO!</h1> <pre>{json.dumps(respuesta, indent=2)}</pre>"
    
    except Exception as e:
        return f"<h1>FALLÓ ❌</h1> <pre>{str(e)}</pre>"

@app.route('/guardar', methods=['POST'])
def guardar_datos():
    try:
        # Check content type to decide how to parse
        if request.content_type.startswith('multipart/form-data'):
             # Handle Multipart (Video or Photo as File)
            nombre = request.form.get('nombre')
            celular = request.form.get('celular')
            correo = request.form.get('correo')
            
            video_file = request.files.get('video')
            foto_file = request.files.get('foto') # Expecting file for photo too in this mode, or base64 field?
            foto_base64 = request.form.get('foto_base64') # Backwards compatibility / Hybrid

            video_url = None
            encoded_img = None
            
            # --- VIDEO HANDLER ---
            if video_file:
                print(">>> Subiendo video a Cloudinary...", file=sys.stdout)
                upload_result = cloudinary.uploader.upload(video_file, resource_type="video", folder="fiesta_app")
                video_url = upload_result.get("secure_url")
                print(f"Video URL: {video_url}", file=sys.stdout)

            # --- PHOTO HANDLER ---
            # If we received a file for photo (future proofing), upload it or convert to base64? 
            # For now, let's stick to the existing base64 logic if provided, OR just skip photo attachment if it's a video-only entry?
            # User said "add video option", implies either/or.
            
            if foto_base64:
                 # Limpiar base64
                encoded_img = foto_base64
                if "," in foto_base64:
                    header, encoded_img = foto_base64.split(",", 1)
        
        else:
             # Handle JSON (Legacy Photo Mode)
            data = request.json
            nombre = data.get('nombre')
            celular = data.get('celular')
            correo = data.get('correo')
            foto_base64 = data.get('foto')
            video_url = None
            
            encoded_img = None
            if foto_base64:
                 encoded_img = foto_base64
                 if "," in foto_base64:
                    header, encoded_img = foto_base64.split(",", 1)


        # Supabase
        if supabase:
            try:
                supabase.table('usuarios').insert({
                    "nombre": nombre, "celular": celular, "correo": correo, "video_url": video_url
                }).execute()
            except Exception as e:
                print(f"Error Supabase: {e}", file=sys.stdout)

        # HTML
        try:
            html_cliente = render_template('correo.html', nombre=nombre, video_url=video_url) # Pass video_url to template
        except:
            # Fallback inline HTML
            html_cliente = f"<h1>Hola {nombre}</h1><p>Aquí está tu recuerdo.</p>"
            if video_url:
                 html_cliente += f"<p><a href='{video_url}' style='padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;'>🎬 Ver Video</a></p>"

        # Hilo Email
        hilo = threading.Thread(
            target=tarea_enviar_brevo, 
            args=(nombre, celular, correo, encoded_img, html_cliente, video_url)
        )
        hilo.start()

        # Hilo Limpieza (gestión de almacenamiento)
        hilo_limpieza = threading.Thread(target=gestionar_almacenamiento)
        hilo_limpieza.start()

        return jsonify({"status": "ok", "mensaje": "Enviando con Brevo..."})

    except Exception as e:
        print(f"ERROR GENERAL: {e}", file=sys.stdout)
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "mensaje": str(e)}), 500

def tarea_enviar_brevo(nombre, celular, correo_cliente, foto_b64, html_cliente, video_url=None):
    try:
        # 1. Al Admin
        admin_html = f"<p>Nombre: {nombre}<br>Cel: {celular}<br>Email: {correo_cliente}</p>"
        if video_url:
            admin_html += f"<p><strong>VIDEO:</strong> <a href='{video_url}'>{video_url}</a></p>"
        
        enviar_brevo(
            SENDER_EMAIL,
            f"🔔 Nuevo Lead: {nombre} {'(VIDEO)' if video_url else ''}",
            admin_html,
            foto_b64
        )
        
        # 2. Al Cliente
        enviar_brevo(
            correo_cliente,
            f"¡Hola {nombre}, tu recuerdo de la fiesta! {'🎬' if video_url else '📸'}",
            html_cliente,
            foto_b64
        )
        print(f"--- Brevo: Correos enviados para {nombre} ---", file=sys.stdout)

    except Exception as e:
        print(f"!!! Error Brevo: {e}", file=sys.stdout)

def enviar_brevo(destinatario, asunto, html_content, foto_b64):
    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": BREVO_KEY,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": destinatario}],
        "subject": asunto,
        "htmlContent": html_content
    }

    # Adjuntar foto SI existe
    if foto_b64:
        payload["attachment"] = [
            {
                "content": foto_b64,
                "name": "recuerdo_fiesta.png"
            }
        ]

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Status Brevo ({destinatario}): {response.status_code}", file=sys.stdout)
        # print(response.text, file=sys.stdout) # Debug si falla
        return response.json()
    except Exception as e:
        print(f"Error Request Brevo: {e}", file=sys.stdout)
        raise e

def gestionar_almacenamiento():
    # Configuración: 10 GB límite, borrar 5 GB
    LIMIT_BYTES = 10 * 1024 * 1024 * 1024 
    TARGET_DELETE_BYTES = 5 * 1024 * 1024 * 1024 

    print("--- 🧹 Verificando Almacenamiento Cloudinary (Carpeta fiesta_app) ---", file=sys.stdout)
    
    try:
        resources = []
        next_cursor = None
        total_size = 0
        
        # 1. Listar TODOS los videos
        while True:
            res = cloudinary.api.resources(
                type="upload",
                resource_type="video", 
                prefix="fiesta_app/", 
                max_results=500,
                direction="asc", # Del más viejo al más nuevo
                next_cursor=next_cursor
            )
            items = res.get('resources', [])
            resources.extend(items)
            
            for item in items:
                total_size += item.get('bytes', 0)
                
            if 'next_cursor' in res:
                next_cursor = res['next_cursor']
            else:
                break
        
        gb_used = total_size / (1024 * 1024 * 1024)
        print(f"📊 Uso actual: {gb_used:.2f} GB (Límite: 10.00 GB)", file=sys.stdout)

        # 2. Verificar si excede
        if total_size > LIMIT_BYTES:
            print(f"⚠️ Límite excedido. Iniciando limpieza de ~5 GB...", file=sys.stdout)
            
            deleted_accumulated = 0
            ids_to_delete = []
            
            for item in resources:
                if deleted_accumulated >= TARGET_DELETE_BYTES:
                    break
                
                ids_to_delete.append(item['public_id'])
                deleted_accumulated += item.get('bytes', 0)
            
            # 3. Borrar
            if ids_to_delete:
                # Borrar en lotes de 50
                chunk_size = 50
                for i in range(0, len(ids_to_delete), chunk_size):
                    batch = ids_to_delete[i:i + chunk_size]
                    cloudinary.api.delete_resources(batch, resource_type="video")
                    print(f"🗑️ Borrados {len(batch)} videos...", file=sys.stdout)
                
                gb_freed = deleted_accumulated / (1024 * 1024 * 1024)
                print(f"✅ Limpieza completada. Liberados: {gb_freed:.2f} GB", file=sys.stdout)
        else:
            print("✅ Almacenamiento bajo control.", file=sys.stdout)

    except Exception as e:
        print(f"❌ Error en Auto-Limpieza: {e}", file=sys.stdout)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)