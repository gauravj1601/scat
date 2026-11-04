"""Fixed-layout OMR photographic alignment using anonymous printed-reference crops.

Fallback for phones whose perspective/faded red grid defeats line or rail
alignment. SIFT matches printed form details to a known OMR layout; RANSAC
rejects bad feature matches. No answer key or Gemini answers are involved.

Only the ANSWER side is referenced. The supplied templates exclude all
student/invigilator signatures; the lower portion is white in both assets.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from omr_engine import Scan, GridNotFound, locate_grid

TEMPLATES = ('back_template_1.jpg', 'back_template_2.jpg')
CHOICES = 'ABCD'


def _gray(image):
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _sift():
    if not hasattr(cv2, 'SIFT_create'):
        raise GridNotFound('SIFT alignment needs OpenCV with SIFT support (opencv-python-headless >= 4.8).')
    return cv2.SIFT_create(nfeatures=5000, contrastThreshold=0.015)


def _fixed_centers(reference, question_count):
    ybounds, left_fit, _, lefts, _, _ = locate_grid(reference)
    W=reference.shape[1]
    points=[]
    for q in range(1, question_count + 1):
        col=(q - 1)//45
        group=((q - 1)%45)//5
        row=((q - 1)%45)%5
        y=ybounds[group]+(ybounds[group+1]-ybounds[group])*(row+1)/6.0
        left=float(np.polyval(left_fit,y)) if col==0 else lefts[col]+float(np.polyval(left_fit,y))-lefts[0]
        offsets=(30,54,78,102) if col==0 else (30,52,74,98)
        points.append([(left+x*W/900.0,y) for x in offsets])
    return np.asarray(points,dtype=np.float32)


@lru_cache(maxsize=1)
def _reference_data():
    detector=_sift()
    refs=[]
    for name in TEMPLATES:
        path=Path(__file__).resolve().parent/'assets'/name
        image=cv2.imread(str(path))
        if image is None:
            raise GridNotFound(f'OMR reference image is missing: {name}. Copy the assets folder from the update.')
        keypoints,descriptors=detector.detectAndCompute(_gray(image),None)
        if descriptors is None or len(keypoints)<200:
            raise GridNotFound('OMR reference image cannot be calibrated.')
        refs.append((image,keypoints,descriptors))
    return refs


def locate_template_centers(image:np.ndarray,question_count:int=50):
    """Return (centers[N,4,2], alignment report) for the uploaded BGR photo.

    Fail closed if the feature fit is weak, geometrically extreme, or doesn't
    cover the entire answer area. The returned centers are in original image
    coordinates, avoiding blur introduced by warping the student's photo.
    """
    if not 1 <= question_count <= 180:
        raise ValueError('OMR supports 1-180 questions.')
    if image.ndim != 3 or image.shape[0]<700 or image.shape[1]<400:
        raise GridNotFound('Upload an upright, full-page OMR answer photograph.')
    detector=_sift()
    points,desc=detector.detectAndCompute(_gray(image),None)
    if desc is None or len(points)<150:
        raise GridNotFound('Not enough image detail. Retake the photograph in good light.')
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    candidates=[]
    for ref_index,(ref,refpoints,refdesc) in enumerate(_reference_data()):
        matches=matcher.knnMatch(refdesc,desc,k=2)
        good=[a for a,b in matches if a.distance<0.72*b.distance]
        if len(good)<65:
            continue
        src=np.float32([refpoints[m.queryIdx].pt for m in good]).reshape(-1,1,2)
        dst=np.float32([points[m.trainIdx].pt for m in good]).reshape(-1,1,2)
        H,mask=cv2.findHomography(src,dst,cv2.RANSAC,4.0,maxIters=3500,confidence=0.997)
        if H is None or mask is None:
            continue
        inliers=mask.ravel().astype(bool)
        count=int(inliers.sum())
        # Repetitive bubbles can yield a spurious RANSAC fit. Require many
        # matched printed features spread across the actual paper area.
        if count < 38 or count/len(good) < 0.16:
            continue
        refxy=src[inliers].reshape(-1,2)
        if np.ptp(refxy[:,0])<340 or np.ptp(refxy[:,1])<370:
            continue
        canonical=_fixed_centers(ref,question_count)
        transformed=cv2.perspectiveTransform(canonical.reshape(-1,1,2),H).reshape(question_count,4,2)
        Himg,Wimg=image.shape[:2]
        if not np.isfinite(transformed).all():
            continue
        inside=((transformed[:,:,0]>18)&(transformed[:,:,0]<Wimg-18)&
                (transformed[:,:,1]>18)&(transformed[:,:,1]<Himg-18))
        if inside.mean()<.98:
            continue
        # Check that the answer grid has realistic scale and orientation.
        dx=np.diff(transformed,axis=1)
        pitches=np.linalg.norm(dx,axis=2)
        if np.median(pitches)<12 or np.median(pitches)>65:
            continue
        if np.min(dx[:,:,0]) < 5:
            continue
        candidates.append((count,transformed,ref_index,refxy))
    if not candidates:
        raise GridNotFound('Printed OMR reference could not be aligned. Keep both side rails visible, avoid shadows, and retake the photo.')
    count,centers,index,_=max(candidates,key=lambda t:t[0])
    return centers, {'template':TEMPLATES[index],'inliers':count}


def _score_all(image,centers):
    gray=_gray(image)
    black=(gray<136).astype(np.float32)
    darkness=cv2.boxFilter(black,-1,(7,7),normalize=True)
    H,W=darkness.shape
    scores=[]
    for row in centers:
        sr=[]
        for x,y in row:
            xi,yi=int(round(float(x))),int(round(float(y)))
            patch=darkness[max(0,yi-5):min(H,yi+6),max(0,xi-5):min(W,xi+6)]
            sr.append(float(patch.max()) if patch.size else 0.0)
        scores.append(sr)
    return np.asarray(scores,dtype=np.float32)


def scan_template_photo(image:np.ndarray,question_count:int=50)->Scan:
    centers,info=locate_template_centers(image,question_count)
    measurements=_score_all(image,centers)
    answers={}; confidence={}; scores={}; marked={}
    preview=image.copy()
    for index in range(question_count):
        q=index+1
        levels=[round(float(x),4) for x in measurements[index]]
        clear=[j for j,v in enumerate(levels) if v>=0.72]
        highest=max(levels)
        if len(clear)==1:
            ans=CHOICES[clear[0]]
            reliability=max(0.5,min(1.0, highest-max(v for j,v in enumerate(levels) if j!=clear[0])))
        elif len(clear)>1:
            ans='MULTIPLE'; reliability=0.0
        elif highest<0.38:
            ans=''; reliability=0.90
        else:
            ans='UNREADABLE'; reliability=0.0
        answers[q]=ans
        confidence[q]=round(float(reliability),3)
        scores[q]=levels
        marked[q]=[CHOICES[j] for j in clear]
        for j,(x,y) in enumerate(centers[index]):
            point=(int(round(float(x))),int(round(float(y))))
            color=(35,165,40) if ans==CHOICES[j] else (0,155,245) if ans in ('MULTIPLE','UNREADABLE') else (120,120,175)
            cv2.circle(preview,point,6,color,1)
        if ans in ('MULTIPLE','UNREADABLE'):
            x,y=centers[index,0]
            cv2.putText(preview,f'Q{q}',(max(0,int(x)-35),int(y)+5),cv2.FONT_HERSHEY_SIMPLEX,0.42,(0,0,255),1)
    return Scan(answers,confidence,scores,marked,image,preview,[])
