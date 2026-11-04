"""R8.1-inspired timing-rail photo reader for the fixed Sri Chaitanya OMR.

It uses the edge registration bars to rectify the page and then the printed
5-question row separators for vertical correction. It is independent of the
primary pink-grid reader, so disagreements are flagged for human review.
"""
from __future__ import annotations
import cv2
import numpy as np
from omr_engine import Scan, GridNotFound

REF_W, REF_H = 1653, 2338
# Coordinates calibrated in the old, successful YSTT rail-grid scanner.
ANSWER_X = [[166,212,257,301],[560,606,651,695],
            [961,1006,1052,1096],[1397,1443,1489,1534]]
LEFT=(49.739041142679284,0.05607905298586524,101.01217688339575,28.047112125020032)
RIGHT=(1604.9491355970667,0.0956747765691419,69.0698336700528,27.97433684949856)


def _find_rail(gray, side):
    h,w=gray.shape
    black=(gray<140).astype('uint8')
    n,_,stats,centroids=cv2.connectedComponentsWithStats(black,8)
    found=[]
    sx=w/900.;sy=h/1600.
    for i,(x,y,ww,hh,area) in enumerate(stats[1:],1):
        at_edge=(.008*w<x<.17*w) if side=='left' else (.83*w<x<.997*w)
        if (at_edge and .085*h<y<.955*h and
            8*sx<=ww<=29*sx and 2*sy<=hh<=13*sy and area>=23*sx*sy):
            found.append((float(centroids[i][0]),float(centroids[i][1])))
    if len(found)<55:
        raise GridNotFound('Registration marks not detected; retake photo with the page edges visible.')
    pts=np.array(found)
    # Robustly fit the mostly-vertical black rail, excluding unrelated marks.
    best=np.zeros(0,dtype=int)
    rng=np.random.default_rng(13)
    for _ in range(500):
        a,b=rng.choice(len(pts),size=2,replace=False)
        if abs(pts[a,1]-pts[b,1])<.18*h:continue
        slope=(pts[a,0]-pts[b,0])/(pts[a,1]-pts[b,1])
        if abs(slope)>.20:continue
        zero=pts[a,0]-slope*pts[a,1]
        keep=np.where(np.abs(pts[:,0]-slope*pts[:,1]-zero)<5*sx)[0]
        if len(keep)>len(best):best=keep
    if len(best)<65:
        raise GridNotFound('Insufficient registration marks to align OMR.')
    rail=pts[best]
    for _ in range(3):
        coeff=np.polyfit(rail[:,1],rail[:,0],1)
        rail=rail[np.abs(rail[:,0]-np.polyval(coeff,rail[:,1]))<4*sx]
    rail=rail[np.argsort(rail[:,1])]
    return [(float(a),float(b)) for a,b in rail]


def _complete(rail, expected, other, our_ref, other_ref):
    if len(rail)==expected:return rail
    if len(rail)!=expected-1 or len(other)<len(rail)-2:
        raise GridNotFound('Registration bars are missing or obscured; retake the photo.')
    # Determine whether the missing bar belongs to the top or bottom.
    pitch=np.median(np.diff([p[1] for p in rail]))
    opitch=np.median(np.diff([p[1] for p in other]))
    expected_top=(our_ref[2]-other_ref[2])*pitch/our_ref[3]
    observed_top=rail[0][1]-other[0][1]
    expected_bottom=((our_ref[2]+our_ref[3]*(expected-1))-
        (other_ref[2]+other_ref[3]*(len(other)-1)))*pitch/our_ref[3]
    observed_bottom=rail[-1][1]-other[-1][1]
    from_top=abs(expected_top-observed_top)>abs(expected_bottom-observed_bottom)
    subset=np.array(rail[:12] if from_top else rail[-12:])
    ids=np.arange(len(subset),dtype=float)
    xcoeff=np.polyfit(ids,subset[:,0],1)
    ycoeff=np.polyfit(ids,subset[:,1],1)
    index=-1 if from_top else len(subset)
    inserted=(float(np.polyval(xcoeff,index)),float(np.polyval(ycoeff,index)))
    return [inserted]+rail if from_top else rail+[inserted]


def _rails(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    left=_find_rail(gray,'left')
    right=_find_rail(gray,'right')
    # Fail closed rather than choose an arbitrary subsequence of rails.
    if len(left)>78 or len(right)>80:
        raise GridNotFound('Extra registration marks detected; photo needs review.')
    left=_complete(left,78,right,LEFT,RIGHT)
    right=_complete(right,80,left,RIGHT,LEFT)
    if len(left)!=78 or len(right)!=80:
        raise GridNotFound('Registration marks are incomplete.')
    for rail in (left,right):
        diff=np.diff([p[1] for p in rail]); med=np.median(diff)
        if med<=0 or np.max(abs(diff-med))>med*.48:
            raise GridNotFound('Registration marks are not regular enough.')
    return left,right


def _normalize(image):
    left,right=_rails(image)
    src=np.float32([left[0],left[-1],right[0],right[-1]])
    dst=np.float32([
        (LEFT[0]*900/REF_W,LEFT[2]*1600/REF_H),
        ((LEFT[0]+LEFT[1]*77)*900/REF_W,(LEFT[2]+LEFT[3]*77)*1600/REF_H),
        (RIGHT[0]*900/REF_W,RIGHT[2]*1600/REF_H),
        ((RIGHT[0]+RIGHT[1]*79)*900/REF_W,(RIGHT[2]+RIGHT[3]*79)*1600/REF_H),
    ])
    transform=cv2.getPerspectiveTransform(src,dst)
    return cv2.warpPerspective(image,transform,(900,1600),borderValue=(255,255,255))


def _row_bounds(image):
    b,g,r=cv2.split(image.astype('int16'))
    magenta=((r-g>7)&(r-b>6)&(g>20)).astype('uint8')
    strength=magenta[:,50:181].sum(axis=1)
    # Strong horizontal dividers are approximately 115px apart after rectification.
    bounds=[]
    for i in range(9):
        target=299+i*115.3
        ylo=max(0,int(target-32)); yhi=min(1600,int(target+32))
        y=ylo+int(np.argmax(strength[ylo:yhi]))
        if strength[y]<62 or (bounds and not 95<y-bounds[-1]<137):
            raise GridNotFound('Answer row separators not aligned after deskew.')
        bounds.append(y)
    return [2*bounds[0]-bounds[1]]+bounds


def scan_rail_photo(image, question_count=50):
    if not 1<=question_count<=180:raise ValueError('OMR supports 1–180 questions.')
    aligned=_normalize(image)
    bounds=_row_bounds(aligned)
    gray=cv2.cvtColor(aligned,cv2.COLOR_BGR2GRAY)
    dark=(gray<140).astype('uint8')
    answers={};confidence={};scores={};marked={}
    overlay=aligned.copy()
    for q in range(1,question_count+1):
        block=(q-1)//45;local=(q-1)%45;group=local//5;row=local%5
        y=bounds[group]+(bounds[group+1]-bounds[group])*(row+1)/6
        sc=[]
        for xref in ANSWER_X[block]:
            x=xref*900/REF_W; xx=int(round(x));yy=int(round(y))
            # A 3-pixel local adjustment compensates residual lens/perspective
            # distortion without drifting into an adjacent bubble (23px away).
            best_fill=0.0
            for dy in (-3,0,3):
                for dx in (-3,0,3):
                    patch=dark[max(0,yy+dy-4):min(1600,yy+dy+5),
                               max(0,xx+dx-4):min(900,xx+dx+5)]
                    if patch.size:best_fill=max(best_fill,float(patch.mean()))
            sc.append(round(best_fill,4))
        order=np.argsort(sc)[::-1];best=int(order[0]);second=int(order[1])
        if sc[best]<.39:value=''
        elif sc[best]-sc[second]<=.15:value='UNREADABLE'
        else:value='ABCD'[best]
        answers[q]=value
        scores[q]=sc
        confidence[q]=round(max(0.,min(1.,sc[best]-sc[second] if value else 1-sc[best])),3)
        marked[q]=[value] if value in 'ABCD' and value else []
        for j,xref in enumerate(ANSWER_X[block]):
            x=int(round(xref*900/REF_W))
            c=(45,190,45) if value=='ABCD'[j] else (0,190,255) if value=='UNREADABLE' else (160,140,130)
            cv2.circle(overlay,(x,int(round(y))),5,c,1)
    return Scan(answers,confidence,scores,marked,aligned,overlay,[float(v) for v in bounds])
