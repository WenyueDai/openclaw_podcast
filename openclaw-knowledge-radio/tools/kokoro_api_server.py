#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from kokoro_onnx import Kokoro
import subprocess

BASE = Path('/home/eva/openclaw_workspace/openclaw_podcast/openclaw-knowledge-radio')
MODEL = BASE / 'models' / 'kokoro' / 'kokoro-v1.0.onnx'
VOICES = BASE / 'models' / 'kokoro' / 'voices-v1.0.bin'

if not MODEL.exists() or not VOICES.exists():
    raise RuntimeError('Kokoro model files missing')

kokoro = Kokoro(str(MODEL), str(VOICES))

app = FastAPI(title='Kokoro Local TTS API')


class TTSReq(BaseModel):
    input: str
    voice: str = 'bm_george'
    speed: float = 1.35
    response_format: str = 'mp3'
    model: str = 'kokoro'
    stream: bool = False


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/v1/audio/speech')
def speech(req: TTSReq):
    text = (req.input or '').strip()
    if not text:
        raise HTTPException(status_code=400, detail='empty input')
    try:
        audio, sr = kokoro.create(text, voice=req.voice, speed=float(req.speed), lang='en-gb')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'kokoro create failed: {e}')

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        wav = td / 'out.wav'
        mp3 = td / 'out.mp3'
        sf.write(str(wav), audio, sr)
        cmd = ['ffmpeg', '-y', '-i', str(wav), '-codec:a', 'libmp3lame', '-q:a', '4', str(mp3)]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0 or not mp3.exists():
            raise HTTPException(status_code=500, detail='ffmpeg mp3 encode failed')
        data = mp3.read_bytes()

    return Response(content=data, media_type='audio/mpeg')
