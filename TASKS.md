# TASKS

## Obiettivo
Bot Telegram (@Trascrizioni_toan_bot): mandi un link o un audio → ricevi un file `.md` con titolo, riassunto e trascrizione. Funziona anche a PC spento.

## Checklist
- [x] Bot creato su BotFather, token verificato (`getMe` ok)
- [x] Scelto hosting: Vercel (già collegato), funzione Python serverless con webhook Telegram
- [x] ~~Trascrizione via Vercel AI Gateway~~ → bloccato: il Gateway richiede una carta di credito sull'account
- [x] Passaggio a Groq: Whisper large-v3 + riassunto (gpt-oss-120b), codice pronto
- [x] Chiave Groq in `GROQ_API_KEY` su Vercel
- [x] Test pipeline dal server (reel di prova): download + trascrizione + titolo/riassunto OK
- [x] Testi lunghi: riassunto a pezzi + attesa automatica sui limiti 429 (testato su 55k caratteri ≈ 1h: 100 s)
- [x] Download link: yt-dlp (Instagram, TikTok, YouTube, ecc.)
- [x] Input vocali/audio/video inviati direttamente su Telegram
- [x] Test locale: download Instagram del reel di prova ok, trascrizione ok
- [x] Deploy su Vercel (progetto `trascrizioni-bot`, da GitHub) + variabili d'ambiente
- [x] Webhook Telegram impostato con secret → https://trascrizioni-bot-tonno-team.vercel.app/api/index
- [ ] Bot limitato alla tua chat (ALLOWED_CHAT_IDS)
- [ ] Test end-to-end con il reel Instagram di prova, fatto dal server Vercel
- [x] Salvataggio su Google Drive: codice bot + script `drive/Code.gs` (Apps Script, niente OAuth)
- [ ] Tu: pubblicare lo script Apps Script e mandarmi l'URL → lo metto in `DRIVE_URL` su Vercel
- [ ] Test salvataggio su Drive
- [ ] Comando rapido iPhone: registra → sendDocument alla tua chat → POST del messaggio al webhook (nessun codice server in più)
- [ ] Test del comando rapido con un memo vero

## Scoperte
- Script Python "vecchio" non presente nelle repo: repo vuote al momento dell'inizio.
- Instagram: con `curl_cffi` (impersonation) risponde 429 da IP cloud; senza impersonation funziona → patch in `download_url`.
- TikTok: richiede `curl_cffi` (senza, errore "Unexpected response").
- YouTube: da IP cloud chiede "Sign in to confirm you're not a bot" → servono cookie (`YT_COOKIES`, formato Netscape) oppure non funzionerà dal server.
- Limite Whisper 25 MB per file (~1h di audio a bassa qualità). Nessun ffmpeg sul server, quindi niente spezzettamento dei file lunghi.
- File da Telegram: limite 20 MB per il download dal bot.
- Drive: con un service account i file non si possono creare su un Drive personale (serve quota) → si usa un web app Apps Script che gira col tuo account.
- Controllo periodico su Drive scartato: su Vercel Hobby i cron girano al massimo una volta al giorno. L'invio diretto dal comando rapido è immediato.
- AI Gateway Vercel: serviva un header `ai-gateway-protocol-version` (corretto), poi 403 "requires a valid credit card" → abbandonato.
- Groq è dietro Cloudflare: lo User-Agent predefinito di Python viene bloccato (errore 1010) → ora mandiamo un User-Agent esplicito.
- I log runtime di Vercel non sono leggibili dalla sessione (403) → endpoint `{"diag": url}` (protetto dal secret) per testare la pipeline sul server.
- Groq gratuito: 8000 token/minuto per tutti i modelli di testo → riassunto a pezzi da 14k caratteri.
