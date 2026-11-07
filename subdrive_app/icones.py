"""Ícones desenhados aqui mesmo (traço simples, 24×24), pintados na cor que a tela pedir."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "legendas": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 15h4M14 15h3M7 11h2M12 11h5"/>',
    "pendrive": '<rect x="7" y="9" width="10" height="13" rx="2.5"/><path d="M9 9V3h6v6M11 5.5v1M13 5.5v1"/>',
    "atualizar": '<path d="M20 11.5a8 8 0 0 0-14.7-4.4L4 8.5"/><path d="M4 4v4.5h4.5"/><path d="M4 12.5a8 8 0 0 0 14.7 4.4l1.3-1.4"/><path d="M20 20v-4.5h-4.5"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16.2 9.6"/>',
    "fail": '<circle cx="12" cy="12" r="9"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/>',
    "warn": '<path d="M12 3.8L2.8 19.6h18.4z"/><path d="M12 10v4.2M12 17.2v.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.01"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "right": '<path d="M9 6l6 6-6 6"/>',
    "left": '<path d="M15 6l-6 6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "externo": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "ejetar": '<path d="M12 5l7 8H5z"/><path d="M5 18h14"/>',
    "ajuda": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.3c-.7.3-1.1.8-1.1 1.5v.5M12 17v.01"/>',
    "corrigir": '<path d="M15 4.5a4.5 4.5 0 0 0-5.4 5.9L3.8 16.2a2 2 0 0 0 2.8 2.8l5.8-5.8A4.5 4.5 0 0 0 18.3 8l-2.6 2.6-2.6-.7-.7-2.6z"/>',
    "pgs": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15.5h10M9 12.5h6"/>',
    "sincronia": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M10 2.5h4"/>',
    "mais": '<circle cx="5.5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="18.5" cy="12" r="1"/>',
    "fechar": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "baixar": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "recarregar": '<path d="M20 12a8 8 0 1 1-2.3-5.7L20 8.5"/><path d="M20 3.5v5h-5"/>',
    "soltar": '<path d="M12 15V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "lista": '<path d="M9 6h11M9 12h11M9 18h11M4.5 6v.01M4.5 12v.01M4.5 18v.01"/>',
    "livro": '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z"/><path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>',
    "conversa": '<path d="M20 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/>',
}

LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#b45309"/>'
        '<g transform="translate(-3 0)"><rect x="6" y="20" width="10" height="24" rx="2" fill="#fff" opacity=".85"/>'
        '<rect x="8.5" y="26" width="2.5" height="4" fill="#b45309"/><rect x="8.5" y="34" width="2.5" height="4" fill="#b45309"/>'
        '<rect x="16" y="14" width="42" height="36" rx="8" fill="#fff"/><rect x="22" y="31" width="30" height="5" rx="2.5" fill="#b45309"/>'
        '<rect x="27" y="39" width="20" height="5" rx="2.5" fill="#b45309"/></g></svg>')

_cache = {}


def _svg(name, color, width):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="%s" '
            'stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (color, width, PATHS[name]))


def _render(svg: str, size: int) -> QPixmap:
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    ratio = max(ratio, 2.0)
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, pix.width(), pix.height()))
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def pixmap(name: str, color: str, size: int = 20, width: float = 1.8) -> QPixmap:
    key = (name, color, size, width)
    if key not in _cache:
        _cache[key] = _render(_svg(name, color, width), size)
    return _cache[key]


def icon(name: str, color: str, size: int = 20, width: float = 1.8) -> QIcon:
    return QIcon(pixmap(name, color, size, width))


def logo(size: int = 32) -> QPixmap:
    key = ("logo", size)
    if key not in _cache:
        _cache[key] = _render(LOGO, size)
    return _cache[key]


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_render(LOGO, s))
    return ic
