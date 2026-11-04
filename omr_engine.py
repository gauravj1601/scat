"""Sri Chaitanya fixed-format OMR reader. The image is never sent to a server.

Geometry derives from the colored printed answer-grid dividers, not hardcoded
image y positions. Values marked UNREADABLE/MULTIPLE need human review.
"""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np

CHOICES = 'ABCD'


class GridNotFound(ValueError):
    pass


@dataclass
class Scan:
    answers: dict[int, str]
    confidence: dict[int, float]
    scores: dict[int, list[float]]
    marked: dict[int, list[str]]
    image: np.ndarray
    preview: np.ndarray
    lines: list[float]


def decode_image(blob: bytes, rotate: int = 0, target_height: int = 1600) -> np.ndarray:
    data = np.frombuffer(blob, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Unable to decode image. Upload JPEG or PNG.')
    if rotate:
        turns = (rotate // 90) % 4
        image = np.rot90(image, turns).copy()  # counterclockwise
    if image.shape[0] < 400 or image.shape[1] < 300:
        raise ValueError('Image resolution is too low.')
    scale = target_height / image.shape[0]
    return cv2.resize(image, (int(round(image.shape[1]*scale)), target_height), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)


def red_mask(image):
    # The printed SCAT OMR grid is pink/magenta. Avoid relying on dark marks.
    b, g, r = cv2.split(image.astype(np.int16))
    return ((r > g + 12) & (r > b + 10) & (r > 80) & (g > 35)).astype(np.uint8)


def _line_runs(mask, y, x0, x1, min_run):
    y = int(round(y)); height, width = mask.shape
    if y < 2 or y >= height-2:
        return []
    x0=max(0,int(x0)); x1=min(width,int(x1))
    q=mask[y-2:y+3,x0:x1].sum(axis=0)
    inds=np.flatnonzero(q>=2)
    if not len(inds):return []
    chunks=np.split(inds,np.where(np.diff(inds)>1)[0]+1)
    return [(x0+int(c[0]), x0+int(c[-1]),len(c)) for c in chunks if len(c)>=min_run]


def locate_grid(image):
    """Locate the fixed SCAT 5-row dividers despite faded pink ink and perspective.

    The original detector searched for straight, equally spaced grid lines.
    A photo angled relative to the camera compresses the first few rows and
    expands the lower rows; faint magenta lines may disappear at the strict
    red threshold. We instead recover an ordered set of nine dividers and
    interpolate/extrapolate local row spacing.
    """
    H,W=image.shape[:2]
    if not .40 <= W/H <= .83:
        raise GridNotFound('Please upload a portrait photograph showing the whole OMR.')
    b,g,r=cv2.split(image.astype(np.int16))
    candidates=[]
    # Try increasingly relaxed colour contrast to accommodate different
    # indoor lighting/phone cameras. Exclude nearly white pixels.
    for chroma in (6,4,2):
        mask=((r>g+chroma)&(r>b+chroma)&(r>74)&(g>28)).astype(np.uint8)
        detected=[]
        for y in range(int(H*.15),int(H*.735)):
            runs=_line_runs(mask,y,W*.065,W*.275,int(W*.074))
            if runs:
                x0,x1,n=max(runs,key=lambda a:a[2])
                detected.append((y,x0,x1,n))
        groups=[]
        batch=[]
        for row in detected:
            if batch and row[0]-batch[-1][0]>1:
                arr=np.asarray(batch,dtype=float)
                groups.append((float(np.median(arr[:,0])),float(np.median(arr[:,1])),float(np.median(arr[:,2]))))
                batch=[]
            batch.append(row)
        if batch:
            arr=np.asarray(batch,dtype=float)
            groups.append((float(np.median(arr[:,0])),float(np.median(arr[:,1])),float(np.median(arr[:,2]))))
        # Find nine consecutive 5-question row dividers with slowly varying
        # gaps. This rejects the long banner border and signature boxes.
        lo,hi=(67*H/1600,101*H/1600)
        def walk(path):
            if len(path)>=9:
                candidates.append((path,groups,mask))
                return
            for idx in range(path[-1]+1,len(groups)):
                gap=groups[idx][0]-groups[path[-1]][0]
                if gap<lo:continue
                if gap>hi:break
                if len(path)>=2:
                    prior=groups[path[-1]][0]-groups[path[-2]][0]
                    if abs(gap-prior)>8.5*H/1600:continue
                walk(path+[idx])
        for st,grp in enumerate(groups):
            if .195*H <= grp[0] <= .32*H:
                walk([st])
        if candidates:
            break
    if not candidates:
        raise GridNotFound('Pink answer grid could not be aligned. Try a brighter photo taken directly above the page, with no cropping.')
    def rank(item):
        path,groups,_=item
        seq=[groups[i] for i in path]
        gaps=np.diff([t[0] for t in seq])
        widths=np.asarray([t[2]-t[1] for t in seq])
        # Prefer a smooth grid that is close to the expected first-column
        # rectangle dimensions (and whose width doesn't vary erratically).
        return -(float(np.std(np.diff(gaps)))*2 + float(np.std(widths))*.12 + abs(float(np.median(gaps))-87*H/1600)*.15)
    ids,groups,mask=max(candidates,key=rank)
    seq=[groups[i] for i in ids]
    ys=np.asarray([q[0] for q in seq],dtype=float)
    gaps=np.diff(ys)
    # A quadratic mapping handles mild vertical perspective (gaps not constant).
    yfirst=ys[0]-float(gaps[0]-(gaps[1]-gaps[0])) if len(gaps)>=2 else ys[0]-float(gaps[0])
    y_bounds=[float(yfirst)]+[float(v) for v in ys]
    left_fit=np.polyfit(ys,np.array([q[1] for q in seq]),1)
    right_fit=np.polyfit(ys,np.array([q[2] for q in seq]),1)
    lefts=[float(np.polyval(left_fit,seq[0][0]))]
    for col in (1,2,3):
        typical_left=[.32,.55,.79][col-1]*W
        points=[]
        for yy,*_ in seq[:min(6,len(seq))]:
            runs=_line_runs(mask,yy,typical_left-W*.07,typical_left+W*.15,int(W*.057))
            if runs:
                near=min(runs,key=lambda g:abs(g[0]-typical_left))
                if abs(near[0]-typical_left)<W*.075:points.append(near[0])
        lefts.append(float(np.median(points)) if points else
                     [lefts[0]+204*W/900,lefts[0]+405*W/900,lefts[0]+620*W/900][col-1])
    return y_bounds,left_fit,right_fit,lefts,float(np.median(gaps)),image


def _score_patch(dark_fraction,x,y,x_range=6,y_range=4):
    H,W=dark_fraction.shape
    x=int(round(x));y=int(round(y))
    xa=max(0,x-x_range);xb=min(W,x+x_range+1)
    ya=max(0,y-y_range);yb=min(H,y+y_range+1)
    if xa>=xb or ya>=yb:return 0.,(x,y)
    roi=dark_fraction[ya:yb,xa:xb]
    p=np.unravel_index(int(np.argmax(roi)),roi.shape)
    return float(roi[p]),(xa+int(p[1]),ya+int(p[0]))


def scan_answers(image:np.ndarray, question_count:int=50, threshold:float=.70)->Scan:
    if not 1<=question_count<=180:
        raise ValueError('OMR allows 1–180 questions')
    ybounds,left_fit,right_fit,lefts,period,im=locate_grid(image)
    H,W=im.shape[:2]
    gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
    # Filled dark bubbles are close to black; printed empty pink outlines are lighter.
    dark=np.uint8(gray<126)
    dark_fraction=cv2.boxFilter(dark.astype(np.float32),-1,(7,7),normalize=True)
    answers={}; conf={};scores={};marked={}
    overlay=im.copy()
    for q in range(1,question_count+1):
        col=(q-1)//45
        position=(q-1)%45
        group=position//5
        row=position%5
        y=ybounds[group] +(ybounds[group+1]-ybounds[group])*(row+1)/6.0
        left=float(np.polyval(left_fit,y)) if col==0 else lefts[col]+float(np.polyval(left_fit,y))-lefts[0]
        # Front of form has nonuniform column widths; use calibrated offsets.
        offsets=[30,54,78,102] if col==0 else [30,52,74,98]
        option_x=[left+a*(W/900.) for a in offsets]
        sc=[];points=[]
        for x in option_x:
            s,p=_score_patch(dark_fraction,x,y,max(3,int(6*W/900)),4)
            sc.append(round(s,4));points.append(p)
        selected=[CHOICES[i] for i,v in enumerate(sc) if v>=threshold]
        if len(selected)==1:
            answer=selected[0];score=sc[CHOICES.index(answer)]
        elif len(selected)>1:
            answer='MULTIPLE';score=max(sc)
        else:
            answer='' if max(sc)<.42 else 'UNREADABLE'
            score=1-max(sc) if not answer else max(sc)
        answers[q]=answer;conf[q]=round(float(score),3); scores[q]=sc;marked[q]=selected
        for opt,loc in enumerate(points):
            rgb=(30,165,40) if answer==CHOICES[opt] else ((0,140,235) if answer in ('UNREADABLE','MULTIPLE') else (180,120,100))
            cv2.circle(overlay,loc,5,rgb,1)
        if answer in ('UNREADABLE','MULTIPLE'):
            cv2.putText(overlay,f'Q{q}',(max(0,int(option_x[0]-30)),int(y+5)),cv2.FONT_HERSHEY_SIMPLEX,.35,(0,0,255),1)
    return Scan(answers,conf,scores,marked,im,overlay,[float(v) for v in ybounds])


def preview_jpeg(image:np.ndarray, max_width:int=950)->bytes:
    H,W=image.shape[:2]
    if W>max_width:image=cv2.resize(image,(max_width,int(H*max_width/W)))
    ok,data=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,82])
    if not ok:raise ValueError('Unable to encode preview')
    return data.tobytes()
