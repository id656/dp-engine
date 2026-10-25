# -*- coding: utf-8 -*-
"""Обложка альбома: логотип бюро на весь лист + пустой лист, затем альбом (без номеров, вне ведомости листов).
python3 tools/cover.py objects/<объект> [N]  ->  out/<шифр>_ред<N>.pdf (N — номер редакции, по умолчанию из project.rev)"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(obj, rev=None):
    import build as B
    B.setup(obj)
    import paths
    import kit
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from pypdf import PdfReader, PdfWriter
    from PIL import Image
    P = kit.PROJECT
    album = os.path.join(paths.OUT, f'{P["cipher"]}_Рабочая_документация.pdf')
    if not os.path.exists(album):
        raise SystemExit('сначала соберите альбом: python3 build.py ' + obj + ' all')
    logo = P.get('logo_cover')
    if not logo or not os.path.exists(logo):          # обрезка логотипа под пропорции А3 без искажений
        im = Image.open(P['logo'])
        w = round(im.height * 420 / 297)
        x0 = max(0, (im.width - w) // 2)
        logo = paths.out('logo_cover.jpg')
        im.crop((x0, 0, x0 + min(w, im.width), im.height)).save(logo, quality=95)
    cov = paths.out('_cover.pdf')
    c = canvas.Canvas(cov, pagesize=(420 * mm, 297 * mm))
    c.drawImage(logo, 0, 0, 420 * mm, 297 * mm)
    c.showPage()
    c.showPage()
    c.save()
    if rev is None:
        m = re.search(r'(\d+)', P.get('rev', '1'))
        rev = m.group(1) if m else '1'
    dst = os.path.join(paths.OUT, f'{P["cipher"]}_ред{rev}.pdf')
    w = PdfWriter()
    for f in (cov, album):
        for pg in PdfReader(f).pages:
            w.add_page(pg)
    w.add_metadata({'/Title': f'{P["cipher"]} Дизайн-проект', '/Author': P.get('author', '')})
    w.write(dst)
    os.remove(cov)
    print('ok', dst)
    return dst


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
