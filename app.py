import os
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from groq import Groq
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.getenv("SECRET_KEY", "cle-secrete-par-defaut")

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            role TEXT,
            content TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("La clé GROQ_API_KEY est manquante.")
    return Groq(api_key=api_key)

SYSTEM_PROMPT = """
Tu es un Mentor Business direct, efficace et concis. 

Règles de formatage strictes et absolues :
1. N'utilise jamais d'astérisques (*).
2. Utilise des points (.) pour structurer ou introduire tes titres.
3. Sous chaque titre, mets 3 tirets (-) grand maximum.
4. Va droit au but, évite les longs discours superflus.
"""

@app.route('/')
def home():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()
    session['user'] = {
        "id": "google_" + str(user_info.get('sub')),
        "name": user_info.get('name'),
        "email": user_info.get('email')
    }
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name', 'Utilisateur')
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    hashed_password = generate_password_hash(password)
    user_id = "email_" + email

    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, name, email, password) VALUES (?, ?, ?, ?)",
                       (user_id, name, email, hashed_password))
        conn.commit()
        conn.close()
        
        session['user'] = {"id": user_id, "name": name, "email": email}
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Cet email est déjà utilisé."}), 400

@app.route('/api/login-email', methods=['POST'])
def login_email():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email et mot de passe requis"}), 400

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, password FROM users WHERE email = ?", (email,))
    user_row = cursor.fetchone()
    conn.close()

    if user_row and check_password_hash(user_row[3], password):
        session['user'] = {"id": user_row[0], "name": user_row[1], "email": user_row[2]}
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Email ou mot de passe incorrect."}), 401

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    user = session.get('user')
    if not user:
        return jsonify([])
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM conversations WHERE user_id = ? ORDER BY created_at DESC", (user['id'],))
    rows = cursor.fetchall()
    conn.close()
    
    convs = [{"id": r[0], "title": r[1]} for r in rows]
    return jsonify(convs)

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Non authentifié"}), 401
        
    data = request.json
    conv_id = data.get('id')
    title = data.get('title', 'Nouvelle discussion')
    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
                   (conv_id, user['id'], title))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/conversations/<conv_id>/messages', methods=['GET'])
def get_messages(conv_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conv_id,))
    rows = cursor.fetchall()
    conn.close()
    
    messages = [{"role": r[0], "content": r[1]} for r in rows]
    return jsonify(messages)

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    history = data.get('history', [])
    conv_id = data.get('conversation_id')
    user = session.get('user')

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history
        )
        reply = response.choices[0].message.content

        if user and conv_id and len(history) > 0:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # 1. Vérifier si la conversation existe, sinon la créer
            cursor.execute("SELECT id, title FROM conversations WHERE id = ?", (conv_id,))
            conv_row = cursor.fetchone()
            if not conv_row:
                cursor.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
                               (conv_id, user['id'], "Nouvelle discussion"))
                current_title = "Nouvelle discussion"
            else:
                current_title = conv_row[1]

            # 2. Récupérer le dernier message envoyé par l'utilisateur
            last_user_msg = history[-1]['content']

            # 3. Vérifier si ce message exact n'a pas déjà été enregistré juste avant (anti-duplication)
            cursor.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 2", (conv_id,))
            last_msgs = cursor.fetchall()
            
            already_exists = False
            if last_msgs:
                # Si le dernier message en base est identique au message utilisateur actuel
                if any(m[0] == 'user' and m[1] == last_user_msg for m in last_msgs):
                    already_exists = True

            # S'il n'existe pas encore en base, on l'ajoute proprement
            if not already_exists:
                cursor.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                               (conv_id, "user", last_user_msg))
                cursor.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                               (conv_id, "assistant", reply))
                conn.commit()

            # 4. Génération automatique d'un titre intelligent si c'est une "Nouvelle discussion"
            if current_title == "Nouvelle discussion":
                try:
                    cursor.execute("SELECT role, content FROM messages WHERE conversation_id = ? LIMIT 4", (conv_id,))
                    context_rows = cursor.fetchall()
                    conversation_snippet = "\n".join([f"{r[0]}: {r[1]}" for r in context_rows])

                    title_response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": "Tu es un expert en résumé. Analyse l'échange et génère un titre court et percutant de 3 à 5 mots maximum (sans guillemets, sans ponctuation finale, orienté métier/thème) pour nommer la discussion."},
                            {"role": "user", "content": f"Voici les premiers messages de la discussion :\n{conversation_snippet}\n\nDonne un titre thématique court :"}
                        ]
                    )
                    generated_title = title_response.choices[0].message.content.strip().replace('"', '')
                    if len(generated_title) > 35:
                        generated_title = generated_title[:32] + '...'
                        
                    cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (generated_title, conv_id))
                    conn.commit()
                except Exception as e:
                    print("Erreur génération titre:", e)

            conn.close()

        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
<<<<<<< Updated upstream
    app.run(host='0.0.0.0', port=port)
=======
    app.run(host='0.0.0.0', port=port)
>>>>>>> Stashed changes
