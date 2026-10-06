"""Reusable frame transitions. Incoming frames occupy existing timeline time."""
import math
from PIL import Image, ImageFilter


def zoom_frame(frame: Image.Image, scale: float, target=(0.5, 0.5)) -> Image.Image:
    w, h = frame.size
    cw, ch = w/scale, h/scale
    x = max(0, min(w-cw, target[0]*w-cw/2))
    y = max(0, min(h-ch, target[1]*h-ch/2))
    return frame.transform((w,h), Image.Transform.EXTENT, (x,y,x+cw,y+ch), Image.Resampling.BICUBIC)


def cut(old, new, p, target): return new.copy()
def crossfade(old, new, p, target): return Image.blend(old, new, p)


def slide(old, new, p, direction, whip=False):
    w,h=new.size
    progress = 1-(1-p)**3 if whip else p
    distance = round(w*progress)
    result = Image.new("RGB", (w,h))
    if direction == "left":
        result.paste(old, (-distance,0)); result.paste(new, (w-distance,0))
    else:
        result.paste(old, (distance,0)); result.paste(new, (distance-w,0))
    if whip and 0<p<1:
        # Directional smear: blend shifted samples, retaining a distinct
        # horizontal whip rather than substituting a normal crossfade.
        radius = round(w*0.035*math.sin(math.pi*p))
        smeared=result.copy()
        for offset in (-radius, radius):
            sample=result.copy(); sample.paste(result,(offset,0))
            smeared=Image.blend(smeared,sample,0.3)
        return smeared
    return result


def zoom_in(old, new, p, target):
    return Image.blend(zoom_frame(old,1+0.5*p,target), zoom_frame(new,1.5-0.5*p,target),p)


def zoom_out(old, new, p, target):
    scale=1-.6*p
    small=old.resize((max(1,round(old.width*scale)),max(1,round(old.height*scale))),Image.Resampling.BICUBIC)
    outgoing=new.copy()
    outgoing.paste(small,(round(target[0]*old.width*(1-scale)),round(target[1]*old.height*(1-scale))))
    return Image.blend(outgoing,new,p)


def zoom_through(old, new, p, target):
    incoming=zoom_frame(new,1+2*(1-p),target)
    outgoing=zoom_frame(old,1+5*p*p,target)
    return Image.blend(outgoing,incoming,p*p*(3-2*p))


def blur(old, new, p, target):
    mixed=Image.blend(old,new,p)
    return mixed.filter(ImageFilter.GaussianBlur(min(new.size)*0.022*math.sin(math.pi*p)))


TRANSITIONS = {
    "cut": cut, "crossfade": crossfade,
    "slide_left": lambda a,b,p,t: slide(a,b,p,"left"),
    "slide_right": lambda a,b,p,t: slide(a,b,p,"right"),
    "zoom_in": zoom_in, "zoom_out": zoom_out, "zoom_through": zoom_through,
    "whip_left": lambda a,b,p,t: slide(a,b,p,"left",True),
    "whip_right": lambda a,b,p,t: slide(a,b,p,"right",True), "blur": blur,
}


def apply_transition(old, new, spec, progress):
    kind=spec["type"]
    if kind not in TRANSITIONS: raise ValueError(f"Transizione non supportata: {kind}")
    if progress <= 0: return old.copy() if kind != "cut" else new.copy()
    if progress >= 1: return new.copy()
    return TRANSITIONS[kind](old,new,float(progress),spec.get("target",(0.5,0.5)))
