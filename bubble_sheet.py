"""Create a numbered visual crop sheet, from OMR geometry, for an independent
second bubble classification. Never supply Python's detected answers or key.
"""
from __future__ import annotations
import io
import cv2
import numpy as np
from PIL import Image
from omr_engine import locate_grid, GridNotFound
from template_alignment import locate_template_centers


def make_bubble_sheet(back_image: np.ndarray, question_count: int, questions=None) -> bytes:
    """Return PNG contact sheet: each row Q# and 1(A),2(B),3(C),4(D).

    Each bubble is cropped from the source photo, then enlarged. The image does
    not show the Python decision or the correct answer. Geometry is shared for
    localisation only, so the verifier is independent in classification, not
    in image registration.
    """
    im=back_image
    H, W = im.shape[:2]
    try:
        ybounds, left_fit, _, lefts, _, _ = locate_grid(back_image)
        template_centers=None
    except GridNotFound:
        # The independent AI still receives only enlarged photograph crops.
        # It does not receive the Python-marked answers or answer key.
        template_centers,_ = locate_template_centers(back_image,question_count)
    qs = list(questions) if questions is not None else list(range(1, question_count + 1))
    if not qs or any(not 1 <= q <= 180 for q in qs):
        raise ValueError('Invalid question selection')
    # One image, five columns, maximum ten rows for a 50-question paper.
    cols = min(5, max(1, (len(qs) + 9) // 10))
    rows = (len(qs) + cols - 1) // cols
    tile_w, tile_h, chip = 350, 75, 47
    out = np.full((40 + rows * tile_h, cols * tile_w, 3), 255, np.uint8)
    cv2.putText(out, 'Filled bubble: 1=A  2=B  3=C  4=D  |  empty = blank', (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX, .56, (20, 20, 20), 2, cv2.LINE_AA)
    for k, q in enumerate(qs):
        col, row = divmod(k, rows)
        bx, by = col * tile_w, 40 + row * tile_h
        cv2.putText(out, f'Q{q:02d}', (bx + 8, by + 43),
                    cv2.FONT_HERSHEY_SIMPLEX, .60, (10, 10, 10), 2, cv2.LINE_AA)
        block = (q-1)//45
        local = (q-1)%45
        if template_centers is None:
            group, r = divmod(local, 5)
            yy = ybounds[group] + (ybounds[group+1]-ybounds[group]) * (r+1)/6.
            left = float(np.polyval(left_fit, yy)) if block == 0 else lefts[block] + float(np.polyval(left_fit, yy)) - lefts[0]
            offsets = [30,54,78,102] if block == 0 else [30,52,74,98]
            locations=[(left+ofs*(W/900.),yy) for ofs in offsets]
        else:
            locations=template_centers[q-1]
        for i, (xx,yy) in enumerate(locations):
            cx, cy = int(round(xx)), int(round(yy))
            half = max(6, int(round(7.5*W/900.)))
            xa, xb = max(0,cx-half), min(W,cx+half+1)
            ya, yb = max(0,cy-half), min(H,cy+half+1)
            crop = im[ya:yb,xa:xb]
            if crop.size:
                # Preserve bubble red rings and filled black ink.
                crop = cv2.resize(crop,(chip,chip),interpolation=cv2.INTER_CUBIC)
                dx = bx + 66 + i*69
                dy = by + 15
                out[dy:dy+chip,dx:dx+chip] = crop
                cv2.rectangle(out, (dx,dy), (dx+chip,dy+chip), (160,160,160), 1)
                cv2.putText(out, str(i+1), (dx+17,dy+chip+11),
                            cv2.FONT_HERSHEY_SIMPLEX,.30,(45,45,45),1,cv2.LINE_AA)
    rgb = cv2.cvtColor(out,cv2.COLOR_BGR2RGB)
    b=io.BytesIO()
    Image.fromarray(rgb).save(b,format='PNG')
    return b.getvalue()
