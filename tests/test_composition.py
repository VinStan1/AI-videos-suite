import io
import json
import shutil
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import media, pipeline, store
from app.composition import asset_key, normalize_scene, required_asset_ids
from app.compositor import Compositor, camera_rect
from app.main import app
from app.models import Scene, Settings, Storyboard, Transition
from app.transitions import TRANSITIONS, apply_transition


def scene(**kwargs):
    return {"id":"s_00000001","text":"Una spiegazione.","prompt":"", "motion":"still",**kwargs}


def test_legacy_storyboards_and_default_asset_are_unchanged():
    data=scene(prompt="The original prompt",motion="pan_left")
    parsed=Scene.model_validate(data)
    assert parsed.assets==[] and parsed.visual_events==[] and parsed.transition is None
    assert Settings().video_mode=="narrative"
    plan=normalize_scene(data,4,{})
    assert plan["legacy"] and plan["motion"]=="pan_left"
    assert plan["assets"][0]=={"id":"default","prompt":"The original prompt"}
    assert required_asset_ids(plan)=={"default"}
    assert plan["events"][0]["start"]==0 and plan["events"][0]["end"]==4
    minimum=Scene.model_validate({"text":"Una storia.","prompt":"Original","motion":"zoom_in"})
    assert minimum.id.startswith("s_") and minimum.visual_events==[]


def test_all_existing_examples_parse():
    for path in (Path(__file__).parents[1]/"examples").glob("*.json"):
        raw=json.loads(path.read_text("utf-8"))
        if "scenes" not in raw: continue
        board=Storyboard.model_validate(raw)
        assert len(board.scenes)==len(raw["scenes"])
        for old,new in zip(raw["scenes"],board.scenes):
            assert old["text"]==new.text and old.get("prompt","")==new.prompt


@pytest.mark.parametrize("event",[
    {"type":"show_text","text":"X","start":2,"end":1},
    {"type":"show_text","text":"X","start":-1,"end":1},
    {"type":"show_text","text":"X","start":0,"end":float("nan")},
    {"type":"reframe","start":0,"end":1,"to":[.8,.1,.4,.4]},
    {"type":"reframe","start":0,"end":1,"to":[0,0,0,.4]},
    {"type":"show_text","text":"X","end":1,"position":[1.1,.5]},
    {"type":"show_text","text":"X","end":1,"position":[.5,float("inf")]},
    {"type":"show_image","asset":"missing","end":1},
    {"type":"arrow","end":1,"points":[[.5,.5]]},
    {"type":"circle","end":1,"position":[.5,.5],"size":[0,.5]},
    {"type":"show_image","asset":"default","end":1,"transition":{"type":"spin"}},
    {"type":"show_image","asset":"default","end":1,"transition":{"type":"zoom_through","target":[-.1,.5]}},
    {"type":"diagram","end":1,"nodes":[{"id":"a","label":"A","position":[.2,.3]}],"edges":[{"source":"a","target":"bad"}]},
    {"type":"show_text","text":"X","end":1,"layer":"subtitles"},
])
def test_validation_reports_scene_and_event(event):
    with pytest.raises(ValueError,match="Scena s_00000001.*evento 1"):
        Scene.model_validate(scene(visual_events=[event]))


def test_event_bounds_are_checked_against_actual_audio():
    data=scene(visual_events=[{"type":"headline","text":"Titolo","end":5}])
    Scene.model_validate(data)
    with pytest.raises(ValueError,match="evento 1.*oltre audio/scena"):
        normalize_scene(data,4,{})
    with pytest.raises(ValueError,match="evento 1.*oltre durata"):
        Scene.model_validate(dict(data,duration=4))


def test_duplicate_assets_and_invalid_transition_timing():
    for definitions in [[{"id":"default"}], [{"id":"a"},{"id":"a"}]]:
        with pytest.raises(ValueError,match="Scena s_00000001"):
            Scene.model_validate(scene(assets=definitions))
    with pytest.raises(ValueError): Transition(type="blur",duration=0)
    assert Transition(type="cut",duration=0).duration==0
    data=scene(assets=[{"id":"a"}],visual_events=[{"type":"show_image","asset":"a","start":0,"end":.2,
                "transition":{"type":"crossfade","duration":.4}}])
    with pytest.raises(ValueError,match="evento 1.*transizione"):
        normalize_scene(data,1,{})


def test_image_overlaps_require_separate_layers_or_z():
    events=[{"type":"show_image","asset":"default","start":0,"end":2},
            {"type":"show_image","asset":"default","start":1,"end":3}]
    with pytest.raises(ValueError,match="sovrapposti"):
        normalize_scene(scene(visual_events=events),3,{})
    events[1]["z"]=11
    assert len(normalize_scene(scene(visual_events=events),3,{})["events"])==2


def test_preset_reuses_assets_and_creates_shorter_shots():
    plan=normalize_scene(scene(prompt="Original image"),9,{"video_mode":"educational"})
    assert not plan["legacy"]
    shots=[e for e in plan["events"] if e["type"]=="show_image"]
    assert len(shots)==4 and all(e["end"]-e["start"]<=2.5 for e in shots)
    assert required_asset_ids(plan)=={"default"}
    assert any(e["type"]=="reframe" for e in plan["events"])
    assert any(e["type"]=="headline" for e in plan["events"])


def test_camera_overlaps_are_rejected_with_scene_context():
    data=scene(visual_events=[{"type":"reframe","start":0,"end":2,"to":[0,0,.7,.7]},
                            {"type":"pan","start":1,"end":3,"to":[.3,0,.7,.7]}])
    with pytest.raises(ValueError,match="Scena s_00000001.*camera sovrapposti"):
        normalize_scene(data,4,{})


def test_crop_coordinates_refer_to_source_and_reframe_holds_its_end(tmp_path):
    image=Image.new("RGB",(400,400),"blue");image.paste("red",(0,0,200,200))
    path=tmp_path/"quadrants.png";image.save(path)
    data=scene(assets=[{"id":"earth"}],visual_events=[
        {"type":"show_image","asset":"earth","start":0,"end":4},
        {"type":"reframe","start":0,"end":2,"to":[0,0,.5,.5]}])
    plan=normalize_scene(data,4,{})
    compositor=Compositor(plan,{"earth":path},(100,160),24)
    event=next(e for e in plan["events"] if e["type"]=="show_image")
    assert camera_rect(plan,event,1)==pytest.approx([0,0,.75,.75])
    assert camera_rect(plan,event,3)==pytest.approx([0,0,.5,.5])
    assert compositor.frame(3).getpixel((50,80))==(255,0,0)


def test_layers_draw_annotations_over_images_and_text_over_annotations(tmp_path):
    path=tmp_path/"image.png";Image.new("RGB",(100,160),"red").save(path)
    data=scene(visual_events=[
        {"type":"show_image","asset":"default","end":3},
        {"type":"highlight","position":[.5,.5],"size":[.6,.3],"color":"#00FF00","end":2},
        {"type":"headline","text":"TEST","position":[.5,.5],"end":1}])
    plan=normalize_scene(data,3,{})
    assert [e["layer"] for e in plan["events"]]==["images","annotations","text"]
    compositor=Compositor(plan,{"default":path},(100,160),24)
    assert compositor.frame(1.5).getpixel((20,80))[1]>200
    assert compositor.frame(2.5).getpixel((50,80))==(255,0,0)
    assert compositor.frame(.5).tobytes()!=compositor.frame(1.5).tobytes()


@pytest.mark.parametrize("kind",list(TRANSITIONS))
def test_every_transition_has_correct_endpoints_and_a_distinct_midpoint(kind):
    old=Image.new("RGB",(120,180),"red");new=Image.new("RGB",(120,180),"blue")
    spec={"type":kind,"target":[.65,.4]}
    assert apply_transition(old,new,spec,1).tobytes()==new.tobytes()
    expected=new if kind=="cut" else old
    assert apply_transition(old,new,spec,0).tobytes()==expected.tobytes()
    if kind!="cut":
        middle=apply_transition(old,new,spec,.5)
        assert middle.size==new.size and middle.tobytes() not in (old.tobytes(),new.tobytes())


def test_zoom_through_uses_its_target_point():
    image=Image.new("RGB",(200,200),"black")
    image.paste("red",(0,0,100,200));image.paste("blue",(100,0,200,200))
    assert apply_transition(image,image,{"type":"zoom_through","target":[.2,.4]},.5).getpixel((100,100))[0]>200
    assert apply_transition(image,image,{"type":"zoom_through","target":[.8,.4]},.5).getpixel((100,100))[2]>200


def test_primitive_scene_needs_no_ai_image():
    data=scene(visual_events=[{"type":"headline","text":"UNA IDEA","end":2}])
    plan=normalize_scene(data,2,{"video_mode":"educational"})
    assert required_asset_ids(plan)==set()
    assert Compositor(plan,{},(120,200),24).frame(1).getbbox()


def test_overlay_on_legacy_manual_image_keeps_the_default_image():
    data=scene(visual_events=[{"type":"headline","text":"Il titolo","end":2}])
    assert required_asset_ids(normalize_scene(data,2,{},available_assets={"default"}))=={"default"}
    data["visual_events"].append({"type":"background","color":"#101827","end":2})
    assert required_asset_ids(normalize_scene(data,2,{},available_assets={"default"}))==set()


class Context:
    def check(self): pass
    def progress(self,*args): pass
    def run(self,args,cwd=None,timeout=7200):
        import subprocess
        result=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace"))
        return result.stdout


def test_legacy_clip_is_byte_identical_to_original_renderer(tmp_path):
    if not shutil.which("ffmpeg"):pytest.skip("FFmpeg required")
    for directory in ("assets/images","cache","output"):(tmp_path/directory).mkdir(parents=True,exist_ok=True)
    path=tmp_path/"assets/images/source.png"
    image=Image.new("RGB",(180,320),"gray");image.paste("red",(15,40,75,120));image.save(path)
    audio=tmp_path/"cache/narration.wav"
    with wave.open(str(audio),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(48000);out.writeframes(b"\0\0"*48000)
    data=scene(prompt="Original",motion="pan_left")
    settings=Settings(resolution="540x960",fps=24,subtitles_enabled=False).model_dump()
    reference=tmp_path/"original.mp4"
    media.render_segment(path,reference,data,24,(540,960),24,settings,Context())
    project={"settings":settings,"scenes":[data],"assets":{"images":{"s_00000001":store.asset(tmp_path,str(path.relative_to(tmp_path)),"manual",stale=False)},"music":None}}
    narration={"path":"cache/narration.wav","duration":1,"timeline":[{"id":"s_00000001","start":0,"end":1}]}
    media.render_movie(tmp_path,project,narration,None,True,Context())
    key=store.digest([store.file_hash(path),"pan_left","cover",24,(540,960),24,"renderer-v1"])
    clip=tmp_path/"cache/render"/(key+".mp4")
    assert clip.read_bytes()==reference.read_bytes()


def test_primitive_diagram_and_all_camera_variants_render(tmp_path):
    image=Image.new("RGB",(180,320),"blue");path=tmp_path/"source.png";image.save(path)
    for kind in ("reframe","zoom","pan","crop","focus"):
        data=scene(visual_events=[{"type":"show_image","asset":"default","end":2},
                                 {"type":kind,"start":0,"end":1,"to":[.1,.2,.5,.5]}])
        plan=normalize_scene(data,2,{})
        assert Compositor(plan,{"default":path},(90,160),24).frame(1.5).size==(90,160)
    data=scene(visual_events=[{"type":"diagram","end":2,"nodes":[
        {"id":"a","label":"Telefono","position":[.2,.3]},
        {"id":"b","label":"Costa","position":[.8,.3]}],"edges":[{"source":"a","target":"b"}]}])
    plan=normalize_scene(data,2,{})
    frame=Compositor(plan,{},(270,480),24).frame(1)
    assert frame.getpixel((135,144))!=frame.getpixel((135,430))


def test_composition_encoder_can_be_cancelled_without_partial_output(tmp_path):
    if not shutil.which("ffmpeg"):pytest.skip("FFmpeg required")
    from app.jobs import Cancelled
    class CancellingContext:
        calls=0
        def check(self):
            self.calls+=1
            if self.calls>1:raise Cancelled("Annullato")
    path=tmp_path/"cancelled.mp4"
    with pytest.raises(Cancelled):
        media.encode_frames((Image.new("RGB",(90,160),"blue") for _ in range(24)),path,24,(90,160),24,CancellingContext())
    assert not path.exists() and not path.with_suffix(".part.mp4").exists()


def test_scene_transition_uses_the_last_encoded_frame(tmp_path):
    if not shutil.which("ffmpeg"):pytest.skip("FFmpeg required")
    path=tmp_path/"outgoing.mp4"
    media.encode_frames((Image.new("RGB",(90,160),color) for color in ("red","green","blue")),path,3,(90,160),24,Context())
    pixel=media.last_video_frame(path,(90,160)).getpixel((45,80))
    assert pixel[2]>200 and pixel[0]<30


def test_educational_render_has_timed_shots_audio_and_cache_invalidation(tmp_path):
    if not shutil.which("ffmpeg"):pytest.skip("FFmpeg required")
    for directory in ("assets/images","cache","output"): (tmp_path/directory).mkdir(parents=True,exist_ok=True)
    images={}
    for aid,color in [("earth","red"),("cable","blue")]:
        path=tmp_path/f"assets/images/{aid}.png";Image.new("RGB",(90,160),color).save(path)
        images[asset_key("s_00000001",aid)]=store.asset(tmp_path,str(path.relative_to(tmp_path)),"manual",stale=False)
    audio=tmp_path/"cache/narration.wav"
    with wave.open(str(audio),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(48000);out.writeframes(b"\0\0"*96000)
    events=[{"type":"show_image","asset":"earth","end":1,"transition":{"type":"cut"}},
            {"type":"show_image","asset":"cable","start":1,"end":2,"transition":{"type":"cut"}},
            {"type":"label","text":"Prima prova","start":.1,"end":.5}]
    project={"settings":Settings(resolution="540x960",fps=24,subtitles_enabled=False).model_dump(),
             "scenes":[scene(assets=[{"id":"earth"},{"id":"cable"}],visual_events=events)],
             "assets":{"images":images,"music":None}}
    narration={"path":"cache/narration.wav","duration":2,"timeline":[{"id":"s_00000001","start":0,"end":2}]}
    movie,info=media.render_movie(tmp_path,project,narration,None,True,Context())
    assert info["duration"]==pytest.approx(2,abs=.1)
    for timestamp,channel in [(.7,0),(1.7,2)]:
        raw=media.run(["ffmpeg","-v","error","-ss",str(timestamp),"-i",str(movie),"-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"])
        image=Image.frombytes("RGB",(540,960),raw)
        pixel=image.getpixel((270,650));assert pixel[channel]>200 and pixel[(channel+1)%3]<30
    segments=[p for p in (tmp_path/"cache/render").glob("*.mp4") if ".part." not in p.name];assert len(segments)==1
    before=segments[0].stat().st_mtime_ns
    media.render_movie(tmp_path,project,narration,None,True,Context())
    assert segments[0].stat().st_mtime_ns==before
    events[-1]["text"]="Un nuovo titolo"
    media.render_movie(tmp_path,project,narration,None,True,Context())
    assert len([p for p in (tmp_path/"cache/render").glob("*.mp4") if ".part." not in p.name])==2
    assert json.loads((tmp_path/"output/composition.json").read_text())["scenes"][0]["legacy"] is False


def test_named_asset_api_roundtrip_and_manual_protection(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DATA_ROOT",tmp_path)
    with TestClient(app) as client:
        project=client.post("/api/projects",json={"title":"Educational"}).json();pid=project["id"]
        board={"title":"Educational","scenes":[scene(assets=[{"id":"earth","prompt":"Earth"}])],"settings":{"video_mode":"educational"}}
        result=client.put(f"/api/projects/{pid}/storyboard",json=board);assert result.status_code==200,result.text
        image=io.BytesIO();Image.new("RGB",(64,64),"green").save(image,"PNG")
        url=f"/api/projects/{pid}/upload?kind=image&scene_id=s_00000001&asset_id=earth"
        uploaded=client.post(url,files={"file":("earth.png",image.getvalue(),"image/png")});assert uploaded.status_code==200
        key=asset_key("s_00000001","earth");manifest=uploaded.json();original=manifest["assets"]["images"][key]
        manifest=pipeline.store.load(pid)
        pipeline.generate_images(manifest,{"scene_id":"s_00000001","asset_id":"earth","force":True},Context())
        assert store.load(pid)["assets"]["images"][key]==original
        board=client.get(f"/api/projects/{pid}/storyboard").json();board["scenes"][0]["assets"][0]["prompt"]="Changed"
        saved=client.put(f"/api/projects/{pid}/storyboard",json=board).json()
        assert key in saved["assets"]["images"] and not saved["assets"]["images"][key]["stale"]
        assert client.post(url.replace("asset_id=earth","asset_id=missing"),files={"file":("x.png",image.getvalue(),"image/png")}).status_code==400
        assert client.get(f"/api/projects/{pid}/prompts").text.find("ASSET earth")>=0
        assert client.delete(f"/api/projects/{pid}/assets?kind=image&scene_id=s_00000001&asset_id=earth").status_code==200


def test_generated_named_assets_are_invalidated_independently(tmp_path,monkeypatch):
    monkeypatch.setattr(store,"DATA_ROOT",tmp_path)
    with TestClient(app) as client:
        pid=client.post("/api/projects",json={"title":"Assets"}).json()["id"]
        board={"title":"Assets","scenes":[scene(assets=[{"id":"a","prompt":"A"},{"id":"b","prompt":"B"}])]}
        assert client.put(f"/api/projects/{pid}/storyboard",json=board).status_code==200
        manifest=store.load(pid)
        manifest["assets"]["images"]={asset_key("s_00000001",a):{"source":"cloudflare","stale":False} for a in ("a","b")}
        store.save(manifest)
        board=client.get(f"/api/projects/{pid}/storyboard").json();board["scenes"][0]["assets"][0]["prompt"]="New A"
        saved=client.put(f"/api/projects/{pid}/storyboard",json=board).json()
        assert saved["assets"]["images"][asset_key("s_00000001","a")]["stale"]
        assert not saved["assets"]["images"][asset_key("s_00000001","b")]["stale"]


def test_educational_demo_is_72_seconds_and_exercises_the_engine():
    board=Storyboard.model_validate_json((Path(__file__).parents[1]/"examples/internet-undersea-educational.json").read_text("utf-8"))
    assert sum(s.duration for s in board.scenes)==72
    plans=[normalize_scene(s.model_dump(),s.duration,board.settings.model_dump()) for s in board.scenes]
    events=[e for plan in plans for e in plan["events"]]
    assert {"headline","reframe","arrow","highlight","statistic","diagram"} <= {e["type"] for e in events}
    transitions={s.transition.type for s in board.scenes if s.transition}
    transitions|={e["transition"]["type"] for e in events if e.get("transition")}
    assert "zoom_through" in transitions and len(transitions)>=3
