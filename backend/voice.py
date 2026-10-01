import base64
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from auth import current_user
from llm import transcribe_audio, synthesize_speech, record_usage, STT_CREDITS, TTS_CREDITS

router = APIRouter(prefix="/api/voice", tags=["voice"])

VOICES = ["alloy", "nova", "shimmer", "echo", "fable", "onyx", "coral", "sage", "ash"]


class TranscribeIn(BaseModel):
    audio_b64: str
    filename: str = "audio.webm"


class TTSIn(BaseModel):
    text: str
    voice: str = "alloy"


@router.get("/voices")
async def voices():
    return {"voices": VOICES}


@router.post("/transcribe")
async def transcribe(x: TranscribeIn, u: dict = Depends(current_user)):
    try:
        data = base64.b64decode(x.audio_b64.split(",")[-1])
        text = await transcribe_audio(data, x.filename)
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {str(e)[:120]}")
    await record_usage(u["id"], "voice_stt", STT_CREDITS, {})
    return {"text": text}


@router.post("/tts")
async def tts(x: TTSIn, u: dict = Depends(current_user)):
    if not x.text.strip():
        raise HTTPException(400, "Empty text")
    voice = x.voice if x.voice in VOICES else "alloy"
    try:
        audio = await synthesize_speech(x.text, voice)
    except Exception as e:
        raise HTTPException(502, f"TTS failed: {str(e)[:120]}")
    await record_usage(u["id"], "voice_tts", TTS_CREDITS, {})
    return Response(content=audio, media_type="audio/mpeg")
