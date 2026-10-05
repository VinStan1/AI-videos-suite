from __future__ import annotations

import html
import difflib
import math
import re
import textwrap
import unicodedata
from pathlib import Path

STAMP = re.compile(r"^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})$")


def _alignment_key(value: str) -> str:
    value=unicodedata.normalize("NFKD",value.casefold())
    return "".join(character for character in value if character.isalnum())


def _script_words(text: str) -> list[str]:
    words=[]
    for token in text.split():
        if _alignment_key(token):
            words.append(token)
        elif words:
            words[-1]+=" "+token
    return words


def _allocate_words(tokens: list[str], start: float, end: float) -> list[dict]:
    if not tokens:
        return []
    weights=[max(2,len(_alignment_key(token))) for token in tokens]
    total=sum(weights);span=max(0.0,end-start)
    cursor=start; result=[]
    for index,(token,weight) in enumerate(zip(tokens,weights)):
        stop=end if index==len(tokens)-1 else cursor+span*weight/total
        result.append(dict(word=token,start=cursor,end=stop));cursor=stop
    return result


def align_script_words(script: str, recognized: list[dict], duration: float, minimum_score: float=.58):
    """Keep Whisper timing while making the authored script authoritative.

    Exact matches retain their word timestamps. Replaced, merged or split spans
    share the corresponding real audio interval. Words missed by Whisper are
    interpolated only inside the neighboring recognized interval.
    """
    reference=_script_words(script)
    heard=[word for word in recognized if _alignment_key(word.get("word",""))]
    if not reference or not heard:
        raise ValueError("Whisper non ha prodotto abbastanza parole per allineare il copione.")
    ref_keys=[_alignment_key(word) for word in reference]
    heard_keys=[_alignment_key(word["word"]) for word in heard]
    token_score=difflib.SequenceMatcher(None,ref_keys,heard_keys,autojunk=False).ratio()
    character_score=difflib.SequenceMatcher(None," ".join(ref_keys)," ".join(heard_keys),autojunk=False).ratio()
    score=.35*token_score+.65*character_score
    if score<minimum_score:
        raise ValueError(
            f"Whisper e copione divergono troppo per correggere i sottotitoli in sicurezza "
            f"(somiglianza {score:.0%}). Verifica che l'audio corrisponda al testo delle scene."
        )
    matcher=difflib.SequenceMatcher(None,ref_keys,heard_keys,autojunk=False)
    aligned=[None]*len(reference)
    exact=0
    for tag,i1,i2,j1,j2 in matcher.get_opcodes():
        if tag=="equal":
            exact+=i2-i1
            for ref_index,heard_index in zip(range(i1,i2),range(j1,j2)):
                aligned[ref_index]=dict(word=reference[ref_index],start=heard[heard_index]["start"],end=heard[heard_index]["end"])
        elif tag=="replace" and i1<i2 and j1<j2:
            replacement=_allocate_words(reference[i1:i2],heard[j1]["start"],heard[j2-1]["end"])
            aligned[i1:i2]=replacement
    index=0
    while index<len(aligned):
        if aligned[index] is not None:
            index+=1;continue
        stop=index
        while stop<len(aligned) and aligned[stop] is None: stop+=1
        left=aligned[index-1]["end"] if index else 0.0
        right=aligned[stop]["start"] if stop<len(aligned) else duration
        # A missing Whisper token can be fused into a neighbor. If there is no
        # audible gap, redistribute the neighboring phrase rather than create
        # overlapping or zero-duration timestamps.
        if right-left<.025*(stop-index):
            group_start=max(0,index-1);group_stop=min(len(aligned),stop+1)
            left=aligned[group_start]["start"] if aligned[group_start] else left
            right=aligned[group_stop-1]["end"] if aligned[group_stop-1] else right
            aligned[group_start:group_stop]=_allocate_words(reference[group_start:group_stop],left,right)
        else:
            aligned[index:stop]=_allocate_words(reference[index:stop],left,right)
        index=stop
    result=normalize_words(aligned,duration)
    if len(result)!=len(reference):
        raise ValueError("Non e' stato possibile assegnare timestamp validi a tutto il copione.")
    stats={"score":round(score,4),"script_words":len(reference),"recognized_words":len(heard),"exact_words":exact}
    return result,stats


def seconds(stamp: str) -> float:
    m = STAMP.fullmatch(stamp.strip())
    if not m or int(m[2]) > 59 or int(m[3]) > 59:
        raise ValueError("Timestamp SRT non valido: " + stamp)
    return int(m[1])*3600 + int(m[2])*60 + int(m[3]) + int(m[4])/1000


def parse_srt(text: str) -> list[dict]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").strip()
    if not text:
        raise ValueError("Il file dei sottotitoli e' vuoto.")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip().splitlines()
        if lines and lines[0].strip().isdigit(): lines.pop(0)
        if not lines or "-->" not in lines[0]:
            raise ValueError("Formato SRT non valido: manca la riga con -->.")
        bounds = lines.pop(0).split("-->")
        if len(bounds) != 2: raise ValueError("Intervallo SRT non valido.")
        start, end = seconds(bounds[0]), seconds(bounds[1])
        content = html.unescape(re.sub(r"<[^>]*>", "", "\n".join(lines))).strip()
        if start < 0 or end <= start or not content:
            raise ValueError("Sottotitolo vuoto o durata non positiva.")
        if cues and start < cues[-1]["end"] - 0.002:
            raise ValueError("Sottotitoli sovrapposti o non ordinati. Correggi gli intervalli nell'editor.")
        cues.append(dict(start=start, end=end, text=content))
    return cues


def timestamp(t: float) -> str:
    n = max(0, round(t * 1000))
    h, n = divmod(n, 3600000); m, n = divmod(n, 60000); s, ms = divmod(n, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[dict]) -> str:
    return "\n\n".join(f"{i}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c['text']}" for i,c in enumerate(cues,1)) + "\n"


def normalize_words(words: list[dict], duration: float) -> list[dict]:
    out = []
    last = 0.0
    for w in words:
        text = str(w.get("word", w.get("text", ""))).strip()
        try:
            start = float(w.get("start", w.get("start_time")))
            end = float(w.get("end", w.get("end_time")))
        except (TypeError, ValueError):
            continue
        if not text or not math.isfinite(start + end) or end <= start: continue
        start, end = max(last, 0.0, start), min(duration, end)
        if end <= start: continue
        out.append(dict(word=text, start=start, end=end)); last = end
    return out


def words_to_cues(words: list[dict], max_words=5, max_chars=43) -> list[dict]:
    cues, group = [], []
    def flush():
        if group:
            text = " ".join(x["word"] for x in group)
            text = re.sub(r"\s+([.,!?;:])", r"\1", text)
            cues.append(dict(start=group[0]["start"], end=group[-1]["end"], text=text))
            group.clear()
    for word in words:
        if group and (len(group) >= max_words or sum(len(x["word"])+1 for x in group)+len(word["word"]) > max_chars or word["start"]-group[-1]["end"] > 0.65):
            flush()
        group.append(word)
        if re.search(r"[.!?]$", word["word"]): flush()
    flush()
    return cues


def estimated_cues(timeline: list[dict]) -> list[dict]:
    """Explicitly approximate: uniform character-weighted allocation, not alignment."""
    cues = []
    for row in timeline:
        words = row["text"].split()
        weights = [max(2,len(w)) for w in words]
        total = sum(weights) or 1
        start = row["start"]
        end = row.get("speech_end",row["end"])
        items = []
        for w, weight in zip(words,weights):
            stop = start + (end-row["start"]) * weight / total
            items.append(dict(word=w,start=start,end=stop)); start=stop
        cues.extend(words_to_cues(items))
    return cues


def ass_time(t: float) -> str:
    n = max(0,round(t*100)); h,n=divmod(n,360000); m,n=divmod(n,6000); s,cs=divmod(n,100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_text(text: str, width: int = 29) -> str:
    # Never allow user-supplied ASS override tags or escape commands.
    text = text.replace("\\", "/").replace("{", "(").replace("}", ")")
    text = " ".join(text.split())
    lines = textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False)
    return "\\N".join(lines)


def make_ass(cues: list[dict], settings: dict) -> str:
    size = settings["subtitle_size"]
    width = max(18, round(29*62/size))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size},&H00FFFFFF,&H00FFFFFF,&H00111111,&H70000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,180,{settings['subtitle_bottom']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header + "\n".join(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Default,,0,0,0,,{ass_text(c['text'],width)}" for c in cues)+"\n"
