# -*- coding: utf-8 -*-
"""Настройки бюро — общие для всех объектов (объект может переопределить любое поле в project.py)."""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

BUREAU = dict(
    stage='ДП',                                   # стадия в основной надписи
    designer='Демиденко Д.',                      # графа «Дизайнер»
    drafter='Якубовский Н.',                      # графа «Чертил»
    author='Демиденко Д.',                        # автор (метаданные PDF)
    logo=os.path.join(_HERE, 'logo.jpg'),         # логотип PORTFOLIO (обрезан по рамке), в штамп и на титул
    logo_cover=os.path.join(_HERE, 'logo_cover.jpg'),   # логотип на всю страницу (обложка, лист без номера)
    logo_aspect=2484 / 1197,                      # ширина/высота logo.jpg
    studio='ДАНИЛ ДЕМИДЕНКО',
    studio_sub='проектирование и дизайн интерьеров',
    phone='+7 990 033-96-48',
    email='Indent656@gmail.com',
    tg='@ind_656',
)
