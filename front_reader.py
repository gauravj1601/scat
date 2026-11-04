"""Extract filled letters and roll-number bubbles from the supplied fixed OMR front.

Marked rows are independent of Tesseract's ability to recognize handwriting.
Tesseract is only used to locate the *printed* 'Roll No.' caption.
All extracted fields must be confirmed by the operator.
"""
from __future__ import annotations
from dataclasses import dataclass,field
import re
import cv2
import numpy as np
from omr_engine import _score_patch,red_mask

@dataclass
class FrontInfo:
    name: str=''
    roll_number: str=''
    alerts: list[str]=field(default_factory=list)
    name_raw: list[str]=field(default_factory=list)
    roll_raw: list[str]=field(default_factory=list)


def _find_roll_heading(image):
    try:
        import pytesseract
        small=image[int(image.shape[0]*.11):int(image.shape[0]*.24),int(image.shape[1]*.42):int(image.shape[1]*.72)]
        result=pytesseract.image_to_data(small,config='--psm 11',output_type=pytesseract.Output.DICT)
        for i,t in enumerate(result['text']):
            if re.fullmatch('roll',t.strip(),re.I):
                return int(result['top'][i])+int(image.shape[0]*.11)
    except Exception:
        pass
    return None


def read_front(image:np.ndarray, shift:int=0)->FrontInfo:
    H,W=image.shape[:2]
    out=FrontInfo()
    if W/H<.4 or W/H>.85:
        out.alerts.append('Expected a portrait full-page photo.')
        return out
    label_y=_find_roll_heading(image)
    if label_y is None:
        out.alerts.append('Could not locate printed Roll No. heading. Enter/verify student details manually.')
        return out
    label_y+=shift
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    dark=cv2.boxFilter((gray<125).astype(np.float32),-1,(7,7))
    scale=W/900
    # Roll grid is fixed on paper but shifts and compresses slightly in
    # phone photos. Locate its 8 x 10 marks instead of assuming x=420px.
    fits=[]
    for x0 in range(int(390*scale),int(439*scale),max(1,int(2*scale))):
        for dx in (24,24.5,25,25.5,26,26.5,27,27.5):
            xs=np.rint(x0+dx*scale*np.arange(8)).astype(int)
            if xs[-1]>=W:continue
            for y0 in range(label_y+34,label_y+67,2):
                for dy in (12.5,13,13.5,14,14.5,15):
                    ys=np.rint(y0+dy*np.arange(10)).astype(int)
                    if ys[-1]>=H:continue
                    v=dark[ys[:,None],xs[None,:]].T
                    ranked=np.sort(v,axis=1)
                    maxima=ranked[:,-1]
                    second=ranked[:,-2]
                    objective=float(np.minimum(1,maxima).sum()
                        - 2*np.maximum(0,second-.42).sum()
                        - 1.7*np.maximum(0,.67-maxima).sum())
                    # Upper digit boxes anchor the grid. Perspective changes
                    # its y-offset along with its horizontal displacement.
                    expected=label_y+52-.55*(420-x0/scale)
                    objective-=.12*abs(y0-expected)
                    fits.append((objective,x0,dx,y0,dy,v))
    if not fits:
        out.alerts.append('Roll-number grid could not be located; confirm manually.')
        return out
    best=max(fits,key=lambda item:item[0])
    _,rx,rdx,ry,rdy,grid=best
    raw=[]
    for column in grid:
        order=np.argsort(column)
        digit=int(order[-1])
        raw.append(str(digit) if column[digit]>.65 and column[order[-2]]<.45 else '?')
    out.roll_raw=raw
    if '?' not in raw:
        out.roll_number=''.join(raw)
    else:
        out.alerts.append('One or more roll number columns were not confidently marked.')
    # Detect first printed name bubble x from the red 26 x 22 bubble grid.
    m=red_mask(image)
    hist=m[max(0,label_y+65):min(H,label_y+365),int(60*scale):int(110*scale)].sum(axis=0)
    # First circle is around 72px (photo 1) or 88px (photo 2).
    x0_candidates=np.arange(int(68*scale),min(W,int(96*scale)))
    if len(x0_candidates):
        local=hist[x0_candidates-int(60*scale)]
        x0=float(x0_candidates[int(np.argmax(local))])
    else:
        x0=75*scale
    # 22 printed letter positions; the final bubble is near x=393 (900px reference).
    step=((393*scale)-x0)/21
    nameletters=[]
    for i in range(22):
        x=x0+step*i
        scores=[_score_patch(dark,x,label_y+46+14.55*j,4,5)[0] for j in range(26)]
        matches=[j for j,s in enumerate(scores) if s>.72]
        nameletters.append(chr(ord('A')+matches[0]) if len(matches)==1 else ('?' if len(matches)>1 else ' '))
    out.name_raw=nameletters
    name=''.join(nameletters).strip()
    name=re.sub(r'\s+',' ',name)
    if name and '?' not in name:
        out.name=name
    else:
        out.alerts.append('Student name bubble readings were incomplete or ambiguous; confirm manually.')
    return out
