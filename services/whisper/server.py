"""Optional CPU-only transcription service. No forced-alignment claims."""
import os
import tempfile
import threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException

app=FastAPI(title="Cryptid Whisper CPU")
lock=threading.Lock()
model=None

@app.get("/health")
def health():
    return {"status":"ok","loaded":model is not None,"model":os.getenv("WHISPER_MODEL","base")}

@app.post("/transcribe")
def transcribe(file:UploadFile=File(...),language:str=Form("it")):
    global model
    if language not in ("it","en","es","fr","de","pt"):
        raise HTTPException(400,"Lingua non supportata dal wrapper.")
    filename=None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav",delete=False) as tmp:
            filename=tmp.name;size=0
            while chunk:=file.file.read(1024*1024):
                size+=len(chunk)
                if size>250*1024*1024: raise HTTPException(413,"Audio troppo grande.")
                tmp.write(chunk)
        with lock:
            if model is None:
                from faster_whisper import WhisperModel
                model=WhisperModel(os.getenv("WHISPER_MODEL","base"),device="cpu",compute_type="int8",
                    cpu_threads=int(os.getenv("CPU_THREADS","2")),num_workers=1,
                    download_root="/models",local_files_only=os.getenv("OFFLINE","0")=="1")
            segments,info=model.transcribe(filename,language=language,beam_size=3,
                    word_timestamps=True,vad_filter=True,condition_on_previous_text=False)
            words=[];text=[]
            for segment in segments:
                text.append(segment.text)
                for w in segment.words or []:
                    words.append({"word":w.word.strip(),"start":w.start,"end":w.end,"probability":w.probability})
            return {"language":info.language,"text":" ".join(text),"words":words,
                    "method":"automatic_speech_recognition","not_forced_alignment":True}
    finally:
        if filename: Path(filename).unlink(missing_ok=True)
