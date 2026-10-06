"""Bounded-memory layer compositor; FFmpeg still encodes and mixes the result."""
from __future__ import annotations

import math
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .composition import CAMERA_EVENTS
from .transitions import apply_transition


@lru_cache(maxsize=128)
def font(name: str, size: int):
    try: return ImageFont.truetype(name, size)
    except OSError:
        raise ValueError(f"Font del tema non disponibile: {name}. Installa il font nel container.")


def ease(value):
    p=max(0.0,min(1.0,value))
    return p*p*(3-2*p)


def camera_rect(plan, image, time):
    rect=list(image.get("to") or (0,0,1,1))
    cameras=sorted((e for e in plan["events"] if e["type"] in CAMERA_EVENTS and
                    image["start"] <= e["start"] < image["end"] and
                    (not e.get("asset") or e["asset"]==image["asset"])), key=lambda e:(e["start"],e["index"]))
    motion=image.get("motion", "still")
    if not cameras and motion != "still":
        p=max(0,min(1,(time-image["start"])/(image["end"]-image["start"])))
        zoom=1+0.08*p if motion=="zoom_in" else 1.08-0.08*p if motion=="zoom_out" else 1.08
        scale=1/zoom; x=(1-scale)/2; y=x
        if motion=="pan_left": x=(1-scale)*(1-p)
        if motion=="pan_right": x=(1-scale)*p
        rect=[x,y,scale,scale]
    for event in cameras:
        if time < event["start"]: break
        origin=list(event.get("from_rect") or rect)
        p=1.0 if event["type"]=="crop" else ease((time-event["start"])/(event["end"]-event["start"]))
        rect=[a+(b-a)*p for a,b in zip(origin,event["to"])]
    return rect


def wrap_text(text, face, width):
    lines=[]
    for paragraph in text.split("\n"):
        current=""
        for word in paragraph.split():
            candidate=(current+" "+word).strip()
            if current and face.getlength(candidate)>width:
                lines.append(current);current=""
            # Split unusually long unspaced words rather than clipping them.
            for char in word:
                if face.getlength(current+char)>width and current:
                    lines.append(current);current=""
                current+=char
            current+=" "
        lines.append(current.strip())
    return "\n".join(lines)


def text_block(canvas, text, center, style, theme, color=None, box=None, card=False):
    w,h=canvas.size; spec=theme["styles"][style]
    width=box[0] if box else w*(1-2*theme["margin"])
    max_height=box[1] if box else h*0.35
    size=max(8,round(h*spec["size"]))
    draw=ImageDraw.Draw(canvas)
    while True:
        face=font(theme["font_bold"] if spec["bold"] else theme["font"],size)
        available=max(1,width-h*theme["text_padding"])
        wrapped=wrap_text(text,face,available)
        spacing=max(2,round(size*0.18))
        bounds=draw.multiline_textbbox((0,0),wrapped,font=face,spacing=spacing,align="center")
        longest=max((face.getlength(word) for word in text.split()),default=0)
        if (bounds[3]-bounds[1]<=max_height and longest<=available) or size<=9: break
        size-=1
    tw,th=bounds[2]-bounds[0],bounds[3]-bounds[1]
    x,y=center[0]-tw/2-bounds[0],center[1]-th/2-bounds[1]
    if card:
        padding=h*theme["card_padding"]
        draw.rounded_rectangle((center[0]-tw/2-padding,center[1]-th/2-padding,
                                center[0]+tw/2+padding,center[1]+th/2+padding),
                               radius=h*theme["radius"],fill=theme["card"])
    draw.multiline_text((x,y),wrapped,font=face,fill=color or theme["foreground"],spacing=spacing,align="center",
                        stroke_width=max(0,round(h*0.001)),stroke_fill=theme["background"])


def arrow(draw, points, color, width, head):
    draw.line(points,fill=color,width=width,joint="curve")
    a,b=points[-2],points[-1]; angle=math.atan2(b[1]-a[1],b[0]-a[0])
    wings=[(b[0]-head*math.cos(angle+d),b[1]-head*math.sin(angle+d)) for d in (-0.5,0.5)]
    draw.polygon([b,*wings],fill=color)


def draw_text(canvas,event,theme,time):
    kind=event["type"]
    style="headline" if kind=="headline" else "label" if kind=="label" else event.get("style","body")
    pos=event.get("position") or theme["styles"][style]["position"]
    text=event["text"]
    if event.get("animation")=="typewriter":
        p=min(1,(time-event["start"])/max(theme["animation_duration"],len(text)*theme["typewriter_char_seconds"]))
        text=text[:max(1,math.ceil(len(text)*p))]
    box=event.get("size")
    text_block(canvas,text,(pos[0]*canvas.width,pos[1]*canvas.height),style,theme,event.get("color"),
               (box[0]*canvas.width,box[1]*canvas.height) if box else None,kind=="label")


def draw_statistic(canvas,event,theme,time):
    w,h=canvas.size; pos=event.get("position") or theme["styles"]["statistic"]["position"]
    size=event.get("size") or (0.8,0.25); bw,bh=size[0]*w,size[1]*h
    cx,cy=pos[0]*w,pos[1]*h; draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((cx-bw/2,cy-bh/2,cx+bw/2,cy+bh/2),radius=h*theme["radius"],fill=theme["card"],
                           outline=event.get("color") or theme["accent"],width=max(1,round(h*theme["stroke"])))
    text_block(canvas,event["value"],(cx,cy-bh*.12),"statistic",theme,event.get("color") or theme["accent"],(bw*.9,bh*.55))
    if event.get("text"):
        text_block(canvas,event["text"],(cx,cy+bh*.29),"label",theme,box=(bw*.88,bh*.26))


def draw_annotation(canvas,event,theme,time):
    w,h=canvas.size; draw=ImageDraw.Draw(canvas)
    color=event.get("color") or theme["accent"]; width=max(2,round(h*theme["stroke"]))
    if event["type"] in ("line","arrow"):
        points=[(p[0]*w,p[1]*h) for p in event["points"]]
        if event["type"]=="arrow": arrow(draw,points,color,width,h*theme["arrow_head"])
        else: draw.line(points,fill=color,width=width,joint="curve")
    else:
        x,y=event["position"]; sw,sh=event["size"]
        box=((x-sw/2)*w,(y-sh/2)*h,(x+sw/2)*w,(y+sh/2)*h)
        if event["type"]=="circle": draw.ellipse(box,outline=color,width=width)
        else: draw.rounded_rectangle(box,radius=h*theme["radius"],fill=color[:7]+"35",outline=color,width=width)


def draw_diagram(canvas,event,theme,time):
    w,h=canvas.size; draw=ImageDraw.Draw(canvas)
    nodes={node["id"]:node for node in event["nodes"]}
    color=event.get("color") or theme["accent"]
    bw,bh=w*theme["diagram_node_size"][0],h*theme["diagram_node_size"][1]
    for edge in event["edges"]:
        a=nodes[edge["source"]]["position"]; b=nodes[edge["target"]]["position"]
        dx,dy=(b[0]-a[0])*w,(b[1]-a[1])*h
        boundary=min(bw/2/max(abs(dx),1e-9),bh/2/max(abs(dy),1e-9),.45)
        points=[(a[0]*w+dx*boundary,a[1]*h+dy*boundary),(b[0]*w-dx*boundary,b[1]*h-dy*boundary)]
        arrow(draw,points,color,max(2,round(h*theme["stroke"])),h*theme["arrow_head"])
        if edge.get("label"):
            label_width=min(w*theme["diagram_label_size"][0],math.hypot(dx,dy)*.4)
            text_block(canvas,edge["label"],((a[0]+b[0])*w/2,(a[1]+b[1])*h/2-h*.025),"label",theme,box=(label_width,h*theme["diagram_label_size"][1]),card=True)
    for node in nodes.values():
        x,y=node["position"][0]*w,node["position"][1]*h
        draw.rounded_rectangle((x-bw/2,y-bh/2,x+bw/2,y+bh/2),radius=h*theme["radius"],fill=theme["card"],outline=color,width=2)
        text_block(canvas,node["label"],(x,y),"label",theme,box=(bw*.9,bh*.8))


def draw_background(canvas,event,theme,time):
    canvas.paste(event.get("color") or theme["background"],(0,0,canvas.width,canvas.height))


PRIMITIVES={"show_text":draw_text,"headline":draw_text,"label":draw_text,"statistic":draw_statistic,
            "arrow":draw_annotation,"line":draw_annotation,"circle":draw_annotation,"highlight":draw_annotation,
            "diagram":draw_diagram,"background":draw_background}


class Compositor:
    def __init__(self, plan: dict, sources: dict[str,Path], size, fps, fit="cover", previous=None):
        self.plan,self.size,self.fps,self.fit=plan,size,fps,fit
        self.theme=plan["theme"];self.previous=previous
        self.sources=sources;self.images=OrderedDict()
        self.previous_shots=OrderedDict()

    def load_image(self,asset):
        if asset in self.images:
            self.images.move_to_end(asset);return self.images[asset]
        with Image.open(self.sources[asset]) as source:
            image=source.convert("RGB")
        self.images[asset]=image
        while len(self.images)>3:self.images.popitem(last=False)
        return image

    def shot(self,event,time,size):
        source=self.load_image(event["asset"]); x,y,w,h=camera_rect(self.plan,event,time)
        # Crop coordinates refer to the original source, before output fitting.
        cropped=source.crop((x*source.width,y*source.height,(x+w)*source.width,(y+h)*source.height))
        if self.fit=="cover": return ImageOps.fit(cropped,size,Image.Resampling.BICUBIC)
        result=Image.new("RGB",size,self.theme["background"])
        fitted=ImageOps.contain(cropped,size,Image.Resampling.BICUBIC)
        result.paste(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
        return result

    def image_layer(self,event,time):
        w,h=self.size; pos=event.get("position") or (0.5,0.5); size=event.get("size") or (1,1)
        shot_size=(max(1,round(w*size[0])),max(1,round(h*size[1])))
        shot=self.shot(event,time,shot_size)
        transition=event["transition"]; p=(time-event["start"])/max(1e-9,transition["duration"])
        if transition["type"]!="cut" and p<1:
            key=(event["index"],shot_size)
            if key not in self.previous_shots:
                previous=[e for e in self.plan["events"] if e["type"]=="show_image" and e["z"]==event["z"] and
                          e["layer"]==event["layer"] and e["end"]<=event["start"]+0.000001]
                previous=max(previous,key=lambda e:e["end"]) if previous else None
                old=self.shot(previous,max(previous["start"],previous["end"]-1/self.fps),shot_size) if previous else Image.new("RGB",shot_size,self.theme["background"])
                self.previous_shots[key]=old
                while len(self.previous_shots)>3:self.previous_shots.popitem(last=False)
            self.previous_shots.move_to_end(key)
            shot=apply_transition(self.previous_shots[key],shot,transition,p)
        layer=Image.new("RGBA",self.size)
        layer.paste(shot,(round(pos[0]*w-shot_size[0]/2),round(pos[1]*h-shot_size[1]/2)))
        return layer

    def frame(self,time,scene_transition=True):
        result=Image.new("RGBA",self.size,self.theme["background"])
        for event in self.plan["events"]:
            if event["type"] in CAMERA_EVENTS or not event["start"]<=time<event["end"]: continue
            if event["type"]=="show_image":
                layer=self.image_layer(event,time)
            else:
                layer=Image.new("RGBA",self.size)
                PRIMITIVES[event["type"]](layer,event,self.theme,time)
                p=ease((time-event["start"])/self.theme["animation_duration"])
                animation=event.get("animation","none")
                if animation in ("fade","pop","slide_up") and p<1:
                    layer.putalpha(layer.getchannel("A").point(lambda a:round(a*p)))
                    if animation=="pop":
                        scale=.82+.18*p; scaled=layer.resize((max(1,round(self.size[0]*scale)),max(1,round(self.size[1]*scale))),Image.Resampling.BICUBIC)
                        layer=Image.new("RGBA",self.size);layer.paste(scaled,((self.size[0]-scaled.width)//2,(self.size[1]-scaled.height)//2))
                    elif animation=="slide_up":
                        shifted=Image.new("RGBA",self.size);shifted.paste(layer,(0,round(self.size[1]*.025*(1-p))));layer=shifted
            result.alpha_composite(layer)
        result=result.convert("RGB")
        spec=self.plan["transition"]
        if scene_transition and self.previous is not None and spec["type"]!="cut" and time<spec["duration"]:
            result=apply_transition(self.previous,result,spec,time/spec["duration"])
        return result

    def frames(self,count):
        for index in range(count):
            yield self.frame(min(index/self.fps,self.plan["duration"]-1e-9))
