import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from auth import current_user
from llm import transcribe_audio, synthesize_speech, record_usage
from pricing import rate
from ratelimit import rate_limit

router = APIRouter(prefix="/api/voice", tags=["voice"])

VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "nova", "onyx", "fable"]
# gpt-realtime voices usable in live calls; the rest are TTS-only and get mapped for Realtime
REALTIME_VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]
VOICE_INFO = {"marin": "Hangat, ceria (Realtime)", "cedar": "Tenang, bersahabat (Realtime)", "alloy": "Netral", "ash": "Dalam, mantap",
              "ballad": "Lembut, ekspresif", "coral": "Ramah, energik", "echo": "Jernih, formal", "sage": "Kalem, bijak",
              "shimmer": "Cerah, ringan", "verse": "Dinamis", "nova": "Hangat (TTS)", "onyx": "Berat (TTS)", "fable": "Naratif (TTS)"}
TTS_FALLBACK = {"marin": "coral", "cedar": "ash"}


class TranscribeIn(BaseModel):
    audio_b64: str
    filename: str = "audio.webm"
    language: str | None = None


class TTSIn(BaseModel):
    text: str
    voice: str = "alloy"


@router.get("/voices")
async def voices():
    return {"voices": VOICES, "realtime": REALTIME_VOICES, "info": VOICE_INFO}


@router.post("/transcribe")
async def transcribe(x: TranscribeIn, u: dict = Depends(current_user)):
    await rate_limit(u, "voice")
    lang = x.language or (u.get("settings", {}) or {}).get("conversation_language") or "id"
    text = ""
    try:
        data = base64.b64decode(x.audio_b64.split(",")[-1])
        text = await transcribe_audio(data, x.filename, language=lang)
    except Exception as exc:
        raise HTTPException(502, "Transkripsi gagal, coba lagi") from exc
    await record_usage(u["id"], "voice_stt", rate("stt"), {})
    return {"text": text}


@router.post("/tts")
async def tts(x: TTSIn, u: dict = Depends(current_user)):
    await rate_limit(u, "voice")
    if not x.text.strip():
        raise HTTPException(400, "Empty text")
    voice = x.voice if x.voice in VOICES else "alloy"
    audio = b""
    try:
        audio = await synthesize_speech(x.text, voice)
    except Exception:
        try:
            audio = await synthesize_speech(x.text, TTS_FALLBACK.get(voice, "alloy"))
        except Exception as exc:
            raise HTTPException(502, "Sintesis suara gagal, coba lagi") from exc
    await record_usage(u["id"], "voice_tts", rate("tts"), {})
    return Response(content=audio, media_type="audio/mpeg")
