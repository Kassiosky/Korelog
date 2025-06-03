import time
import re
import pygetwindow as gw
import mss
import mss.tools
import requests
import sqlite3
import asyncio
import matplotlib.pyplot as plt

import threading
from datetime import datetime, timedelta
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import LOG_FILE, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from pywinauto import Application, findwindows

# ========= FUNÇÃO PARA ENVIAR COMANDO DIRETO AO OPENKORE =========
def send_command_to_openkore(comando: str):
    try:
        # Conectar ao processo start.exe
        app = Application().connect(path="start.exe")
        janela = app.top_window()

        # Focar na janela e enviar o comando + ENTER
        janela.set_focus()
        janela.type_keys(comando + "{ENTER}", with_spaces=True, pause=0.05)
        print(f"Comando enviado para o OpenKore: {comando}")
        return True
    except findwindows.ElementNotFoundError:
        print("❌ Processo start.exe não encontrado!")
        return False
    except Exception as e:
        print(f"❌ Erro ao enviar comando para o OpenKore: {e}")
        return False


# ========= FUNÇÕES TELEGRAM =========

def gerar_grafico_status():
    # Dados XP
    cursor.execute("SELECT base_xp, job_xp, timestamp FROM xp_log ORDER BY timestamp DESC LIMIT 20")
    xp_data = cursor.fetchall()

    if not xp_data:
        return None

    base_xp = [row[0] for row in xp_data][::-1]
    job_xp = [row[1] for row in xp_data][::-1]
    timestamps = [row[2][11:19] for row in xp_data][::-1]  # só hora

    # Dados itens
    cursor.execute("""
        SELECT item, SUM(quantidade) as total
        FROM item_log
        GROUP BY item
        ORDER BY total DESC
        LIMIT 10
    """)
    itens_data = cursor.fetchall()

    itens = [row[0] for row in itens_data]
    quantidades = [row[1] for row in itens_data]

    fig, axs = plt.subplots(2, 1, figsize=(10, 8))

    # Gráfico XP
    axs[0].plot(timestamps, base_xp, label='Base XP')
    axs[0].plot(timestamps, job_xp, label='Job XP')
    axs[0].set_title('Últimos 20 Registros de XP')
    axs[0].set_ylabel('XP')
    axs[0].legend()
    axs[0].tick_params(axis='x', rotation=45)

    # Gráfico itens
    axs[1].barh(itens, quantidades, color='skyblue')
    axs[1].set_title('Top 10 Itens Coletados')
    axs[1].invert_yaxis()  # itens maiores no topo
    axs[1].set_xlabel('Quantidade')

    plt.tight_layout()
    path = 'status_graph.png'
    plt.savefig(path)
    plt.close()
    return path

async def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")


async def send_photo_telegram(file_path, caption="Screenshot Ragnarok"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(file_path, 'rb') as photo:
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
        files = {'photo': photo}
        r = requests.post(url, data=payload, files=files)
        if r.status_code == 200:
            print("✅ Screenshot enviada ao Telegram!")
        else:
            print(f"❌ Erro ao enviar screenshot: {r.text}")


def screenshot_ragnarok(output="ragnarok.png"):
    windows = [w for w in gw.getWindowsWithTitle('Ragnarok') if w.visible]

    if not windows:
        print("❌ Janela do Ragnarok não encontrada ou não está visível.")
        return False

    window = windows[0]
    left, top, right, bottom = window.left, window.top, window.right, window.bottom
    width = right - left
    height = bottom - top

    print(f"Capturando janela em {left},{top},{width}x{height}...")

    with mss.mss() as sct:
        monitor = {"top": top, "left": left, "width": width, "height": height}
        sct_img = sct.grab(monitor)
        mss.tools.to_png(sct_img.rgb, sct_img.size, output=output)

    print(f"📸 Screenshot salva em {output}")
    return True


# ========= BANCO DE DADOS =========

conn = sqlite3.connect('openkore.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS xp_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    base_xp INTEGER,
    job_xp INTEGER,
    base_percent REAL,
    job_percent REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS item_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    item TEXT,
    quantidade INTEGER
)
""")

conn.commit()


def log_xp(base_xp, job_xp, base_percent, job_percent):
    cursor.execute("""
        INSERT INTO xp_log (timestamp, base_xp, job_xp, base_percent, job_percent)
        VALUES (?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), base_xp, job_xp, base_percent, job_percent))
    conn.commit()


def log_item(item, quantidade):
    cursor.execute("""
        INSERT INTO item_log (timestamp, item, quantidade)
        VALUES (?, ?, ?)
    """, (datetime.now().isoformat(), item, quantidade))
    conn.commit()


# ========= MONITORAMENTO DO LOG =========
print (f'🎒 Monitor Iniciado..')

def monitor_log():
    asyncio.run(send_telegram(' ✅ Monitor Iniciado.  ✅'))

    with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)  # Vai para o final do arquivo

        base_xp_total = 0
        job_xp_total = 0
        itens_coletados = {}

        last_report_time = datetime.now()

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue

            line = line.strip()
            #print(line)

            match_item = re.search(r"Item adicionado ao inventário: (.+)", line)
            if match_item:
                item_info = match_item.group(1)
                item_match = re.match(r"(.+?) x (\d+)", item_info)
                if item_match:
                    item_nome = item_match.group(1).strip()
                    quantidade = int(item_match.group(2))
                else:
                    item_nome = item_info.strip()
                    quantidade = 1

                log_item(item_nome, quantidade)

                if item_nome in itens_coletados:
                    itens_coletados[item_nome] += quantidade
                else:
                    itens_coletados[item_nome] = quantidade

            match_xp = re.search(r"obteve (\d+)/(\d+) \(([\d.]+)%/([\d.]+)%\) de Experiência", line)
            if match_xp:
                base_xp = int(match_xp.group(1))
                job_xp = int(match_xp.group(2))
                base_percent = float(match_xp.group(3))
                job_percent = float(match_xp.group(4))

                log_xp(base_xp, job_xp, base_percent, job_percent)

                base_xp_total += base_xp
                job_xp_total += job_xp

            if "Tempo esgotado no Servidor de Mapa" in line:
                mensagem = "🚨 *ALERTA*: Desconectado do servidor de mapa! Verificar o bot!"
                print(mensagem)
                asyncio.run(send_telegram(mensagem))

            now = datetime.now()
            if now - last_report_time >= timedelta(minutes=10):
                relatorio = "📊 *Resumo dos últimos 10 minutos:*\n"

                if base_xp_total > 0 or job_xp_total > 0:
                    relatorio += (
                        f"\n✨ *Experiência:*\n"
                        f"🔸 Base XP: +{base_xp_total}\n"
                        f"🔸 Job XP: +{job_xp_total}\n"
                    )

                if itens_coletados:
                    relatorio += "\n🎒 *Itens coletados:*\n"
                    for item, quantidade in itens_coletados.items():
                        relatorio += f"• {item} x{quantidade}\n"

                if base_xp_total > 0 or job_xp_total > 0 or itens_coletados:
                    asyncio.run(send_telegram(relatorio))

                base_xp_total = 0
                job_xp_total = 0
                itens_coletados = {}
                last_report_time = now


# ========= LOOP DE SCREENSHOT =========
async def itens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT item, SUM(quantidade) as total
        FROM item_log
        GROUP BY item
        ORDER BY total DESC
        LIMIT 20
    """)
    itens = cursor.fetchall()

    if not itens:
        await update.message.reply_text("Nenhum item coletado até agora.")
        return

    mensagem = "*🎒 Itens coletados:*\n"
    for item, quantidade in itens:
        mensagem += f"• {item} x{quantidade}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=mensagem, parse_mode="Markdown")

def screenshot_loop():
    while True:
        sucesso = screenshot_ragnarok()
        if sucesso:
            asyncio.run(send_photo_telegram('ragnarok.png'))
        time.sleep(900)  # 15 minutos


# ========= TELEGRAM BOT =========

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mensagem com resumo rápido dos últimos dados
    cursor.execute("SELECT base_xp, job_xp, base_percent, job_percent, timestamp FROM xp_log ORDER BY timestamp DESC LIMIT 1")
    xp = cursor.fetchone()
    if xp:
        base_xp, job_xp, base_percent, job_percent, ts = xp
        texto = (
            f"*Status Atual*\n"
            f"🕒 {ts}\n"
            f"✨ Base XP: {base_xp} (+{base_percent:.2f}%)\n"
            f"✨ Job XP: {job_xp} (+{job_percent:.2f}%)\n"
        )

    else:
        texto = "*Status Atual*\nNenhum dado de XP encontrado."
    print(texto)


    await context.bot.send_message(chat_id=update.effective_chat.id, text=texto, parse_mode="Markdown")

    # Gerar gráfico
    grafico_path = gerar_grafico_status()
    if grafico_path:
        with open(grafico_path, 'rb') as photo:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="📊 Gráfico de Status")

    # Tirar screenshot do Ragnarok
    sucesso = screenshot_ragnarok("ragnarok_status.png")
    if sucesso:
        with open("ragnarok_status.png", 'rb') as photo:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="🎮 Screenshot do Ragnarok")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Não foi possível capturar a janela do Ragnarok.")



async def comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Use: /comando <comando>")
        return
    comando = " ".join(context.args)
    sucesso = send_command_to_openkore(comando)
    if sucesso:
        await update.message.reply_text(f"Comando enviado: {comando}")
    else:
        await update.message.reply_text("Erro ao enviar comando para o OpenKore.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Use /status para ver o status atual.\n"
        "Use /comando <texto> para enviar comandos ao bot OpenKore."
    )


def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("itens", itens))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("comando", comando))

    # Rodar monitor de log em thread separada
    threading.Thread(target=monitor_log, daemon=True).start()

    # Rodar loop de screenshots em thread separada
    threading.Thread(target=screenshot_loop, daemon=True).start()

    application.run_polling()


if __name__ == "__main__":
    main()
