"""Bot Telegram: link o audio -> trascrizione + titolo + riassunto in un file .md."""
import asyncio
import datetime as dt
import glob
import json
import os
import re
import tempfile
import traceback
import urllib.error
import urllib.request
import uuid
import base64

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SECRET = os.environ.get("WEBHOOK_SECRET", "")
DRIVE_URL = os.environ.get("DRIVE_URL", "")  # web app Apps Script (drive/Code.gs)
DRIVE_KEY = os.environ.get("DRIVE_KEY", "")
ALLOWED = {c for c in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if c}
TG = f"https://api.telegram.org/bot{TOKEN}"
GATEWAY = "https://ai-gateway.vercel.sh"
STT_MODEL = "openai/whisper-1"
LLM_MODEL = "anthropic/claude-haiku-4.5"
MAX_AUDIO = 25 * 1024 * 1024  # limite Whisper
MIME = {"m4a": "audio/mp4", "mp4": "video/mp4", "webm": "audio/webm", "ogg": "audio/ogg",
        "oga": "audio/ogg", "opus": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav",
        "mov": "video/quicktime", "aac": "audio/aac", "flac": "audio/flac"}


def http(url, data=None, headers=None, timeout=240):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} da {url.split('/bot')[0]}: {e.read()[:400].decode(errors='replace')}") from None


def tg(method, **params):
    body = json.dumps(params).encode()
    return json.loads(http(f"{TG}/{method}", body, {"Content-Type": "application/json"}))


def tg_document(chat_id, name, content, caption):
    b = uuid.uuid4().hex
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\n'
             "Content-Type: text/markdown\r\n\r\n"]
    body = "".join(parts).encode() + content.encode() + f"\r\n--{b}--\r\n".encode()
    http(f"{TG}/sendDocument", body, {"Content-Type": f"multipart/form-data; boundary={b}"})


def download_url(url, tmp):
    import yt_dlp
    from yt_dlp.extractor.instagram import InstagramBaseIE
    InstagramBaseIE._can_impersonate = False  # con curl_cffi Instagram risponde 429; serve solo a TikTok
    opts = {"format": "ba[abr<=96]/wa/ba/b", "outtmpl": f"{tmp}/a.%(ext)s", "quiet": True,
            "noplaylist": True, "max_filesize": MAX_AUDIO}
    cookies = os.environ.get("YT_COOKIES")
    if cookies:
        open(f"{tmp}/cookies.txt", "w").write(cookies)
        opts["cookiefile"] = f"{tmp}/cookies.txt"
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    return glob.glob(f"{tmp}/a.*")[0], info.get("title") or ""


def download_tg_file(file_id, tmp):
    path = tg("getFile", file_id=file_id)["result"]["file_path"]
    dest = f"{tmp}/a.{path.rsplit('.', 1)[-1]}"
    open(dest, "wb").write(http(f"https://api.telegram.org/file/bot{TOKEN}/{path}"))
    return dest


def transcribe(path, oidc):
    data = open(path, "rb").read()
    if len(data) > MAX_AUDIO:
        raise ValueError("Audio oltre 25 MB: troppo lungo per una sola trascrizione.")
    ext = path.rsplit(".", 1)[-1].lower()
    body = json.dumps({"audio": base64.b64encode(data).decode(), "mediaType": MIME.get(ext, "audio/mpeg")})
    r = json.loads(http(f"{GATEWAY}/v4/ai/transcription-model", body.encode(), {
        "Authorization": f"Bearer {oidc}", "ai-model-id": STT_MODEL, "Content-Type": "application/json"}))
    return r["text"].strip(), r.get("language"), r.get("durationInSeconds")


def summarize(text, oidc, hint):
    prompt = ("Ti do la trascrizione di un video. Rispondi SOLO con un JSON "
              '{"titolo": "...", "riassunto": "..."} in italiano. '
              "titolo: max 8 parole, descrive il contenuto. "
              "riassunto: markdown, 1 frase di sintesi e poi i punti chiave in elenco puntato, "
              "utile per studiare.\n"
              f"Titolo originale (può essere vuoto): {hint}\n\nTRASCRIZIONE:\n{text}")
    body = json.dumps({"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]})
    r = json.loads(http(f"{GATEWAY}/v1/chat/completions", body.encode(), {
        "Authorization": f"Bearer {oidc}", "Content-Type": "application/json"}))
    out = r["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", out, re.S)
    try:
        j = json.loads(m.group(0))
        return j["titolo"].strip(), j["riassunto"].strip()
    except Exception:
        return hint or "Trascrizione", out.strip()


def paragraphs(text, n=4):
    s = re.split(r"(?<=[.!?])\s+", text)
    return "\n\n".join(" ".join(s[i:i + n]) for i in range(0, len(s), n))


def build_md(title, summary, text, source, lang, secs):
    meta = [f"- **Fonte:** {source}", f"- **Data:** {dt.date.today().isoformat()}"]
    if lang:
        meta.append(f"- **Lingua:** {lang}")
    if secs:
        meta.append(f"- **Durata:** {int(secs) // 60}:{int(secs) % 60:02d}")
    return f"# {title}\n\n" + "\n".join(meta) + f"\n\n## Riassunto\n\n{summary}\n\n## Trascrizione\n\n{paragraphs(text)}\n"


def slug(s):
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "trascrizione"


def process(msg, oidc):
    chat = msg["chat"]["id"]
    status = tg("sendMessage", chat_id=chat, text="⏳ Trascrivo…",
                reply_to_message_id=msg["message_id"])["result"]["message_id"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            text_in = msg.get("text") or msg.get("caption") or ""
            url = re.search(r"https?://\S+", text_in)
            media = next((msg[k] for k in ("voice", "audio", "video", "video_note", "document") if k in msg), None)
            if media:
                path, hint, source = download_tg_file(media["file_id"], tmp), media.get("file_name", ""), "file inviato su Telegram"
            elif url:
                path, hint = download_url(url.group(0), tmp)
                source = url.group(0)
            else:
                tg("editMessageText", chat_id=chat, message_id=status,
                   text="Mandami un link (YouTube, Instagram, TikTok…) o un audio/vocale.")
                return
            text, lang, secs = transcribe(path, oidc)
        title, summary = summarize(text, oidc, hint)
        md = build_md(title, summary, text, source, lang, secs)
        name = f"{dt.date.today().isoformat()}-{slug(title)}.md"
        tg_document(chat, name, md, f"📝 {title}"[:1000])
        if DRIVE_URL:
            try:
                http(DRIVE_URL, json.dumps({"key": DRIVE_KEY, "name": name, "content": md}).encode(),
                     {"Content-Type": "application/json"}, timeout=60)
            except Exception as e:
                tg("sendMessage", chat_id=chat, text=f"⚠️ Non salvato su Drive: {str(e)[:300]}")
        tg("deleteMessage", chat_id=chat, message_id=status)
    except Exception as e:
        traceback.print_exc()
        tg("editMessageText", chat_id=chat, message_id=status, text=f"❌ Errore: {str(e)[:500]}")


def diag(url, oidc):
    """Esegue la pipeline senza Telegram e riporta ogni passo (per i test)."""
    out = {"oidc": bool(oidc)}
    try:
        from vercel.cache.context import get_context
        out["wait_until"] = get_context().wait_until is not None
        with tempfile.TemporaryDirectory() as tmp:
            path, hint = download_url(url, tmp)
            out["download"] = [path, os.path.getsize(path), hint]
            text, lang, secs = transcribe(path, oidc)
            out["transcribe"] = [text[:200], lang, secs]
        out["summary"] = summarize(text, oidc, hint)
    except Exception:
        out["error"] = traceback.format_exc()[-1500:]
    return out


async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    ok = scope["method"] == "POST" and (not SECRET or headers.get("x-telegram-bot-api-secret-token") == SECRET)
    data = json.loads(body or b"{}") if ok else {}
    oidc = headers.get("x-vercel-oidc-token") or os.environ.get("VERCEL_OIDC_TOKEN", "")
    if ok and "diag" in data:
        out = json.dumps(await asyncio.to_thread(diag, data["diag"], oidc), ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": out})
        return
    if ok:
        msg = data.get("message")
        if msg and (not ALLOWED or str(msg["chat"]["id"]) in ALLOWED):
            print("messaggio da chat", msg["chat"]["id"])
            job = asyncio.to_thread(process, msg, oidc)
            try:
                from vercel.functions import wait_until
                from vercel.cache.context import get_context
                if get_context().wait_until is None:
                    raise RuntimeError
                wait_until(job)
            except Exception:
                print("wait_until non disponibile: elaborazione sincrona")
                await job
        elif msg:
            print("chat non autorizzata:", msg["chat"]["id"])
    await send({"type": "http.response.start", "status": 200 if ok else 403,
                "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": b"ok"})
