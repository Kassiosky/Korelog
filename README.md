# 🎯 OpenKore Log Monitor com Telegram

Este projeto é uma ferramenta de monitoramento que lê os logs do **OpenKore**, armazena eventos em um banco de dados SQLite e envia alertas no **Telegram**, além de gerar gráficos de atividade.

---

## 📦 Funcionalidades

- 📜 Monitora o arquivo de log `console.txt` do OpenKore.
- 🔔 Envia alertas automáticos via **Telegram** quando detecta eventos importantes. ( no momento apenas disconect) 
- 📊 Gera gráficos com estatísticas dos logs.
- 🖥️ Captura e envia screenshots da tela do jogo.
- 🗄️ Armazena os dados em um banco SQLite para análises futuras.
- 🕒 Mensagem automatica a cada 10 minutos com status do bot.

---

## 🎒 Comandos Telegram

- /status  = obtem informação de exp + gráfico com drop de itens e experiência + ScreenShot da instância do Ragnarok (Precisa estar em primeiro plano, sem nada na frente )
- /comando = Executa o comando direto no console do Openkore ( ex: move pay_dun00  | ai )


## 🚀 Instalação

1. Acesse o diretório do openkore e entre no diretório [log]

2. extraia o conteúdo dentro dessa pasta

3. Configure os tokens/RoomID no arquivo config.py

4. Após o openkore estar rodando execute o arquivo [ start_log.bat ] 
