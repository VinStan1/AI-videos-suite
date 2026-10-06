"""Offline 72s educational demo. Run inside the project Docker image."""
from __future__ import annotations
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from app import media, pipeline, store
from app.models import Storyboard


class Context:
    def check(self): pass
    def progress(self,message,percent=None): print(message,flush=True)
    def run(self,args,cwd=None,timeout=7200):
        import subprocess
        result=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace")[-4500:])
        return result.stdout


def demo_asset(path:Path,kind:str):
    """Original schematic artwork, intentionally illustrative and not AI output."""
    w,h=540,960; image=Image.new("RGB",(w,h));d=ImageDraw.Draw(image)
    for y in range(h): d.line((0,y,w,y),fill=(12,25+y//40,45+y//28))
    if kind=="earth":
        d.ellipse((38,165,502,730),fill="#153B5B",outline="#64C8CF",width=3)
        d.polygon([(75,315),(155,240),(215,330),(180,440),(220,520),(155,660),(90,500)],fill="#3B7D80")
        d.polygon([(325,270),(405,290),(465,380),(405,435),(390,530),(325,590),(285,460)],fill="#3B7D80")
        for offset in (-35,0,35):
            points=[(170+x*190/60,440+offset+math.sin(x/60*math.pi)*60) for x in range(61)]
            d.line(points,fill="#9EF2E3",width=3)
        for x,y in [(170,440),(360,440)]:d.ellipse((x-7,y-7,x+7,y+7),fill="#FFFFFF")
    elif kind=="cable":
        d.polygon([(0,700),(100,675),(240,710),(390,665),(540,700),(540,960),(0,960)],fill="#172B3C")
        d.line([(0,600),(150,620),(300,610),(540,640)],fill="#18212E",width=38)
        d.line([(0,600),(150,620),(300,610),(540,640)],fill="#5FABB4",width=18)
        d.line([(0,600),(150,620),(300,610),(540,640)],fill="#B5F8D6",width=5)
        d.ellipse((215,420,395,640),fill="#131C2D",outline="#BADEE0",width=12)
        d.ellipse((245,450,365,610),fill="#24526B",outline="#659CAC",width=9)
        for x,y in [(290,520),(325,520),(305,560)]: d.ellipse((x-9,y-9,x+9,y+9),fill="#B5F8D6")
    else:
        for offset in (-85,-42,0,42,85):
            points=[(x,460+offset+55*math.sin(x/90)) for x in range(w)]
            d.line(points,fill="#438B9B",width=10)
            d.line(points,fill="#B2F9E7",width=3)
            for x in (100,270,450):
                y=460+offset+55*math.sin(x/90); d.ellipse((x-6,y-6,x+6,y+6),fill="#FFFFFF")
    image.save(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final",action="store_true",help="Render at storyboard resolution instead of 540p preview")
    parser.add_argument("--prepare-only",action="store_true",help="Create assets and narration without rendering")
    args=parser.parse_args();ctx=Context()
    path=Path(__file__).resolve().parents[1]/"examples/internet-undersea-educational.json"
    board=Storyboard.model_validate_json(path.read_text("utf-8")).model_dump(exclude={"revision"})
    project=store.create(board["title"],board["story"]);project.update(board)
    root=store.project_dir(project["id"])
    artwork={}
    for kind in ("earth","cable","fiber"):
        image=root/"assets/images"/("demo_"+kind+".png");demo_asset(image,kind)
        artwork[kind]=store.asset(root,str(image.relative_to(root)),"demo",stale=False)
    from app.composition import asset_key
    for scene in project["scenes"]:
        for asset in scene["assets"]:
            project["assets"]["images"][asset_key(scene["id"],asset["id"])]=dict(artwork[asset["id"]])
    store.save(project);pipeline.generate_voice(project,{},ctx)
    # Explicit demo timing only: fit the technical voice to authored 12s slots.
    # The production engine never silently stretches narration to visual events.
    for scene in project["scenes"]:
        info=project["assets"]["audio"][scene["id"]];audio=store.safe_path(root,info["path"])
        slot=scene["duration"];length=media.wav_seconds(audio)
        if length>slot-.2:
            adjusted=audio.with_suffix(".fit.wav")
            ctx.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(audio),"-af",f"atempo={length/(slot-.2):.9f}",str(adjusted)])
            adjusted.replace(audio);length=media.wav_seconds(audio)
        padded=audio.with_suffix(".padded.wav")
        media.join_voice_parts([(audio,0),(None,max(0,slot-length))],padded);padded.replace(audio)
        info.update(sha256=store.file_hash(audio),duration=media.wav_seconds(audio))
    store.save(project)
    pipeline.assemble_audio(project,ctx)
    pipeline.generate_captions(project,{"caption_method":"estimate","allow_estimated":True},ctx)
    if not args.prepare_only: pipeline.render(project,{"preview":not args.final},ctx)
    print(json.dumps({"project_id":project["id"],"seconds":project["narration"]["duration"],
                      "project":str(root),"video":str(root/"output"/("video_finale.mp4" if args.final else "preview.mp4")) if not args.prepare_only else None},indent=2))


if __name__=="__main__":main()
