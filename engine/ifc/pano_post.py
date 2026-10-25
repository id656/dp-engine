# -*- coding: utf-8 -*-
"""Постобработка панорам: EXR (pbrt gbuffer) → PFM → OIDN → тонмаппинг (filmic) → JPEG (+ XMP GPano)."""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

import paths as _paths
PBRT = os.path.join(_paths.EXT, 'pbrt-v4', 'build')
OIDN = os.path.join(_paths.EXT, 'oidn', 'oidn-2.3.1.x86_64.linux')


def read_pfm(path):
    with open(path, 'rb') as f:
        hdr = f.readline().strip()
        w, h = map(int, f.readline().split())
        sc = float(f.readline())
        data = np.frombuffer(f.read(), dtype='<f4' if sc < 0 else '>f4')
    ch = 3 if hdr == b'PF' else 1
    return np.flipud(data.reshape(h, w, ch)).astype(np.float32)


def denoise(exr, tmp):
    it = os.path.join(PBRT, 'imgtool')
    c, a, n, d = (f'{tmp}_{s}.pfm' for s in 'cand')
    for chans, out in (('R,G,B', c), ('Albedo.R,Albedo.G,Albedo.B', a), ('Ns.X,Ns.Y,Ns.Z', n)):
        subprocess.run([it, 'convert', '--channels', chans, exr, '--outfile', out], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(OIDN, 'lib'))
    subprocess.run([os.path.join(OIDN, 'bin', 'oidnDenoise'), '--hdr', c, '--alb', a, '--nrm', n, '-o', d],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    img = read_pfm(d)
    for f in (c, a, n, d):
        os.remove(f)
    return img


def aces(x):
    a, b, c, d_, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d_) + e), 0, 1)


def auto_wb(img, strength=0.7):
    """Баланс белого по средним тонам (как камера в режиме авто, с сохранением части теплоты)."""
    lum = img.mean(-1)
    lo, hi = np.percentile(lum, 20), np.percentile(lum, 90)
    m = (lum > lo) & (lum < hi)
    c = img[m].mean(0)
    g = c.mean() / np.maximum(c, 1e-6)
    return tuple(float(x) for x in (1 + (g - 1) * strength))


def tonemap(img, key=0.18, ev=0.0, wb=None, sat=1.05, lavg=None):
    """Экспозиция по среднему логарифму яркости (без самых ярких зон — окна, лампы), ACES, sRGB."""
    lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    h = img.shape[0]
    band = lum[int(h * 0.2):int(h * 0.8)]
    v = np.clip(band, 1e-4, None)
    v = v[v < np.percentile(v, 97)]
    if lavg is None:
        lavg = float(np.exp(np.mean(np.log(v))))
    x = img * (key / lavg) * (2.0 ** ev)
    if wb is not None:
        x = x * np.array(wb, dtype=np.float32)
    m = x.mean(-1, keepdims=True)
    x = m + (x - m) * sat
    y = aces(np.clip(x, 0, None))
    srgb = np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)
    return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8), lavg


def xmp_gpano(w, h):
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:GPano="http://ns.google.com/photos/1.0/panorama/">'
        '<GPano:ProjectionType>equirectangular</GPano:ProjectionType><GPano:UsePanoramaViewer>True</GPano:UsePanoramaViewer>'
        f'<GPano:FullPanoWidthPixels>{w}</GPano:FullPanoWidthPixels><GPano:FullPanoHeightPixels>{h}</GPano:FullPanoHeightPixels>'
        f'<GPano:CroppedAreaImageWidthPixels>{w}</GPano:CroppedAreaImageWidthPixels>'
        f'<GPano:CroppedAreaImageHeightPixels>{h}</GPano:CroppedAreaImageHeightPixels>'
        '<GPano:CroppedAreaLeftPixels>0</GPano:CroppedAreaLeftPixels><GPano:CroppedAreaTopPixels>0</GPano:CroppedAreaTopPixels>'
        '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')


def save_jpeg(arr, path, pano_w=None, pano_h=None, q=92):
    im = Image.fromarray(arr, 'RGB')
    w, h = pano_w or im.width, pano_h or im.height
    try:
        im.save(path, quality=q, subsampling=0, xmp=xmp_gpano(w, h).encode('utf-8'))
    except TypeError:
        im.save(path, quality=q, subsampling=0)
    return path


if __name__ == '__main__':
    exr = sys.argv[1]
    img = denoise(exr, exr[:-4])
    arr, lavg = tonemap(img)
    save_jpeg(arr, exr[:-4] + '.jpg')
    print('lavg', lavg)
