import numpy as np, cv2
from PIL import Image
from scipy import ndimage
def matte(rgb, bg=None, lo=8.0, hi=24.0, erode=1):
    I = rgb.astype(np.float32)
    if bg is None:
        b = np.concatenate([I[:6].reshape(-1,3), I[-6:].reshape(-1,3), I[:, :6].reshape(-1,3), I[:, -6:].reshape(-1,3)])
        bg = np.median(b, 0)
    # backdrop is one flat colour: score = distance from it in brightness and in warmth (R-B), measured per channel
    L = I.mean(2); Lb = bg.mean(); rbb = bg[0] - bg[2]
    s = 1.6 * np.maximum(np.abs(L - Lb) - 2.5, 0) + 2.2 * np.maximum(np.abs((I[..., 0] - I[..., 2]) - rbb) - 2.5, 0) \
        + 1.0 * np.maximum(np.abs(I[..., 1] - I[..., 2] - (bg[1] - bg[2])) - 3, 0)
    a = np.clip((s - lo) / (hi - lo), 0, 1)
    # background = low-score region connected to the frame border; enclosed low-score holes stay opaque
    low = s < hi
    lab, n = ndimage.label(low)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bgreg = np.isin(lab, border[border > 0])
    # enclosed pockets (e.g. between the curled tail and the back) whose colour matches the backdrop are background too
    for i in range(1, n + 1):
        if i in border: continue
        reg = lab == i; ar = reg.sum()
        if ar > 25 and np.median(s[reg]) < 10: bgreg |= reg
    a = np.where(bgreg, a, 1.0)
    # keep only the largest foreground blob (drops compression specks)
    fg = a > 0.5; lab2, n2 = ndimage.label(fg)
    if n2 > 1:
        sizes = ndimage.sum(fg, lab2, range(1, n2 + 1)); keep = lab2 == (1 + int(np.argmax(sizes)))
        keep = ndimage.binary_dilation(keep, iterations=3); a = a * keep
    # despeckle: semi-transparent compression noise -> 0; solid core opened, then the soft edge re-attached
    core = ndimage.binary_opening(a > 0.5, iterations=2)
    holes = ndimage.binary_fill_holes(core) & ~core
    hl, hn = ndimage.label(holes)
    if hn:
        hs = ndimage.sum(holes, hl, range(1, hn + 1))
        core |= np.isin(hl, [k + 1 for k, v in enumerate(hs) if v < 40])     # only tiny holes are filled
    if erode: core = ndimage.binary_erosion(core, iterations=erode)
    near = ndimage.binary_dilation(core, iterations=2)
    a = np.where(core, 1.0, np.where(near, a, 0.0)) * (a > 0.25)
    a = cv2.GaussianBlur(a.astype(np.float32), (0, 0), 0.7)
    # colour decontamination: remove the grey that bleeds into semi-transparent fur
    A = np.maximum(a[..., None], 1e-3)
    F = np.clip((I - (1 - A) * bg) / A, 0, 255)
    F = np.where(a[..., None] > 0.98, I, F)
    out = np.dstack([F, a * 255]).astype(np.uint8); out[out[..., 3] == 0] = 0
    return out, bg
