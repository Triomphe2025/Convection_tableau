"""
TriosSeconverter — Interface graphique principale (v2 — sidebar navigation).

Lance avec :  python interface.py
"""

import datetime
import json
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

from converter import Converter
from data_dictionary import get_dictionary, get_pending_dictionary
from template import TableTemplate, TemplateManager

logging.basicConfig(level=logging.DEBUG)


def _resource(name: str) -> Path:
    """Résout le chemin d'une ressource (fonctionne aussi dans un .exe PyInstaller)."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / name
    return Path(__file__).parent / name


def _tag_from_msg(msg: str) -> str:
    """Déduit le tag de couleur d'un message de log selon son contenu."""
    if any(c in msg for c in ('✓', '✅')):
        return 'ok'
    if any(c in msg for c in ('✗', '✘', '⛔')):
        return 'err'
    if any(c in msg for c in ('⚠', '△')):
        return 'warn'
    if any(c in msg for c in ('═', '─', '━', '▶')):
        return 'muted'
    return 'info'


# ── Palette de couleurs ───────────────────────────────────────────────
BG_MAIN = "#1a1a2e"
BG_PANEL = "#16213e"
BG_CARD = "#0f3460"
BG_LOG = "#0a0a14"
FG_TEXT = "#e0e0f0"
FG_MUTED = "#7878a0"
FG_OK = "#56c596"
FG_ERR = "#e05c5c"
FG_WARN = "#e0a050"
COL_ACC = "#e94560"   # rouge-rose accent
COL_ACC2 = "#533483"   # violet secondaire
BTN_HVR = "#c73652"
FONT_MAIN = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_H1 = ("Segoe UI", 18, "bold")
FONT_H2 = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)


# ── Animation d'accueil ───────────────────────────────────────────────

class WelcomeAnimation:
    """Animation pseudo-3D : mini personnage 3D porte une statue d'oiseau
    vers une boite magique 3D isométrique. L'oiseau sort vivant et s'envole.
    Canvas 580×180 px.
    """

    TOTAL_FRAMES = 160
    _BX, _BY = 300, 168  # centre boite — BY calculé pour que le bas touche _GY
    _GY = 202             # ligne de sol — bas du canvas (216px) moins ombre

    def __init__(self, canvas: tk.Canvas):
        self._c = canvas
        self._frame = 0
        self._running = True
        self._c.after(100, self._tick)

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        try:
            if self._c.winfo_width() < 10:
                self._c.after(100, self._tick)
                return
        except Exception:
            return
        self._draw()
        self._frame = (self._frame + 1) % self.TOTAL_FRAMES
        self._c.after(33, self._tick)

    # ── Orchestration ─────────────────────────────────────────────────

    def _draw(self):
        import math
        self._c.delete('anim')
        f = self._frame
        bx, by, gy = self._BX, self._BY, self._GY
        glowing = 75 <= f < 108

        # Ouverture de porte : 0=fermée → 1=ouverte → referme après l'envol
        if f < 56:
            door_open = 0.0
        elif f < 72:
            door_open = min(1.0, (f - 56) / 16.0)   # s'ouvre
        elif f < 144:
            door_open = 1.0                           # reste ouverte
        elif f < 158:
            door_open = max(0.0, 1.0 - (f - 144) / 14.0)  # se referme
        else:
            door_open = 0.0                           # fermée pour la pause

        # Sol — bord à bord, jusqu'au bas du canvas
        cw = max(self._c.winfo_width(), 2000)
        self._c.create_rectangle(0, gy + 1, cw, gy + 14,
                                 fill="#08111e", outline='', tags='anim')
        self._c.create_line(0, gy + 1, cw, gy + 1,
                            fill="#243858", width=2, tags='anim')
        self._c.create_line(0, gy + 3, cw, gy + 3,
                            fill="#0d1a30", width=1, tags='anim')

        # Boite 3D avec porte (toujours présente)
        gcol = (COL_ACC if (f // 4) % 2 == 0 else COL_ACC2) if glowing else None
        self._draw_box3d(bx, by, gcol, door_open)

        if f < 56:
            # Minion marche depuis la gauche en portant la statue
            mx = int(-55 + (bx - 35) * f / 55)
            wk = (f % 14) / 14
            self._shadow(mx, gy)
            self._minion(mx, gy, walk=wk, carrying=True)
            self._bird(mx + 22, gy - 48, statue=True)

        elif f < 75:
            # Dépôt dans la boite (porte ouverte depuis f=72)
            p = (f - 56) / 18
            mx = bx - 90
            self._shadow(mx, gy)
            self._minion(mx, gy, lean=int(p * 11))
            if p < 0.88:
                self._bird(mx + 22 + int(p * 20),
                           gy - 48 + int(p * 36), statue=True)

        elif f < 108:
            # Boite brille — Minion recule et observe
            p = (f - 75) / 32
            mx = bx - 90 - int(p * 16)
            self._shadow(mx, gy)
            self._minion(mx, gy, watching=True)
            # Particules orbitales autour de la boite
            for i in range(7):
                angle = i * math.pi * 2 / 7 + f * 0.22
                r = 40 + 9 * math.sin(f * 0.28 + i)
                px = bx + int(r * math.cos(angle))
                py = by + int(r * 0.38 * math.sin(angle))
                sz = 2 + int(abs(math.sin(angle + f * 0.12)) * 3)
                col = COL_ACC if i % 2 == 0 else COL_ACC2
                self._c.create_oval(px - sz, py - sz, px + sz, py + sz,
                                    fill=col, outline='', tags='anim')

        elif f < 152:
            # Oiseau sort par la porte et traverse l'écran
            p = (f - 108) / 43
            mx = bx - 106
            self._shadow(mx, gy)
            self._minion(mx, gy, watching=True)
            bird_x = int(bx + 20 + p * 295)
            bird_y = int(by - 5 - p * 77)
            wt = (f % 10) / 10
            sc = max(0.28, 1.0 - p * 0.72)
            self._bird(bird_x, bird_y, statue=False, wing_t=wt, scale=sc)

        else:
            # Pause (porte se referme)
            mx = bx - 106
            self._shadow(mx, gy)
            self._minion(mx, gy, watching=True)

    # ── Coffre magique isométrique avec porte ────────────────────────────

    def _draw_box3d(self, cx, cy, glow=None, door_open=0.0):
        """Coffre isométrique posé au sol, avec porte animée.
        w×h légèrement portrait, bottom = cy + h//2 aligné sur _GY.
        door_open : 0.0 fermée → 1.0 ouverte à 90°.
        """
        w, h, ddx, ddy = 62, 64, 20, -10
        x1, y1 = cx - w // 2, cy - h // 2
        x2, y2 = cx + w // 2, cy + h // 2

        # Couleurs selon état
        if glow:
            cf = glow
            ct = "#ffe8f0" if glow == COL_ACC else "#e0e8ff"
            cs = "#1a0530"
            bw, bc = 2, COL_ACC
        else:
            cf = BG_CARD
            ct = "#1a4a7a"
            cs = "#07192e"
            bw, bc = 1, COL_ACC

        # Ombre portée au sol (ellipse aplatie juste sous la boite)
        self._c.create_oval(cx - 36, y2 + 1,
                            cx + 36 + ddx // 2, y2 + 9,
                            fill="#080f1c", outline='', tags='anim')

        # ── Face avant ───────────────────────────────────────────────
        self._c.create_rectangle(x1, y1, x2, y2,
                                 fill=cf, outline=bc, width=bw, tags='anim')

        # ── Face du dessus ────────────────────────────────────────────
        self._c.create_polygon(
            x1, y1,  x1 + ddx, y1 + ddy,
            x2 + ddx, y1 + ddy,  x2, y1,
            fill=ct, outline=bc, width=1, tags='anim')

        # ── Face droite ───────────────────────────────────────────────
        self._c.create_polygon(
            x2, y1,  x2 + ddx, y1 + ddy,
            x2 + ddx, y2 + ddy,  x2, y2,
            fill=cs, outline=bc, width=1, tags='anim')

        # ── Cornières métalliques (détail 3D) ─────────────────────────
        stripe = COL_ACC2
        # Bord supérieur
        self._c.create_rectangle(x1, y1, x2, y1 + 5,
                                 fill=stripe, outline='', tags='anim')
        # Bord inférieur
        self._c.create_rectangle(x1, y2 - 5, x2, y2,
                                 fill=stripe, outline='', tags='anim')
        # Bords verticaux gauche et droit
        self._c.create_rectangle(x1, y1, x1 + 4, y2,
                                 fill=stripe, outline='', tags='anim')
        self._c.create_rectangle(x2 - 4, y1, x2, y2,
                                 fill=stripe, outline='', tags='anim')

        # ── PORTE ─────────────────────────────────────────────────────
        dw = int(w * 0.56)        # largeur de la porte
        dh = int(h * 0.76)        # hauteur de la porte
        dpx = cx - dw // 2        # bord gauche de la porte
        dpy = y2 - dh             # bord haut de la porte

        if door_open < 0.03:
            # ── Porte fermée ──────────────────────────────────────────
            # Panneau principal
            self._c.create_rectangle(dpx, dpy, dpx + dw, y2,
                                     fill="#0d2040", outline=COL_ACC2,
                                     width=1, tags='anim')
            # Moulure interne (encadrement)
            m = 4
            self._c.create_rectangle(dpx + m, dpy + m,
                                     dpx + dw - m, y2 - m,
                                     fill='', outline=COL_ACC2,
                                     width=1, tags='anim')
            # Poignée (droite, centrée en hauteur)
            hx = dpx + dw - 9
            hy = dpy + dh // 2
            self._c.create_oval(hx - 3, hy - 5, hx + 3, hy + 5,
                                fill=COL_ACC, outline='', tags='anim')
            # Charnières (gauche)
            for hy_h in (dpy + dh // 5, dpy + 3 * dh // 5):
                self._c.create_rectangle(dpx, hy_h - 3, dpx + 5, hy_h + 3,
                                         fill=COL_ACC2, outline='', tags='anim')

        elif door_open < 0.97:
            # ── Porte en cours d'ouverture (forshortening 2D) ─────────
            vis_w = max(1, int(dw * (1.0 - door_open)))
            # Face visible de la porte (se rétrécit)
            self._c.create_rectangle(dpx, dpy, dpx + vis_w, y2,
                                     fill="#0d2040", outline=COL_ACC2,
                                     tags='anim')
            # Épaisseur de la porte (visible de côté)
            edge = max(1, int(9 * door_open))
            ex = dpx + vis_w
            self._c.create_polygon(
                ex,          dpy,
                ex + edge,   dpy - edge // 2,
                ex + edge,   y2 - edge // 2,
                ex,          y2,
                fill="#1a2a3a", outline='', tags='anim')
            # Poignée (tant que la porte n'est pas trop ouverte)
            if door_open < 0.45:
                hx2 = dpx + vis_w - 7
                hy2 = dpy + dh // 2
                self._c.create_oval(hx2 - 2, hy2 - 4, hx2 + 2, hy2 + 4,
                                    fill=COL_ACC, outline='', tags='anim')

        else:
            # ── Porte ouverte — intérieur visible ─────────────────────
            int_d = 11   # profondeur visible de l'intérieur
            self._c.create_polygon(
                dpx,          dpy,
                dpx + int_d,  dpy - int_d // 2,
                dpx + int_d,  y2 - int_d // 2,
                dpx,          y2,
                fill="#050d18", outline='', tags='anim')
            if glow:
                # Lueur magique intérieure
                mid_y = (dpy + y2) // 2
                self._c.create_oval(dpx + 1, mid_y - 10,
                                    dpx + int_d + 1, mid_y + 10,
                                    fill=glow, outline='', tags='anim')

        # Symbole magique au-dessus de la porte
        sym_y = dpy - 7
        self._c.create_text(cx, sym_y,
                            text="✨" if glow else "trios",
                            fill="white" if glow else COL_ACC,
                            font=("Segoe UI", 9, "bold"), tags='anim')

    # ── Personnage 3D miniature ────────────────────────────────────────

    def _shadow(self, cx, gy):
        self._c.create_oval(cx - 17, gy - 3, cx + 17, gy + 3,
                            fill="#0c1828", outline='', tags='anim')

    def _minion(self, x, gy, walk=0.0, carrying=False,
                lean=0, watching=False):
        """Minion 2D isométrique dessiné sur Canvas — du fond vers l'avant."""
        import math
        # Palette Minion
        YL = "#f5d028"   # jaune clair
        YM = "#d4aa00"   # jaune moyen
        YD = "#b08800"   # jaune sombre (ombres)
        BL = "#5b8ed6"   # bleu salopette
        BD = "#3a6ab0"   # bleu salopette ombre
        BS = "#1e408a"   # bleu salopette contour
        GR = "#909098"   # gris lunettes
        GRD = "#5a5a62"   # gris sombre
        EW = "#ffffff"   # blanc œil
        EBR = "#7a3800"   # brun iris
        EPU = "#080400"   # noir pupille
        BK = "#101012"   # noir chaussures/cheveux
        BKS = "#282830"   # noir reflet

        bx = x + lean // 2
        sw = math.sin(walk * 2 * math.pi)
        ls = int(sw * 8)   # swing jambes

        fy = gy         # sol
        shY = fy - 6     # dessus chaussure
        lgT = fy - 22    # haut jambes
        ovB = fy - 24    # bas salopette
        ovM = fy - 37    # milieu salopette (logo)
        ovT = fy - 52    # haut salopette
        bckT = fy - 67    # sommet du corps
        hCY = fy - 58    # centre tête
        hRX = 16         # rayon horizontal tête
        hRY = 14         # rayon vertical tête
        bHW = 15         # demi-largeur corps (total 30px)
        armY = ovT + 6    # position verticale des bras

        # ── 1. Chaussure arrière ──────────────────────────────────────
        self._c.create_oval(bx - 13 - ls, shY - 3,
                            bx + 1 - ls, fy + 3,
                            fill=BK, outline='', tags='anim')

        # ── 2. Jambe arrière ──────────────────────────────────────────
        self._c.create_rectangle(bx - 10 - ls, lgT,
                                 bx - 2 - ls, shY,
                                 fill=YM, outline='', tags='anim')

        # ── 3. Bras arrière ───────────────────────────────────────────
        aW = 6                               # epaisseur des bras
        sbX, sbY = bx - bHW + 1, armY + 3   # epaule gauche
        if carrying:
            ebX, ebY = sbX - 7, armY - 7
            hbX, hbY = sbX - 5, armY - 18
        elif lean > 0:
            prog = lean / 11.0
            ebX, ebY = sbX + int(8 * prog),  sbY - int(4 * prog)
            hbX, hbY = sbX + int(16 * prog), sbY - int(10 * prog)
        elif watching:
            ebX, ebY = sbX - 6, armY - 3
            hbX, hbY = sbX - 4, armY - 12
        else:
            aof = int(-sw * 8)
            ebX, ebY = sbX - 5, sbY + 5 + aof // 2
            hbX, hbY = sbX - 3, sbY + 13 + aof
        self._c.create_line(sbX, sbY, ebX, ebY,
                            fill=YM, width=aW, capstyle='round', tags='anim')
        self._c.create_line(ebX, ebY, hbX, hbY,
                            fill=YD, width=aW - 1, capstyle='round', tags='anim')
        self._c.create_oval(hbX - 4, hbY - 4, hbX + 4, hbY + 4,
                            fill=YM, outline=YD, width=1, tags='anim')

        # ── 4. Corps jaune principal ───────────────────────────────────
        # Arc bas (demi-sphère basse)
        self._c.create_oval(bx - bHW - 1, ovB - 10,
                            bx + bHW + 1, ovB + 10,
                            fill=YL, outline=YD, width=1, tags='anim')
        # Rectangle central
        self._c.create_rectangle(bx - bHW, bckT,
                                 bx + bHW, ovB,
                                 fill=YL, outline='', tags='anim')
        # Tête (ovale haut)
        self._c.create_oval(bx - hRX, hCY - hRY,
                            bx + hRX, hCY + hRY,
                            fill=YL, outline=YD, width=1, tags='anim')
        # Face droite corps (ombre 3D)
        self._c.create_rectangle(bx + bHW, bckT,
                                 bx + bHW + 5, ovB,
                                 fill=YM, outline='', tags='anim')
        # Face droite tête (ombre 3D)
        self._c.create_polygon(
            bx + hRX - 2, hCY - 5,
            bx + hRX + 4, hCY - 3,
            bx + hRX + 4, hCY + 7,
            bx + hRX - 2, hCY + 9,
            fill=YM, outline='', tags='anim')
        # Reflet (lumière haut gauche)
        self._c.create_oval(bx - 8, hCY - hRY + 2,
                            bx - 2, hCY - hRY + 8,
                            fill="#ffe060", outline='', tags='anim')

        # ── 5. Salopette bleue ────────────────────────────────────────
        # Corps salopette
        self._c.create_polygon(
            bx - bHW + 2, ovT,
            bx - bHW,     ovB,
            bx + bHW,     ovB,
            bx + bHW - 2, ovT,
            fill=BL, outline=BS, width=1, tags='anim')
        # Ombre côté droit
        self._c.create_polygon(
            bx + bHW - 2, ovT,
            bx + bHW,     ovB,
            bx + bHW + 5, ovB,
            bx + bHW + 3, ovT,
            fill=BD, outline='', tags='anim')
        # Bavette (bib) devant
        self._c.create_polygon(
            bx - 9, ovT,
            bx - 10, ovT + 14,
            bx + 10, ovT + 14,
            bx + 9,  ovT,
            fill=BL, outline=BS, width=1, tags='anim')
        # Logo G (petit carré centré)
        self._c.create_rectangle(bx - 5, ovM - 5, bx + 5, ovM + 5,
                                 fill=BD, outline=BS, tags='anim')
        self._c.create_text(bx, ovM, text="G", fill="#90c8ff",
                            font=("Segoe UI", 6, "bold"), tags='anim')
        # Boutons épaulettes (gauche/droit)
        for bxb in (bx - bHW + 4, bx + bHW - 4):
            self._c.create_oval(bxb - 3, ovT + 2, bxb + 3, ovT + 8,
                                fill=GR, outline=GRD, tags='anim')

        # ── 6. Jambe avant ────────────────────────────────────────────
        self._c.create_rectangle(bx - 1 + ls, lgT,
                                 bx + 7 + ls, shY,
                                 fill=YL, outline='', tags='anim')
        self._c.create_rectangle(bx + 7 + ls, lgT,
                                 bx + 10 + ls, shY,
                                 fill=YM, outline='', tags='anim')

        # ── 7. Chaussure avant ────────────────────────────────────────
        self._c.create_oval(bx - 3 + ls, shY - 4,
                            bx + 14 + ls, fy + 3,
                            fill=BK, outline='', tags='anim')
        self._c.create_oval(bx - 1 + ls, shY - 2,
                            bx + 7 + ls, shY + 1,
                            fill=BKS, outline='', tags='anim')

        # ── 8. Bras avant ─────────────────────────────────────────────
        sfX, sfY = bx + bHW - 1, armY + 3   # epaule droite
        if carrying:
            efX, efY = sfX + 7, armY - 7
            hfX, hfY = sfX + 5, armY - 18
        elif lean > 0:
            prog = lean / 11.0
            efX, efY = sfX + int(8 * prog),  sfY - int(4 * prog)
            hfX, hfY = sfX + int(18 * prog), sfY - int(12 * prog)
        elif watching:
            efX, efY = sfX + 10, armY - 6
            hfX, hfY = sfX + 8,  armY - 18
        else:
            aof2 = int(sw * 8)
            efX, efY = sfX + 5, sfY + 5 - aof2 // 2
            hfX, hfY = sfX + 3, sfY + 13 - aof2
        self._c.create_line(sfX, sfY, efX, efY,
                            fill=YL, width=aW, capstyle='round', tags='anim')
        self._c.create_line(efX, efY, hfX, hfY,
                            fill=YM, width=aW - 1, capstyle='round', tags='anim')
        self._c.create_oval(hfX - 4, hfY - 4, hfX + 4, hfY + 4,
                            fill=YL, outline=YD, width=1, tags='anim')

        # ── 9. Lunettes (sangle + anneaux + yeux) ─────────────────────
        gogY = hCY - 2   # centre vertical lunettes
        gR = 9         # rayon anneau
        gl = bx - 9   # centre lunette gauche
        gr = bx + 9   # centre lunette droite

        # Sangle noire (passe derrière la tête, de bord en bord)
        self._c.create_rectangle(bx - hRX - 2, gogY - 3,
                                 bx + hRX + 6, gogY + 3,
                                 fill="#1a1a1a", outline='', tags='anim')
        # Anneaux métalliques
        for gcx in (gl, gr):
            self._c.create_oval(gcx - gR, gogY - gR,
                                gcx + gR, gogY + gR,
                                fill=GRD, outline=GR, width=2, tags='anim')
        # Pont entre les deux lunettes
        self._c.create_rectangle(gl + gR - 2, gogY - 2,
                                 gr - gR + 2, gogY + 2,
                                 fill=GR, outline='', tags='anim')
        # Blancs des yeux
        eR = gR - 2
        for gcx in (gl, gr):
            self._c.create_oval(gcx - eR, gogY - eR,
                                gcx + eR, gogY + eR,
                                fill=EW, outline='', tags='anim')
        # Iris + pupilles (légèrement tournés vers la boite si watching)
        edir = 2 if watching else 1
        for gcx in (gl + edir, gr + edir):
            self._c.create_oval(gcx - 4, gogY - 4, gcx + 4, gogY + 4,
                                fill=EBR, outline='', tags='anim')
            self._c.create_oval(gcx - 2, gogY - 2, gcx + 2, gogY + 2,
                                fill=EPU, outline='', tags='anim')
            # Reflet (point blanc)
            self._c.create_oval(gcx + 1, gogY - 3, gcx + 3, gogY - 1,
                                fill=EW, outline='', tags='anim')
        # Reflets vitrés (arc de cercle clair sur chaque verre)
        for gcx in (gl, gr):
            self._c.create_arc(gcx - eR, gogY - eR, gcx + 2, gogY - 2,
                               start=25, extent=55,
                               fill="#d4dce8", outline='', tags='anim')

        # ── 10. Cheveux (filaments noirs sur le sommet) ────────────────
        hairY = hCY - hRY
        for hxo, dy in ((-6, -9), (-1, -11), (5, -9)):
            self._c.create_line(bx + hxo, hairY,
                                bx + hxo + dy // 4, hairY + dy,
                                fill=BK, width=2, tags='anim')

        # ── 11. Bouche ────────────────────────────────────────────────
        mY = gogY + gR + 6
        if watching:
            # Bouche O (étonné)
            self._c.create_oval(bx - 5, mY - 4, bx + 5, mY + 4,
                                fill="#b08070", outline=YD, tags='anim')
            self._c.create_rectangle(bx - 4, mY - 4, bx + 4, mY - 1,
                                     fill=EW, outline='', tags='anim')
        else:
            # Sourire
            self._c.create_arc(bx - 7, mY - 5, bx + 7, mY + 5,
                               start=200, extent=140,
                               style='arc', outline=YD, width=2, tags='anim')

    # ── Oiseau 3D ──────────────────────────────────────────────────────

    def _bird(self, cx, cy, statue=True, wing_t=0.0, scale=1.0):
        import math
        s = scale

        if statue:
            bw = int(17 * s)
            bh = int(10 * s)
            # Corps (pierre grise)
            self._c.create_oval(cx - bw, cy - bh, cx + bw, cy + bh,
                                fill="#8898b0", outline="#566070",
                                width=1, tags='anim')
            # Reflet 3D corps
            self._c.create_oval(cx - bw + int(4 * s), cy - bh,
                                cx + int(4 * s), cy - int(2 * s),
                                fill="#aabbcc", outline='', tags='anim')
            # Ailes repliées (deux côtés)
            for sgn in (-1, 1):
                self._c.create_polygon(
                    cx + sgn * 3,             cy - bh // 2,
                    cx + sgn * int(26 * s),   cy - int(18 * s),
                    cx + sgn * int(22 * s),   cy + int(4 * s),
                    fill="#6a7a90", outline="#566070", width=1, tags='anim')
            # Tête
            hr = int(7 * s)
            hx, hy_ = cx + int(14 * s), cy - int(11 * s)
            self._c.create_oval(hx - hr, hy_ - hr, hx + hr, hy_ + hr,
                                fill="#9ab0b8", outline="#566070",
                                width=1, tags='anim')
            # Bec
            self._c.create_polygon(
                hx + hr, hy_,
                hx + hr + int(8 * s), hy_ - int(2 * s),
                hx + hr + int(8 * s), hy_ + int(2 * s),
                fill="#7a6050", outline='', tags='anim')
            # Plumes queue
            for i in range(3):
                self._c.create_line(cx - bw, cy,
                                    cx - bw - int(10 * s),
                                    cy + int((i - 1) * 4 * s),
                                    fill="#566070",
                                    width=max(1, int(2 * s)), tags='anim')

        else:
            # Oiseau vivant — coloré, ailes animées
            bw = int(19 * s)
            bh = int(9 * s)
            wu = math.sin(wing_t * 2 * math.pi)
            BC = "#f5a030"   # corps orange doré
            WC = "#e07010"   # aile foncée
            WH = "#ffd060"   # reflet aile

            # Corps
            self._c.create_oval(cx - bw, cy - bh, cx + bw, cy + bh,
                                fill=BC, outline="#c07010",
                                width=1, tags='anim')
            # Reflet corps
            self._c.create_oval(cx - bw + int(3 * s), cy - bh,
                                cx, cy - int(2 * s),
                                fill="#ffd080", outline='', tags='anim')

            # Ailes (haut/bas animées)
            wy = cy - bh - int((5 + 15 * abs(wu)) * s)
            for sgn in (-1, 1):
                tip_x = cx + sgn * int(30 * s)
                pts = [
                    cx,                       cy - bh,
                    cx + sgn * int(14 * s),  wy,
                    tip_x,                    wy + int(5 * s),
                    cx + sgn * int(5 * s),   cy - bh // 2,
                ]
                self._c.create_polygon(*pts, fill=WC,
                                       outline=BC, width=1, tags='anim')
                # Reflet aile
                self._c.create_polygon(
                    cx + sgn * int(2 * s), cy - bh,
                    cx + sgn * int(10 * s), wy + int(3 * s),
                    tip_x - sgn * int(6 * s), wy + int(7 * s),
                    fill=WH, outline='', tags='anim')

            # Tête
            hr = int(8 * s)
            hx, hy_ = cx + int(16 * s), cy - int(9 * s)
            self._c.create_oval(hx - hr, hy_ - hr, hx + hr, hy_ + hr,
                                fill=BC, outline="#c07010", width=1, tags='anim')
            # Oeil
            self._c.create_oval(hx + int(2 * s), hy_ - int(3 * s),
                                hx + int(6 * s), hy_ + int(1 * s),
                                fill="white", outline='', tags='anim')
            self._c.create_oval(hx + int(3 * s), hy_ - int(2 * s),
                                hx + int(5 * s), hy_,
                                fill="#1a1a1a", outline='', tags='anim')
            # Bec
            self._c.create_polygon(
                hx + hr, hy_,
                hx + hr + int(9 * s), hy_ - int(2 * s),
                hx + hr + int(9 * s), hy_ + int(2 * s),
                fill="#f0b030", outline='', tags='anim')
            # Queue animée
            for i in range(3):
                ang = (i - 1) * 0.3 + wing_t * 0.5
                self._c.create_line(
                    cx - bw, cy,
                    cx - bw - int(12 * s),
                    cy + int(math.sin(ang) * 6 * s),
                    fill="#c07010",
                    width=max(1, int(2 * s)), tags='anim')
            # Sillage (petites particules dorées)
            for i in range(4):
                px = cx - bw - int((4 + i * 9) * s)
                py = cy + int(math.sin(wing_t * 6.28 + i * 1.2) * 3)
                r = max(1, int((3.5 - i * 0.8) * s))
                self._c.create_oval(px - r, py - r, px + r, py + r,
                                    fill=WH, outline='', tags='anim')


# ── Bouton arrondi ────────────────────────────────────────────────────

class RoundedButton(tk.Canvas):
    """Bouton à coins arrondis dessiné sur un Canvas."""

    def __init__(self, parent, text, command, bg=COL_ACC, fg="white",
                 hover_bg=BTN_HVR, font=FONT_BOLD, width=220, height=36,
                 radius=8, state='normal', **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent['bg'], highlightthickness=0, **kwargs)
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._font = font
        self._text = text
        self._command = command
        self._radius = radius
        self._state = state
        self._btn_w = width
        self._btn_h = height
        self._draw(bg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        self.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90,  extent=90, **kw)
        self.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0,   extent=90, **kw)
        self.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, **kw)
        self.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, **kw)
        self.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
        self.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)

    def _draw(self, bg):
        self.delete("all")
        fill = bg if self._state == 'normal' else FG_MUTED
        self._rounded_rect(1, 1, self._btn_w - 1, self._btn_h - 1,
                           self._radius, fill=fill, outline=fill)
        self.create_text(self._btn_w // 2, self._btn_h // 2,
                         text=self._text, fill=self._fg,
                         font=self._font)

    def _on_enter(self, _):
        if self._state == 'normal':
            self._draw(self._hover_bg)

    def _on_leave(self, _):
        if self._state == 'normal':
            self._draw(self._bg)

    def _on_click(self, _):
        if self._state == 'normal' and self._command:
            self._command()

    def configure_state(self, state):
        self._state = state
        self._draw(self._bg)

    def set_text(self, text):
        self._text = text
        self._draw(self._bg if self._state == 'normal' else FG_MUTED)


# ── Application principale ────────────────────────────────────────────

class TriosSeconverterApp(tk.Tk):
    """Fenêtre principale de TriosSeconverter — navigation sidebar."""

    def __init__(self):
        super().__init__()
        self.title("TriosSeconverter")
        self.geometry("1060x760")
        self.minsize(900, 640)
        self.configure(bg=BG_MAIN)

        # Icône de la fenêtre
        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        # ── Variables d'état ─────────────────────────────────────────
        self._word_file = tk.StringVar()
        self._tables_word_file = tk.StringVar()
        self._output_dir = tk.StringVar()
        self._queue: queue.Queue = queue.Queue()
        self._result = None
        self._tpl_manager = TemplateManager()
        self._tpl_var = tk.StringVar(value=self._tpl_manager.names()[0])

        from config import Config
        self._ocr_mode = tk.StringVar(value=getattr(Config, 'OCR_MODE', 'tesseract'))
        self._claude_key = tk.StringVar(value=getattr(Config, 'CLAUDE_API_KEY', ''))
        self._agent_session_id = tk.StringVar(
            value=getattr(Config, 'CLAUDE_AGENT_SESSION_ID', '')
        )

        self._validation_interactive = tk.BooleanVar(
            value=getattr(Config, 'VALIDATION_INTERACTIVE', False)
        )
        self._validation_auto_skip = False   # bascule vers mode auto en cours de conversion

        # Timer de conversion
        self._conv_start_time = None
        self._timer_id = None

        # Page courante
        self._current_page = None
        self._nav_buttons = {}

        # Formatage Excel
        self._format_excel_path = tk.StringVar()
        self._format_pdf_path = tk.StringVar()   # PDF source pour extraction espacement
        self._format_output_dir = tk.StringVar()
        self._format_row_height = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_ROW_HEIGHT', 12.6))
        )
        self._format_col_default = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_COL_WIDTH_DEFAULT', 19))
        )
        self._format_col_signal = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_COL_WIDTH_SIGNAL', 33))
        )
        self._format_margin_top = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_TOP', 0.9))
        )
        self._format_margin_bottom = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_BOTTOM', 0.9))
        )
        self._format_margin_left = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_LEFT', 1.75))
        )
        self._format_margin_right = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_RIGHT', 1.75))
        )
        self._format_margin_header = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_HEADER', 0.0))
        )
        self._format_margin_footer = tk.StringVar(
            value=str(getattr(Config, 'FORMAT_MARGIN_FOOTER', 0.0))
        )
        self._format_sheet_vars: dict = {}        # nom_feuille → BooleanVar
        self._format_sheet_col_vars: dict = {}    # nom_feuille → StringVar (nb colonnes)
        self._format_sheet_ps_vars: dict = {}     # nom_feuille → StringVar (lignes/page)
        self._format_n_cols = tk.StringVar(value="0")   # override global colonnes (0 = auto)
        self._format_page_size = tk.StringVar(value="0")  # override global lignes/page (0 = auto)

        # Référence à l'animation (pour pouvoir l'arrêter si besoin)
        self._welcome_anim = None

        # Workflow UX — parcours de traitement
        self._workflow_mode = tk.StringVar(value="")   # "tableaux", "dessins", "mixte"
        self._card_indicators: dict = {}               # mode → Frame indicateur
        self._nav_frame = None                         # référence nav pour pack(after=)

        self._build_ui()

        # Style ttk global
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox",
                        fieldbackground=BG_LOG, background=BG_LOG,
                        foreground=FG_TEXT, selectbackground=COL_ACC)
        style.configure("TNotebook", background=BG_PANEL, tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_MUTED,
                        padding=[14, 6], font=FONT_BOLD)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_PANEL)],
                  foreground=[("selected", COL_ACC)])
        style.configure("Trios.Horizontal.TProgressbar",
                        troughcolor=BG_LOG, background=COL_ACC,
                        lightcolor=COL_ACC, darkcolor=COL_ACC,
                        bordercolor=BG_PANEL, thickness=18)

        self._show_page('accueil')
        self._poll_queue()

        # Raccourci clavier
        self.bind('<Control-s>', lambda e: self._start())

    # ── Construction de l'interface ───────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_toolbar()
        self._build_nav()
        self._build_context_toolbar()   # barre contextuelle workflow (masquée par défaut)
        self._build_status_bar()        # doit être packé avant expand=True
        self._build_main_area()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG_CARD, height=70)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text="Trios", font=("Segoe UI", 22, "bold"),
                 fg=COL_ACC, bg=BG_CARD).pack(side='left', padx=(22, 0), pady=14)
        tk.Label(hdr, text="Seconverter", font=("Segoe UI", 22, "bold"),
                 fg=FG_TEXT, bg=BG_CARD).pack(side='left', pady=14)
        tk.Label(hdr,
                 text="  •  Conversion de borniers électriques vers Excel",
                 font=("Segoe UI", 10),
                 fg=FG_MUTED, bg=BG_CARD).pack(side='left', pady=14)

        # Badge version
        tk.Label(hdr, text=" v1.7 ", font=("Segoe UI", 8),
                 fg=FG_TEXT, bg=COL_ACC2,
                 padx=4, pady=2).pack(side='right', padx=20, pady=22)

    def _build_main_area(self):
        """Zone de contenu des pages (sans sidebar)."""
        self._page_container = tk.Frame(self, bg=BG_MAIN)
        self._page_container.pack(fill='both', expand=True)

        self._pages = {}
        self._pages['accueil'] = self._build_page_accueil(self._page_container)
        self._pages['stepper'] = self._build_page_stepper(self._page_container)
        self._pages['dessins'] = self._build_page_dessins(self._page_container)
        self._pages['mixte'] = self._build_page_mixte(self._page_container)
        self._pages['dashboard'] = self._build_page_dashboard(self._page_container)
        self._pages['params'] = self._build_page_params(self._page_container)
        self._pages['ocr'] = self._build_page_ocr(self._page_container)
        self._pages['format'] = self._build_page_format(self._page_container)
        self._pages['options'] = self._build_page_options(self._page_container)
        self._pages['aide'] = self._build_page_aide(self._page_container)

        for page in self._pages.values():
            page.pack_forget()

    def _build_nav(self):
        """Barre de navigation par onglets horizontaux (sous la toolbar)."""
        nav = tk.Frame(self, bg=BG_CARD, height=40)
        nav.pack(fill='x')
        nav.pack_propagate(False)

        # Trait de séparation haut (accent couleur)
        tk.Frame(nav, bg=COL_ACC2, height=1).pack(fill='x', side='top')

        tabs = tk.Frame(nav, bg=BG_CARD)
        tabs.pack(side='left', fill='y', padx=4)

        # Onglets utilisateur — toujours visibles
        user_items = [
            ('accueil', '\U0001f3e0  Accueil'),
            ('format',  '📐  Formater Excel'),
            ('aide',    '❓  Aide'),
        ]
        for page_id, label in user_items:
            btn = self._make_nav_tab(tabs, label, page_id)
            self._nav_buttons[page_id] = btn

        # Onglets développeur — cachés par défaut dans un container togglable
        self._dev_tabs_container = tk.Frame(tabs, bg=BG_CARD)
        # (pas de pack() ici — géré par le toggle)

        dev_items = [
            ('params',  '⚙  Paramètres'),
            ('ocr',     '\U0001f52c  Mode OCR'),
            ('options', '\U0001f527  Options'),
        ]
        for page_id, label in dev_items:
            btn = self._make_nav_tab(self._dev_tabs_container, label, page_id)
            self._nav_buttons[page_id] = btn

        # Toggle "Dev" sur la droite de la nav bar
        self._dev_mode_on = False
        dev_btn_frame = tk.Frame(nav, bg=BG_CARD, cursor='hand2')
        dev_btn_frame.pack(side='right', fill='y', padx=(0, 10))

        self._dev_toggle_lbl = tk.Label(
            dev_btn_frame, text="⚙ Dev",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_CARD,
            padx=10, pady=0,
        )
        self._dev_toggle_lbl.pack(fill='both', expand=True)

        ind_dev = tk.Frame(dev_btn_frame, bg=BG_CARD, height=3)
        ind_dev.pack(fill='x', side='bottom')

        def _toggle_dev(e=None):
            self._dev_mode_on = not self._dev_mode_on
            if self._dev_mode_on:
                self._dev_tabs_container.pack(side='left', fill='y')
                self._dev_toggle_lbl.configure(fg=FG_WARN)
                ind_dev.configure(bg=FG_WARN)
            else:
                self._dev_tabs_container.pack_forget()
                self._dev_toggle_lbl.configure(fg=FG_MUTED)
                ind_dev.configure(bg=BG_CARD)

        dev_btn_frame.bind('<Button-1>', _toggle_dev)
        self._dev_toggle_lbl.bind('<Button-1>', _toggle_dev)

        self._nav_frame = nav   # référence pour pack(after=) de la barre contextuelle

    def _make_nav_tab(self, parent, label, page_id):
        """Crée un onglet horizontal pour la navigation."""
        tab = tk.Frame(parent, bg=BG_CARD, cursor='hand2')
        tab.pack(side='left', fill='y', padx=1)

        lbl = tk.Label(tab, text=label, font=FONT_BOLD,
                       fg=FG_MUTED, bg=BG_CARD, padx=14, pady=0)
        lbl.pack(fill='both', expand=True)

        # Barre indicatrice sous l'onglet actif
        ind = tk.Frame(tab, bg=BG_CARD, height=3)
        ind.pack(fill='x', side='bottom')

        def _on_enter(e, t=tab, lb=lbl):
            if self._current_page != page_id:
                t.configure(bg=BG_PANEL)
                lb.configure(bg=BG_PANEL, fg=FG_TEXT)

        def _on_leave(e, t=tab, lb=lbl):
            if self._current_page != page_id:
                t.configure(bg=BG_CARD)
                lb.configure(bg=BG_CARD, fg=FG_MUTED)

        def _on_click(e, pid=page_id):
            self._show_page(pid)

        for w in (tab, lbl):
            w.bind('<Enter>', _on_enter)
            w.bind('<Leave>', _on_leave)
            w.bind('<Button-1>', _on_click)

        return (tab, lbl, ind)

    def _show_page(self, page_id: str):
        """Affiche la page demandée et met à jour les onglets de navigation."""
        for pid, widgets in self._nav_buttons.items():
            tab, lbl = widgets[0], widgets[1]
            ind = widgets[2] if len(widgets) > 2 else None
            if pid == page_id:
                tab.configure(bg=BG_PANEL)
                lbl.configure(bg=BG_PANEL, fg=COL_ACC)
                if ind:
                    ind.configure(bg=COL_ACC)
            else:
                tab.configure(bg=BG_CARD)
                lbl.configure(bg=BG_CARD, fg=FG_MUTED)
                if ind:
                    ind.configure(bg=BG_CARD)

        if self._current_page and self._current_page in self._pages:
            self._pages[self._current_page].pack_forget()

        self._current_page = page_id
        self._pages[page_id].pack(fill='both', expand=True)

    def _build_toolbar(self):
        """Barre d'actions principale sous le header."""
        tb = tk.Frame(self, bg=BG_PANEL, height=54)
        tb.pack(fill='x')
        tb.pack_propagate(False)

        # Trait de séparation haut
        tk.Frame(tb, bg=BG_CARD, height=1).pack(fill='x', side='top')

        inner = tk.Frame(tb, bg=BG_PANEL)
        inner.pack(fill='both', expand=True, padx=12, pady=9)

        # Bouton principal — créé mais non affiché (le lancement est dans le stepper)
        # Conservé pour que les appels configure_state() / set_text() ne crashent pas
        self._btn_start = RoundedButton(
            inner, text="▶  Lancer la conversion",
            command=self._start,
            bg=COL_ACC, hover_bg=BTN_HVR,
            width=210, height=36, font=FONT_H2
        )
        # NB : pas de .pack() — bouton retiré de la toolbar, accessible via stepper

        # Boutons résultats
        self._btn_excel = self._mini_btn(inner, "  Excel  ",    self._open_excel)
        self._btn_folder = self._mini_btn(inner, "  Dossier  ",  self._open_folder)
        self._btn_audit = self._mini_btn(inner, "  Audit  ",    self._lancer_audit)
        self._btn_observer = self._mini_btn(inner, " Observer ",   self._ouvrir_observateur)

        for b in (self._btn_excel, self._btn_folder,
                  self._btn_audit, self._btn_observer):
            b.pack(side='left', padx=(4, 0))

        self._result_btns = [self._btn_excel, self._btn_folder,
                             self._btn_audit, self._btn_observer]
        for b in self._result_btns:
            b.configure_state('disabled')

        # Côté droit : dico + progressbar
        right = tk.Frame(inner, bg=BG_PANEL)
        right.pack(side='right', fill='y')

        self._btn_dico = RoundedButton(
            right, text="  Enrichir le dico  ",
            command=self._enrich_dictionary,
            bg=BG_CARD, hover_bg=COL_ACC2,
            width=155, height=36, font=FONT_BOLD,
        )
        self._btn_dico.pack(side='right', padx=(6, 0))

        self._pbar = ttk.Progressbar(
            right, style="Trios.Horizontal.TProgressbar",
            orient='horizontal', mode='determinate', maximum=100,
            length=230
        )
        self._pbar.pack(side='right', padx=(0, 8))

    def _build_status_bar(self):
        """Barre de statut fine en bas de la fenêtre."""
        bar = tk.Frame(self, bg=BG_LOG, height=26)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)

        tk.Frame(bar, bg=BG_CARD, height=1).pack(fill='x', side='top')

        self._status_lbl = tk.Label(
            bar,
            text="Prêt — sélectionnez les fichiers et lancez la conversion.",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_LOG, anchor='w'
        )
        self._status_lbl.pack(side='left', fill='x', expand=True,
                              padx=12, pady=4)

    def _mini_btn(self, parent, text, cmd):
        return RoundedButton(parent, text=text, command=cmd,
                             bg=BG_CARD, hover_bg=COL_ACC2,
                             width=110, height=36,
                             font=FONT_BOLD, state='disabled')

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_page_accueil(self, parent) -> tk.Frame:
        """Page d'accueil : titre + étapes en haut, animation en bas."""
        page = tk.Frame(parent, bg=BG_MAIN)

        # Zone 1 — En-tête bienvenue
        welcome_frame = tk.Frame(page, bg=BG_MAIN)
        welcome_frame.pack(fill='x', padx=32, pady=(20, 8))

        tk.Label(welcome_frame,
                 text="Bienvenue dans TriosSeconverter",
                 font=FONT_H1, fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w')
        tk.Label(welcome_frame,
                 text="Convertissez vos tableaux de borniers"
                      " électriques en Excel en quelques clics.",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN).pack(anchor='w', pady=(4, 0))

        # Zone 2 — Cartes de choix du workflow
        self._build_workflow_cards(page)

        # Zone 3 — Bande d'animation bord à bord, plein bas
        anim_outer = tk.Frame(page, bg=BG_LOG)
        anim_outer.pack(fill='both', expand=True, pady=(10, 0))

        tk.Label(anim_outer,
                 text="La magie de la conversion",
                 font=("Segoe UI", 8, "italic"), fg=FG_MUTED,
                 bg=BG_LOG).pack(anchor='w', padx=12, pady=(4, 0))

        anim_canvas = tk.Canvas(anim_outer, height=216,
                                bg=BG_LOG, highlightthickness=0)
        anim_canvas.pack(fill='x')

        self._welcome_anim = WelcomeAnimation(anim_canvas)

        def _on_anim_resize(event):
            if event.width > 100:
                self._welcome_anim._BX = event.width // 2 + 30
        anim_canvas.bind('<Configure>', _on_anim_resize)

        return page

    # ── Workflow UX — cartes d'accueil ────────────────────────────────

    def _build_workflow_cards(self, parent):
        """3 cartes de choix du type de traitement (Tableaux / Dessins / Mixte)."""
        cards_frame = tk.Frame(parent, bg=BG_PANEL, padx=24, pady=14)
        cards_frame.pack(fill='x', padx=32, pady=(0, 0))

        tk.Label(cards_frame, text="Que souhaitez-vous produire ?",
                 font=FONT_BOLD, fg=COL_ACC, bg=BG_PANEL).pack(anchor='w', pady=(0, 10))

        row = tk.Frame(cards_frame, bg=BG_PANEL)
        row.pack(fill='x')

        cards = [
            {
                "titre": "📊  Transformation tableaux",
                "desc":  "Borniers électriques scannés → Excel structuré",
                "detail": "Outils : Reformater  •  Dictionnaire  •  Logs",
                "mode": "tableaux",
                "couleur": COL_ACC,
            },
            {
                "titre": "📐  Transformation dessins",
                "desc":  "Plans PDF/images → DXF AutoCAD",
                "detail": "Outils : Aperçu  •  Calibration  •  Export DXF",
                "mode": "dessins",
                "couleur": COL_ACC2,
            },
            {
                "titre": "🔀  Tableaux + Dessins",
                "desc":  "Document mixte → Excel + DXF",
                "detail": "Outils : Classification  •  Tableaux  •  Dessins",
                "mode": "mixte",
                "couleur": "#27AE60",
            },
        ]
        for card in cards:
            self._make_workflow_card(row, card)

    def _make_workflow_card(self, parent, card: dict):
        """Carte cliquable de sélection de workflow avec survol coloré."""
        frame = tk.Frame(parent, bg=BG_CARD, padx=16, pady=12,
                         relief='flat', cursor='hand2')
        frame.pack(side='left', fill='both', expand=True, padx=(0, 10))

        # Barre de couleur en haut de la carte
        barre = tk.Frame(frame, bg=card["couleur"], height=4)
        barre.pack(fill='x', pady=(0, 8))

        lbl_titre = tk.Label(frame, text=card["titre"], font=FONT_H2,
                             fg=FG_TEXT, bg=BG_CARD, anchor='w')
        lbl_titre.pack(fill='x')

        lbl_desc = tk.Label(frame, text=card["desc"], font=FONT_MAIN,
                            fg=FG_MUTED, bg=BG_CARD, anchor='w')
        lbl_desc.pack(fill='x', pady=(4, 8))

        lbl_detail = tk.Label(frame, text=card["detail"],
                              font=("Segoe UI", 8),
                              fg=card["couleur"], bg=BG_CARD, anchor='w')
        lbl_detail.pack(fill='x')

        # Indicateur de sélection (barre colorée en bas de la carte)
        ind = tk.Frame(frame, bg=BG_CARD, height=3)
        ind.pack(fill='x', pady=(8, 0))
        self._card_indicators[card["mode"]] = ind

        all_widgets = [frame, barre, lbl_titre, lbl_desc, lbl_detail, ind]

        def _on_click(mode=card["mode"], col=card["couleur"]):
            self._select_workflow(mode, col)

        def _on_enter(e, widgets=all_widgets):
            for w in widgets:
                try:
                    w.configure(bg=BG_PANEL)
                except Exception:
                    pass

        def _on_leave(e, widgets=all_widgets, mode=card["mode"],
                      orig_col=card["couleur"]):
            if self._workflow_mode.get() == mode:
                return
            for w in widgets:
                try:
                    w.configure(bg=BG_CARD)
                except Exception:
                    pass
            # Le label couleur garde sa couleur d'origine
            try:
                lbl_detail.configure(fg=orig_col)
            except Exception:
                pass

        for w in all_widgets:
            w.bind('<Button-1>', lambda e, fn=_on_click: fn())
            w.bind('<Enter>', _on_enter)
            w.bind('<Leave>', _on_leave)

    def _select_workflow(self, mode: str, couleur: str):
        """Sélectionne le workflow, met à jour les indicateurs et la barre contextuelle."""
        self._workflow_mode.set(mode)

        for m, ind in self._card_indicators.items():
            if m == mode:
                colors = {"tableaux": COL_ACC, "dessins": COL_ACC2, "mixte": "#27AE60"}
                ind.configure(bg=colors.get(m, COL_ACC))
            else:
                ind.configure(bg=BG_CARD)

        self._update_context_toolbar()

        if mode == "tableaux":
            self._stepper_goto(0)
            self._show_page('stepper')
        elif mode == "dessins":
            self._show_page('dessins')
        elif mode == "mixte":
            self._show_page('mixte')

    # ── Workflow UX — barre contextuelle ──────────────────────────────

    def _build_context_toolbar(self):
        """Barre d'outils contextuelle — masquée jusqu'au choix d'un workflow."""
        self._ctx_bar = tk.Frame(self, bg="#0d2440", height=38)
        self._ctx_bar.pack_propagate(False)
        # NB : pas de pack() ici — géré par _update_context_toolbar()

        inner = tk.Frame(self._ctx_bar, bg="#0d2440")
        inner.pack(fill='both', expand=True, padx=10, pady=5)

        tk.Label(inner, text="OUTILS TABLEAUX :",
                 font=("Segoe UI", 8, "bold"),
                 fg=COL_ACC, bg="#0d2440").pack(side='left', padx=(0, 12))

        self._ctx_btn_format = self._ctx_btn(
            inner, "📐 Reformater", self._ctx_reformater)
        self._ctx_btn_dico = self._ctx_btn(
            inner, "📚 Enrichir dictionnaire", self._enrich_dictionary)
        self._ctx_btn_log = self._ctx_btn(
            inner, "📋 Ouvrir log", self._ouvrir_observateur)
        self._ctx_btn_folder = self._ctx_btn(
            inner, "📂 Dossier sortie", self._open_folder)

        for btn in (self._ctx_btn_format, self._ctx_btn_dico,
                    self._ctx_btn_log, self._ctx_btn_folder):
            btn.pack(side='left', padx=(0, 8))

    def _ctx_btn(self, parent, text: str, command) -> tk.Button:
        """Bouton compact pour la barre contextuelle."""
        return tk.Button(
            parent, text=text, font=("Segoe UI", 8),
            bg="#1a3a5c", fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=8, pady=3, cursor='hand2',
            command=command,
        )

    def _ctx_reformater(self):
        """Barre contextuelle → aller à la page Formater Excel."""
        self._show_page('format')

    def _update_context_toolbar(self):
        """Affiche ou masque la barre contextuelle selon le workflow actif."""
        if self._nav_frame is None:
            return
        mode = self._workflow_mode.get()
        if mode == "tableaux":
            self._ctx_bar.pack(fill='x', after=self._nav_frame)
        else:
            self._ctx_bar.pack_forget()
        self._update_ctx_btn_states()

    def _update_ctx_btn_states(self):
        """Active/désactive les boutons selon l'état courant (résultat, source, dossier)."""
        if not hasattr(self, '_ctx_btn_format'):
            return
        has_result = self._result is not None
        has_excel = bool(self._format_excel_path.get().strip())
        has_outdir = bool(self._output_dir.get().strip())

        def _state(cond):
            return ('normal', FG_TEXT) if cond else ('disabled', FG_MUTED)

        s, c = _state(has_result or has_excel)
        self._ctx_btn_format.configure(state=s, fg=c)

        s, c = _state(has_result)
        self._ctx_btn_dico.configure(state=s, fg=c)

        # Log : toujours accessible (logs de sessions précédentes)
        self._ctx_btn_log.configure(state='normal', fg=FG_TEXT)

        s, c = _state(has_outdir)
        self._ctx_btn_folder.configure(state=s, fg=c)

    # ── Workflow UX — stepper 3 étapes ───────────────────────────────

    def _build_page_stepper(self, parent) -> tk.Frame:
        """Page assistant 3 étapes pour le workflow tableaux."""
        page = tk.Frame(parent, bg=BG_MAIN)

        self._stepper_frames: list = []
        self._stepper_circle_lbls: list = []
        self._stepper_step_lbls: list = []
        self._stepper_step = 0

        # ── Indicateur d'étapes ───────────────────────────────────
        indicator = tk.Frame(page, bg=BG_PANEL, padx=24, pady=10)
        indicator.pack(fill='x')

        steps_info = [
            ("1", "Source & destination"),
            ("2", "Modèle & OCR"),
            ("3", "Lancer"),
        ]
        for i, (num, label) in enumerate(steps_info):
            circ = tk.Label(indicator, text=f" {num} ",
                            font=("Segoe UI", 9, "bold"),
                            fg="white", bg=FG_MUTED, padx=4, pady=2)
            circ.pack(side='left')
            self._stepper_circle_lbls.append(circ)

            step_lbl = tk.Label(indicator, text=f" {label} ",
                                font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL)
            step_lbl.pack(side='left')
            self._stepper_step_lbls.append(step_lbl)

            if i < len(steps_info) - 1:
                tk.Label(indicator, text="  ────  ",
                         fg=FG_MUTED, bg=BG_PANEL,
                         font=FONT_MONO).pack(side='left')

        # ── Zone de contenu ───────────────────────────────────────
        content = tk.Frame(page, bg=BG_MAIN)
        content.pack(fill='both', expand=True)

        s1 = tk.Frame(content, bg=BG_MAIN)
        self._build_stepper_step1(s1)
        self._stepper_frames.append(s1)

        s2 = tk.Frame(content, bg=BG_MAIN)
        self._build_stepper_step2(s2)
        self._stepper_frames.append(s2)

        s3 = tk.Frame(content, bg=BG_MAIN)
        self._build_stepper_step3(s3)
        self._stepper_frames.append(s3)

        # ── Barre de navigation ───────────────────────────────────
        nav_bar = tk.Frame(page, bg=BG_PANEL)
        nav_bar.pack(fill='x', padx=24, pady=(4, 10))

        self._btn_stepper_prev = tk.Button(
            nav_bar, text="← Précédent",
            font=FONT_BOLD, bg=BG_CARD, fg=FG_MUTED,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=16, pady=7, cursor='hand2',
            state='disabled',
            command=self._stepper_prev,
        )
        self._btn_stepper_prev.pack(side='left', padx=(8, 0), pady=8)

        self._btn_stepper_next = tk.Button(
            nav_bar, text="Suivant →",
            font=FONT_BOLD, bg=COL_ACC, fg="white",
            activebackground=BTN_HVR, activeforeground="white",
            relief='flat', padx=16, pady=7, cursor='hand2',
            command=self._stepper_next,
        )
        self._btn_stepper_next.pack(side='right', padx=(0, 8), pady=8)

        self._stepper_goto(0)
        return page

    def _build_stepper_step1(self, parent):
        """Étape 1 — Source et destination."""
        lf = tk.LabelFrame(parent, text="Source et destination",
                           font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                           labelanchor='nw', bd=1, relief='groove')
        lf.pack(fill='x', padx=0, pady=(8, 0))

        inner = tk.Frame(lf, bg=BG_PANEL, padx=20, pady=16)
        inner.pack(fill='both', expand=True)
        inner.columnconfigure(0, weight=1)

        # Doc.1
        tk.Label(
            inner,
            text="Doc. 1 — Source (Word .docx, PDF, dossier d'images, log .jsonl) :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 3))

        tk.Entry(inner, textvariable=self._word_file,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=1, column=0, sticky='ew', padx=(0, 4), pady=(0, 8))

        btn_src = tk.Frame(inner, bg=BG_PANEL)
        btn_src.grid(row=1, column=1, pady=(0, 8))

        for btn_text, btn_bg, btn_cmd in [
            ("Fichier…",   COL_ACC2,   self._browse_word),
            ("📁 Images…", '#27AE60',  self._browse_images_folder),
            ("📋 Log…",    '#8E44AD',  self._browse_log_jsonl),
        ]:
            tk.Button(btn_src, text=btn_text, font=FONT_MAIN,
                      bg=btn_bg, fg="white",
                      activebackground=COL_ACC, activeforeground="white",
                      relief='flat', padx=8, pady=5, cursor='hand2',
                      command=btn_cmd).pack(side='left', padx=(0, 4))

        # Doc.2
        tk.Label(
            inner,
            text="Doc. 2 optionnel — Word structuré (.docx) :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=2, column=0, columnspan=2, sticky='w', pady=(8, 3))

        tk.Entry(inner, textvariable=self._tables_word_file,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=3, column=0, sticky='ew', padx=(0, 4), pady=(0, 8))

        tk.Button(inner, text="Choisir…", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_TEXT,
                  activebackground=COL_ACC2, activeforeground="white",
                  relief='flat', padx=10, pady=5, cursor='hand2',
                  command=self._browse_tables_word,
        ).grid(row=3, column=1, pady=(0, 8))

        # Destination
        tk.Label(
            inner,
            text="Dossier de destination :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=4, column=0, columnspan=2, sticky='w', pady=(8, 3))

        tk.Entry(inner, textvariable=self._output_dir,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=5, column=0, sticky='ew', padx=(0, 4))

        tk.Button(inner, text="Dossier…", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_TEXT,
                  activebackground=COL_ACC2, activeforeground="white",
                  relief='flat', padx=10, pady=5, cursor='hand2',
                  command=self._browse_output,
        ).grid(row=5, column=1)

    def _build_stepper_step2(self, parent):
        """Étape 2 — Modèle de tableau et moteur OCR."""
        # Modèle
        lf_tpl = tk.LabelFrame(parent, text="Modèle de tableau",
                               font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                               labelanchor='nw', bd=1, relief='groove')
        lf_tpl.pack(fill='x', pady=(8, 0))

        inner_tpl = tk.Frame(lf_tpl, bg=BG_PANEL, padx=20, pady=12)
        inner_tpl.pack(fill='x')

        row_tpl = tk.Frame(inner_tpl, bg=BG_PANEL)
        row_tpl.pack(fill='x', pady=(0, 8))

        tk.Label(row_tpl, text="Modèle :", font=FONT_BOLD,
                 fg=FG_TEXT, bg=BG_PANEL).pack(side='left')

        self._stepper_tpl_combo = ttk.Combobox(
            row_tpl, textvariable=self._tpl_var,
            values=self._tpl_manager.names(),
            state='readonly', font=FONT_MAIN, width=28,
        )
        self._stepper_tpl_combo.pack(side='left', padx=(10, 0))

        self._stepper_tpl_desc = tk.Label(
            inner_tpl, text="",
            font=FONT_MONO, fg=FG_TEXT, bg=BG_PANEL,
            anchor='w', wraplength=500, justify='left',
        )
        self._stepper_tpl_desc.pack(fill='x')
        self._tpl_var.trace_add('write', self._stepper_update_tpl_desc)
        self._stepper_update_tpl_desc()

        # Moteur OCR
        lf_ocr = tk.LabelFrame(parent, text="Moteur OCR",
                               font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                               labelanchor='nw', bd=1, relief='groove')
        lf_ocr.pack(fill='x', pady=(12, 0))

        radio_row = tk.Frame(lf_ocr, bg=BG_PANEL)
        radio_row.pack(fill='x', padx=12, pady=10)

        modes = [
            ("Tesseract (local)",      "tesseract"),
            ("Claude Vision (API)",    "claude"),
            ("Docling (local IA)",     "docling"),
            ("Ollama Vision (local)",  "ollama"),
            ("Hybride",                "hybrid"),
            ("Agent Claude",           "agent"),
        ]
        for lbl, val in modes:
            tk.Radiobutton(
                radio_row, text=lbl, variable=self._ocr_mode, value=val,
                font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
                selectcolor=BG_CARD, activebackground=BG_PANEL,
                activeforeground=FG_TEXT,
                command=self._on_ocr_mode_change,
            ).pack(side='left', padx=(0, 12))

        # Clé API — visible uniquement pour Claude/Hybride/Agent
        self._stepper_api_key_frame = tk.Frame(lf_ocr, bg=BG_PANEL)
        # (pack/pack_forget géré par _on_ocr_mode_change)

        tk.Label(self._stepper_api_key_frame, text="Clé API Anthropic :",
                 font=FONT_BOLD, fg=FG_WARN, bg=BG_PANEL,
        ).pack(side='left', padx=(12, 0))

        tk.Entry(
            self._stepper_api_key_frame, textvariable=self._claude_key,
            font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', width=44, show='*',
        ).pack(side='left', padx=(8, 0))

        tk.Label(
            self._stepper_api_key_frame,
            text="  console.anthropic.com",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left')

        # ID de session agent — visible uniquement en mode "agent"
        self._stepper_agent_frame = tk.Frame(lf_ocr, bg=BG_PANEL)

        tk.Label(self._stepper_agent_frame, text="ID de session agent :",
                 font=FONT_BOLD, fg=FG_WARN, bg=BG_PANEL,
        ).pack(side='left', padx=(12, 0))

        tk.Entry(
            self._stepper_agent_frame, textvariable=self._agent_session_id,
            font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', width=40,
        ).pack(side='left', padx=(8, 0))

        tk.Label(
            self._stepper_agent_frame,
            text="  Format : sesn_XXXX…",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left')

        # Options de validation
        lf_opt = tk.LabelFrame(parent, text="Options de conversion",
                               font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                               labelanchor='nw', bd=1, relief='groove')
        lf_opt.pack(fill='x', pady=(12, 0))

        tk.Radiobutton(
            lf_opt,
            text="Automatique — conversion sans interruption",
            variable=self._validation_interactive, value=False,
            font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            activeforeground=FG_TEXT,
        ).pack(anchor='w', padx=12, pady=(10, 4))

        tk.Radiobutton(
            lf_opt,
            text="Manuelle page par page — vérification à chaque page PDF",
            variable=self._validation_interactive, value=True,
            font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            activeforeground=FG_TEXT,
        ).pack(anchor='w', padx=12, pady=(0, 10))

        # Appliquer l'état initial (au cas où le mode OCR est déjà Claude)
        self._on_ocr_mode_change()

    def _build_stepper_step3(self, parent):
        """Étape 3 — Récapitulatif et lancement."""
        lf = tk.LabelFrame(parent, text="Récapitulatif",
                           font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                           labelanchor='nw', bd=1, relief='groove')
        lf.pack(fill='x', pady=(8, 0))

        inner = tk.Frame(lf, bg=BG_PANEL, padx=20, pady=14)
        inner.pack(fill='x')
        inner.columnconfigure(1, weight=1)

        recap_items = [
            ("Source :",       "_stepper_recap_source"),
            ("Destination :",  "_stepper_recap_dest"),
            ("Modèle :",       "_stepper_recap_tpl"),
            ("Moteur OCR :",   "_stepper_recap_ocr"),
        ]
        for i, (lbl_text, attr) in enumerate(recap_items):
            tk.Label(inner, text=lbl_text, font=FONT_BOLD,
                     fg=FG_MUTED, bg=BG_PANEL, anchor='w', width=14,
            ).grid(row=i, column=0, sticky='w', pady=4)

            val_lbl = tk.Label(inner, text="—",
                               font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
                               anchor='w', wraplength=480, justify='left')
            val_lbl.grid(row=i, column=1, sticky='w', padx=(8, 0), pady=4)
            setattr(self, attr, val_lbl)

        # Bouton Lancer
        btn_frame = tk.Frame(parent, bg=BG_MAIN, pady=16)
        btn_frame.pack(fill='x')

        RoundedButton(
            btn_frame,
            text="▶  Lancer la conversion",
            command=self._start,
            bg=COL_ACC, hover_bg=BTN_HVR,
            width=240, height=42, font=FONT_H2,
        ).pack(anchor='center')

        tk.Label(
            btn_frame,
            text="Le journal de progression apparaît dans l'onglet Mode OCR.",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_MAIN,
        ).pack(anchor='center', pady=(8, 0))

    def _stepper_update_tpl_desc(self, *_):
        """Met à jour la description du modèle sélectionné dans le stepper."""
        if not hasattr(self, '_stepper_tpl_desc'):
            return
        name = self._tpl_var.get()
        tpl = self._tpl_manager.get(name)
        if tpl:
            cols = ', '.join(tpl.columns)
            self._stepper_tpl_desc.configure(
                text=f"{len(tpl.columns)} colonne(s) : {cols}"
            )
        else:
            self._stepper_tpl_desc.configure(text="")

    def _stepper_refresh_recap(self):
        """Rafraîchit les labels de récapitulatif à l'étape 3."""
        if not hasattr(self, '_stepper_recap_source'):
            return
        src = self._word_file.get().strip()
        self._stepper_recap_source.configure(
            text=src if src else "— non sélectionné —",
            fg=FG_TEXT if src else FG_ERR,
        )
        dest = self._output_dir.get().strip()
        self._stepper_recap_dest.configure(
            text=dest if dest else "— non sélectionné —",
            fg=FG_TEXT if dest else FG_ERR,
        )
        self._stepper_recap_tpl.configure(text=self._tpl_var.get())
        modes_fr = {
            "tesseract": "Tesseract (local)",
            "claude":    "Claude Vision (API)",
            "docling":   "Docling — IBM (local IA)",
            "ollama":    "Ollama Vision (local IA)",
            "hybrid":    "Hybride Ollama+Claude",
            "agent":     "Agent Image Data Extractor",
        }
        self._stepper_recap_ocr.configure(
            text=modes_fr.get(self._ocr_mode.get(), self._ocr_mode.get())
        )

    def _stepper_goto(self, step: int):
        """Affiche l'étape N du stepper et met à jour l'indicateur."""
        self._stepper_step = step
        n = len(self._stepper_frames)

        # Show/hide frames
        for i, frame in enumerate(self._stepper_frames):
            if i == step:
                frame.pack(fill='both', expand=True, padx=24, pady=8)
            else:
                frame.pack_forget()

        # Update circles + labels
        for i, (circ, lbl) in enumerate(
            zip(self._stepper_circle_lbls, self._stepper_step_lbls)
        ):
            if i < step:
                circ.configure(bg=FG_OK, fg="white")
                lbl.configure(fg=FG_OK)
            elif i == step:
                circ.configure(bg=COL_ACC, fg="white")
                lbl.configure(fg=COL_ACC)
            else:
                circ.configure(bg=FG_MUTED, fg=BG_MAIN)
                lbl.configure(fg=FG_MUTED)

        # Update nav buttons
        prev_ok = step > 0
        self._btn_stepper_prev.configure(
            state='normal' if prev_ok else 'disabled',
            fg=FG_TEXT if prev_ok else FG_MUTED,
        )
        if step == n - 1:
            # Dernière étape : le bouton "Suivant" devient "Lancer"
            self._btn_stepper_next.configure(
                text="▶  Lancer",
                bg=FG_OK,
                command=self._start,
            )
            self._stepper_refresh_recap()
        else:
            self._btn_stepper_next.configure(
                text="Suivant →",
                bg=COL_ACC,
                command=self._stepper_next,
            )

    def _stepper_validate_step(self, step: int) -> bool:
        """Valide les champs requis avant de passer à l'étape suivante."""
        if step == 0:
            src = self._word_file.get().strip()
            dest = self._output_dir.get().strip()
            if not src:
                messagebox.showwarning(
                    "Source manquante",
                    "Veuillez sélectionner le document source (Doc. 1)\n"
                    "avant de continuer.",
                )
                return False
            if not Path(src).exists():
                messagebox.showerror(
                    "Fichier introuvable",
                    f"Le fichier ou dossier suivant est introuvable :\n{src}",
                )
                return False
            if not dest:
                messagebox.showwarning(
                    "Destination manquante",
                    "Veuillez sélectionner le dossier de destination\n"
                    "avant de continuer.",
                )
                return False
            return True

        if step == 1:
            mode = self._ocr_mode.get()
            if mode in ('claude', 'hybrid', 'agent'):
                key = self._claude_key.get().strip()
                if not key:
                    messagebox.showwarning(
                        "Clé API manquante",
                        f"Le moteur « {mode} » nécessite une clé API Anthropic.\n"
                        "Renseignez-la dans le champ ci-dessus.",
                    )
                    return False
            return True

        return True

    def _stepper_next(self):
        if self._stepper_step < len(self._stepper_frames) - 1:
            if self._stepper_validate_step(self._stepper_step):
                self._stepper_goto(self._stepper_step + 1)

    def _stepper_prev(self):
        if self._stepper_step > 0:
            self._stepper_goto(self._stepper_step - 1)

    # ── Workflow UX — dashboard de conversion ─────────────────────────

    # ── Workflow UX — pages dessins et mixte (squelettes) ────────────

    def _build_page_dessins(self, parent) -> tk.Frame:
        """Page squelette — Transformation dessins (en développement)."""
        page = tk.Frame(parent, bg=BG_MAIN)

        # ── En-tête ───────────────────────────────────────────────
        hdr = tk.Frame(page, bg=BG_CARD, height=50)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text="📐  Transformation dessins",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD,
        ).pack(side='left', padx=20, pady=12)

        tk.Label(hdr, text=" En développement ",
                 font=("Segoe UI", 8), fg="white", bg=FG_WARN,
                 padx=6, pady=2,
        ).pack(side='left', pady=18)

        tk.Button(hdr, text="← Accueil", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_MUTED,
                  activebackground=COL_ACC2, activeforeground="white",
                  relief='flat', padx=12, pady=6, cursor='hand2',
                  command=lambda: self._show_page('accueil'),
        ).pack(side='right', padx=20, pady=12)

        # ── Contenu ───────────────────────────────────────────────
        body = tk.Frame(page, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=40, pady=24)

        # Description
        tk.Label(body,
                 text="Ce module permettra d'extraire et de vectoriser des plans "
                      "techniques scannés ou PDF vers AutoCAD (DXF).",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN,
                 wraplength=600, justify='left',
        ).pack(anchor='w', pady=(0, 24))

        # Étapes prévues
        steps_lf = tk.LabelFrame(body, text="Étapes prévues",
                                 font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                 labelanchor='nw', bd=1, relief='groove')
        steps_lf.pack(fill='x', pady=(0, 20))

        steps = [
            ("1", "Détection automatique",
             "Identifie si le PDF est vectoriel ou scanné (image). "
             "Adapte le pipeline en conséquence."),
            ("2", "Profil dessin",
             "Paramètres de l'export : conserver textes, détecter cartouche, "
             "calque de contrôle pour éléments incertains."),
            ("3", "Analyse et aperçu",
             "Extrait les lignes, courbes, textes. "
             "Affiche un aperçu vectoriel côte à côte avec le plan original."),
            ("4", "Export DXF",
             "Produit un fichier .dxf autonome sans XREF, sans image attachée. "
             "Compatible AutoCAD direct."),
        ]
        for num, titre, desc in steps:
            row = tk.Frame(steps_lf, bg=BG_PANEL)
            row.pack(fill='x', padx=16, pady=8)

            tk.Label(row, text=num, font=("Segoe UI", 11, "bold"),
                     fg="white", bg=COL_ACC2,
                     width=2, padx=6, pady=2,
            ).pack(side='left', anchor='n')

            col = tk.Frame(row, bg=BG_PANEL)
            col.pack(side='left', fill='x', expand=True, padx=(12, 0))

            tk.Label(col, text=titre, font=FONT_BOLD,
                     fg=FG_TEXT, bg=BG_PANEL, anchor='w',
            ).pack(fill='x')
            tk.Label(col, text=desc, font=FONT_MAIN,
                     fg=FG_MUTED, bg=BG_PANEL, anchor='w', wraplength=520,
            ).pack(fill='x')

        # Technologies prévues
        tech_lf = tk.LabelFrame(body, text="Technologies envisagées",
                                font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                labelanchor='nw', bd=1, relief='groove')
        tech_lf.pack(fill='x')

        tech_row = tk.Frame(tech_lf, bg=BG_PANEL)
        tech_row.pack(fill='x', padx=16, pady=10)

        techs = [
            ("PyMuPDF", "Extraction vectorielle depuis PDF", COL_ACC2),
            ("OpenCV", "Traitement des plans scannés", "#27AE60"),
            ("ezdxf", "Écriture du fichier DXF", COL_ACC),
        ]
        for nom, role, col_t in techs:
            f = tk.Frame(tech_row, bg=BG_LOG, padx=10, pady=8)
            f.pack(side='left', padx=(0, 8))
            tk.Label(f, text=nom, font=FONT_BOLD, fg=col_t, bg=BG_LOG).pack()
            tk.Label(f, text=role, font=("Segoe UI", 8),
                     fg=FG_MUTED, bg=BG_LOG).pack()

        return page

    def _build_page_mixte(self, parent) -> tk.Frame:
        """Page squelette — Transformation tableaux + dessins (en développement)."""
        page = tk.Frame(parent, bg=BG_MAIN)

        hdr = tk.Frame(page, bg=BG_CARD, height=50)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)

        tk.Label(hdr, text="🔀  Tableaux + Dessins",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD,
        ).pack(side='left', padx=20, pady=12)

        tk.Label(hdr, text=" En développement ",
                 font=("Segoe UI", 8), fg="white", bg=FG_WARN,
                 padx=6, pady=2,
        ).pack(side='left', pady=18)

        tk.Button(hdr, text="← Accueil", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_MUTED,
                  activebackground=COL_ACC2, activeforeground="white",
                  relief='flat', padx=12, pady=6, cursor='hand2',
                  command=lambda: self._show_page('accueil'),
        ).pack(side='right', padx=20, pady=12)

        body = tk.Frame(page, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=40, pady=24)

        tk.Label(body,
                 text="Ce mode traitera les documents contenant à la fois des tableaux "
                      "de borniers et des plans techniques. Il orchestrera les deux pipelines "
                      "de façon coordonnée et produira un classeur Excel et un fichier DXF.",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN,
                 wraplength=620, justify='left',
        ).pack(anchor='w', pady=(0, 24))

        phases_lf = tk.LabelFrame(body, text="Déroulement prévu",
                                  font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                  labelanchor='nw', bd=1, relief='groove')
        phases_lf.pack(fill='x')

        phases = [
            ("Classification", "L'application classe automatiquement les pages : "
             "tableaux, plans, mixtes, ignorées. L'utilisateur peut corriger."),
            ("Traitement parallèle", "Les borniers sont extraits vers Excel. "
             "Les plans sont vectorisés vers DXF. Les deux pipelines s'exécutent en séquence."),
            ("Rapport global", "Un rapport récapitule les deux productions : "
             "borniers traités, plans exportés, erreurs détectées."),
        ]
        for titre, desc in phases:
            row = tk.Frame(phases_lf, bg=BG_PANEL)
            row.pack(fill='x', padx=16, pady=8)

            tk.Label(row, text="→", font=FONT_H2,
                     fg=COL_ACC, bg=BG_PANEL,
            ).pack(side='left', padx=(0, 12))

            col = tk.Frame(row, bg=BG_PANEL)
            col.pack(side='left', fill='x', expand=True)

            tk.Label(col, text=titre, font=FONT_BOLD,
                     fg=FG_TEXT, bg=BG_PANEL, anchor='w',
            ).pack(fill='x')
            tk.Label(col, text=desc, font=FONT_MAIN,
                     fg=FG_MUTED, bg=BG_PANEL, anchor='w', wraplength=540,
            ).pack(fill='x')

        tk.Label(body,
                 text="Disponible après la finalisation du module Transformation dessins.",
                 font=("Segoe UI", 8, "italic"), fg=FG_MUTED, bg=BG_MAIN,
        ).pack(anchor='w', pady=(16, 0))

        return page

    def _build_page_dashboard(self, parent) -> tk.Frame:
        """Dashboard visuel pendant la conversion (source | progression | modèle)."""
        page = tk.Frame(parent, bg=BG_MAIN)
        self._dash_anim_idx = 0

        # ── En-tête ───────────────────────────────────────────────
        hdr = tk.Frame(page, bg=BG_CARD, height=50)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        self._dash_title_lbl = tk.Label(
            hdr, text="⏳  Conversion en cours…",
            font=FONT_H2, fg=FG_WARN, bg=BG_CARD,
        )
        self._dash_title_lbl.pack(side='left', padx=20, pady=12)

        self._dash_mode_badge = tk.Label(
            hdr, text="",
            font=("Segoe UI", 8), fg=FG_TEXT, bg=COL_ACC2,
            padx=8, pady=3,
        )
        self._dash_mode_badge.pack(side='left', pady=17)

        # ── Journal miroir (side='bottom' — réservé en dernier) ───
        log_zone = tk.Frame(page, bg=BG_MAIN)
        log_zone.pack(fill='both', expand=True, side='bottom',
                      padx=16, pady=(0, 8))

        log_hdr = tk.Frame(log_zone, bg=BG_MAIN)
        log_hdr.pack(fill='x', pady=(4, 4))

        tk.Label(log_hdr, text="Journal de conversion",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_MAIN,
                 anchor='w').pack(side='left')

        tk.Button(
            log_hdr, text="Voir onglet Mode OCR →",
            font=("Segoe UI", 8), bg=BG_CARD, fg=FG_MUTED,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=8, pady=2, cursor='hand2',
            command=lambda: self._show_page('ocr'),
        ).pack(side='right')

        self._dash_log_box = scrolledtext.ScrolledText(
            log_zone, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', state='disabled', height=8,
            padx=10, pady=6,
        )
        self._dash_log_box.pack(fill='both', expand=True)
        for tag, color in (('ok', FG_OK), ('err', FG_ERR),
                           ('warn', FG_WARN), ('muted', FG_MUTED),
                           ('info', FG_TEXT)):
            self._dash_log_box.tag_config(tag, foreground=color)

        # ── Barre de statut ───────────────────────────────────────
        sbar = tk.Frame(page, bg=BG_CARD, height=28)
        sbar.pack(fill='x', side='bottom')
        sbar.pack_propagate(False)

        tk.Frame(sbar, bg=BG_PANEL, height=1).pack(fill='x', side='top')
        inner_sbar = tk.Frame(sbar, bg=BG_CARD)
        inner_sbar.pack(fill='x', padx=14, pady=4)

        self._dash_timer_lbl = tk.Label(
            inner_sbar, text="⏱  00:00",
            font=("Segoe UI", 8, "bold"), fg=COL_ACC, bg=BG_CARD,
        )
        self._dash_timer_lbl.pack(side='left')

        self._dash_status_lbl = tk.Label(
            inner_sbar, text="",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_CARD,
        )
        self._dash_status_lbl.pack(side='left', padx=(20, 0))

        # ── Zone 3 colonnes (entre header et status bar) ──────────
        cols_outer = tk.Frame(page, bg=BG_MAIN, height=210)
        cols_outer.pack(fill='x', side='top', padx=16, pady=(10, 6))
        cols_outer.pack_propagate(False)

        # Colonne gauche — SOURCE
        left_col = tk.Frame(cols_outer, bg=BG_PANEL, width=220)
        left_col.pack(side='left', fill='both', padx=(0, 5))
        left_col.pack_propagate(False)

        tk.Label(left_col, text="SOURCE",
                 font=("Segoe UI", 8, "bold"), fg=FG_MUTED,
                 bg=BG_PANEL).pack(anchor='w', padx=10, pady=(10, 4))

        self._dash_src_lbl = tk.Label(
            left_col, text="—",
            font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
            wraplength=200, justify='left', anchor='w',
        )
        self._dash_src_lbl.pack(fill='x', padx=10, pady=(0, 6))

        # Spinner centré
        self._dash_anim_lbl = tk.Label(
            left_col, text="",
            font=("Segoe UI", 36), fg=COL_ACC, bg=BG_PANEL,
        )
        self._dash_anim_lbl.pack(expand=True, fill='both')

        # Colonne centre — PROGRESSION
        mid_col = tk.Frame(cols_outer, bg=BG_LOG)
        mid_col.pack(side='left', fill='both', expand=True, padx=(0, 5))

        tk.Label(mid_col, text="PROGRESSION",
                 font=("Segoe UI", 8, "bold"), fg=FG_MUTED,
                 bg=BG_LOG).pack(anchor='w', padx=14, pady=(10, 6))

        self._dash_pbar = ttk.Progressbar(
            mid_col, style="Trios.Horizontal.TProgressbar",
            orient='horizontal', mode='determinate', maximum=100,
        )
        self._dash_pbar.pack(fill='x', padx=14, pady=(0, 12))

        self._dash_page_lbl = tk.Label(
            mid_col, text="Démarrage…",
            font=("Segoe UI", 15, "bold"), fg=FG_TEXT, bg=BG_LOG,
        )
        self._dash_page_lbl.pack(pady=(0, 6))

        self._dash_borniers_lbl = tk.Label(
            mid_col, text="",
            font=FONT_MAIN, fg=FG_OK, bg=BG_LOG,
        )
        self._dash_borniers_lbl.pack()

        # Colonne droite — MODÈLE ATTENDU
        right_col = tk.Frame(cols_outer, bg=BG_PANEL, width=220)
        right_col.pack(side='left', fill='both')
        right_col.pack_propagate(False)

        tk.Label(right_col, text="MODÈLE ATTENDU",
                 font=("Segoe UI", 8, "bold"), fg=FG_MUTED,
                 bg=BG_PANEL).pack(anchor='w', padx=10, pady=(10, 6))

        self._dash_tpl_frame = tk.Frame(right_col, bg=BG_PANEL)
        self._dash_tpl_frame.pack(fill='both', expand=True,
                                  padx=10, pady=(0, 10))

        return page

    def _dashboard_reset(self):
        """Prépare le dashboard avant une nouvelle conversion."""
        if not hasattr(self, '_dash_title_lbl'):
            return

        # En-tête
        self._dash_title_lbl.configure(text="⏳  Conversion en cours…", fg=FG_WARN)
        modes_fr = {
            "tesseract": "Tesseract", "claude": "Claude Vision",
            "docling": "Docling", "ollama": "Ollama",
            "hybrid": "Hybride", "agent": "Agent Claude",
        }
        self._dash_mode_badge.configure(
            text=f"  {modes_fr.get(self._ocr_mode.get(), self._ocr_mode.get())}  "
        )

        # Source
        src = self._word_file.get().strip()
        self._dash_src_lbl.configure(
            text=Path(src).name if src else "—"
        )
        self._dash_anim_idx = 0
        self._dash_anim_lbl.configure(text="◐", fg=COL_ACC)

        # Progression
        self._dash_pbar['value'] = 0
        self._dash_page_lbl.configure(text="En attente…", fg=FG_TEXT)
        self._dash_borniers_lbl.configure(text="")

        # Timer
        self._dash_timer_lbl.configure(text="⏱  00:00", fg=COL_ACC)
        self._dash_status_lbl.configure(text="Démarrage…")

        # Template
        self._dashboard_update_template()

        # Log
        self._dash_log_box.configure(state='normal')
        self._dash_log_box.delete('1.0', 'end')
        self._dash_log_box.configure(state='disabled')

    def _dashboard_update_template(self):
        """Affiche les colonnes du modèle sélectionné dans le dashboard."""
        if not hasattr(self, '_dash_tpl_frame'):
            return
        for w in self._dash_tpl_frame.winfo_children():
            w.destroy()

        name = self._tpl_var.get()
        tpl = self._tpl_manager.get(name)
        if not tpl:
            return

        # En-tête de tableau
        hdr_row = tk.Frame(self._dash_tpl_frame, bg=COL_ACC2)
        hdr_row.pack(fill='x', pady=(0, 2))
        for col in tpl.columns:
            tk.Label(hdr_row, text=col, font=("Segoe UI", 8, "bold"),
                     fg="white", bg=COL_ACC2, padx=6, pady=3,
                     relief='flat').pack(side='left', padx=1)

        # Lignes exemple (—)
        for _ in range(4):
            row = tk.Frame(self._dash_tpl_frame, bg=BG_PANEL)
            row.pack(fill='x', pady=1)
            for col in tpl.columns:
                tk.Label(row, text="—", font=("Segoe UI", 8),
                         fg=FG_MUTED, bg=BG_LOG, padx=6, pady=2,
                         relief='flat').pack(side='left', padx=1, fill='x',
                                            expand=True)

        tk.Label(self._dash_tpl_frame, text=f"← {name}",
                 font=("Segoe UI", 8, "italic"), fg=FG_MUTED,
                 bg=BG_PANEL).pack(anchor='w', pady=(4, 0))

    def _dashboard_done(self, result: dict):
        """Met à jour le dashboard avec les résultats de la conversion."""
        if not hasattr(self, '_dash_title_lbl'):
            return
        n_ok = result.get('tableaux', 0)
        n_tot = result.get('total', 0)
        self._dash_title_lbl.configure(
            text=f"✓  Conversion terminée — {n_ok} bornier(s) sur {n_tot}",
            fg=FG_OK,
        )
        self._dash_page_lbl.configure(
            text=f"{n_ok} / {n_tot}", fg=FG_OK,
        )
        self._dash_pbar['value'] = 100
        self._dash_status_lbl.configure(
            text=f"✓ {n_ok} bornier(s) converti(s)", fg=FG_OK,
        )
        self._dash_anim_lbl.configure(text="✓", fg=FG_OK)

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_page_params(self, parent) -> tk.Frame:
        """Page Paramètres avec onglets Documents et Modèles."""
        page = tk.Frame(parent, bg=BG_MAIN)

        tk.Label(page, text="Paramètres", font=FONT_H2,
                 fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w', padx=24, pady=(16, 8))

        notebook = ttk.Notebook(page)
        notebook.pack(fill='both', expand=True, padx=16, pady=(0, 8))

        # Onglet 1 : Documents
        tab_docs = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(tab_docs, text="Documents")
        self._build_tab_documents(tab_docs)

        # Onglet 2 : Modèles
        tab_tpl = tk.Frame(notebook, bg=BG_PANEL)
        notebook.add(tab_tpl, text="Modèles de tableau")
        self._build_tab_templates(tab_tpl)

        return page

    def _build_tab_documents(self, parent):
        """Onglet Documents : sélection des fichiers source et destination."""
        inner = tk.Frame(parent, bg=BG_PANEL, padx=20, pady=16)
        inner.pack(fill='both', expand=True)
        inner.columnconfigure(0, weight=1)

        # ── Doc. 1 : source (fichier ou dossier d'images) ────────────
        tk.Label(
            inner,
            text="Doc. 1 — Source : Word (.docx), PDF, dossier d'images,"
                 " ou journal Claude (.jsonl) :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 3))

        tk.Entry(
            inner, textvariable=self._word_file,
            font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=1, column=0, sticky='ew', padx=(0, 4), pady=(0, 8))

        btn_src = tk.Frame(inner, bg=BG_PANEL)
        btn_src.grid(row=1, column=1, pady=(0, 8))

        tk.Button(
            btn_src, text="Fichier…", font=FONT_MAIN,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=10, pady=5, cursor='hand2',
            command=self._browse_word,
        ).pack(side='left')

        _btn_img = tk.Button(
            btn_src, text="📁 Images…", font=FONT_MAIN,
            bg='#27AE60', fg='white',
            activebackground='#1E8449', activeforeground='white',
            relief='flat', padx=8, pady=5, cursor='hand2',
            command=self._browse_images_folder,
        )
        _btn_img.pack(side='left', padx=(4, 0))

        tk.Button(
            btn_src, text="📋 Log…", font=FONT_MAIN,
            bg='#8E44AD', fg='white',
            activebackground='#6C3483', activeforeground='white',
            relief='flat', padx=8, pady=5, cursor='hand2',
            command=self._browse_log_jsonl,
        ).pack(side='left', padx=(4, 0))

        # Tooltip : explique que ce bouton accepte un dossier d'images PNG/JPG
        _tt_lbl = tk.Label(
            btn_src,
            text="(dossier PNG/JPG)",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        )
        _tt_lbl.pack(side='left', padx=(4, 0))

        # ── Doc. 2 et dossier de destination ─────────────────────────
        self._make_file_row(
            inner,
            "Doc. 2 — Fichier Word avec tableaux structurés (.docx) — optionnel :",
            self._tables_word_file, self._browse_tables_word, row=1,
        )
        self._make_file_row(
            inner,
            "Dossier de destination :",
            self._output_dir, self._browse_output, row=2, is_dir=True,
        )

    def _build_tab_templates(self, parent):
        """Onglet Modèles de tableau."""
        inner = tk.Frame(parent, bg=BG_PANEL, padx=20, pady=16)
        inner.pack(fill='both', expand=True)

        # Sélection du modèle
        sel_row = tk.Frame(inner, bg=BG_PANEL)
        sel_row.pack(fill='x', pady=(0, 10))

        tk.Label(sel_row, text="Modèle de tableau :", font=FONT_BOLD,
                 fg=FG_TEXT, bg=BG_PANEL).pack(side='left')

        self._tpl_combo = ttk.Combobox(
            sel_row, textvariable=self._tpl_var,
            values=self._tpl_manager.names(),
            state='readonly', font=FONT_MAIN, width=28,
        )
        self._tpl_combo.pack(side='left', padx=(10, 0))

        # Boutons de gestion
        btn_row = tk.Frame(inner, bg=BG_PANEL)
        btn_row.pack(fill='x', pady=(0, 12))

        tk.Button(btn_row, text="+ Nouveau modèle", font=FONT_MAIN,
                  bg=COL_ACC2, fg=FG_TEXT,
                  activebackground=COL_ACC, activeforeground="white",
                  relief='flat', padx=10, pady=4, cursor='hand2',
                  command=self._new_template).pack(side='left')

        tk.Button(btn_row, text="✎ Modifier", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_TEXT,
                  activebackground=COL_ACC2, activeforeground="white",
                  relief='flat', padx=10, pady=4, cursor='hand2',
                  command=self._edit_template).pack(side='left', padx=(8, 0))

        tk.Button(btn_row, text="Supprimer", font=FONT_MAIN,
                  bg=BG_CARD, fg=FG_MUTED,
                  activebackground="#5a1010", activeforeground="white",
                  relief='flat', padx=10, pady=4, cursor='hand2',
                  command=self._delete_template).pack(side='left', padx=(8, 0))

        # Description du modèle sélectionné
        desc_frame = tk.Frame(inner, bg=BG_LOG, padx=12, pady=10)
        desc_frame.pack(fill='x')

        tk.Label(desc_frame, text="Colonnes du modèle sélectionné :",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_LOG,
                 anchor='w').pack(fill='x', pady=(0, 4))

        self._tpl_desc_lbl = tk.Label(
            desc_frame, text="",
            font=FONT_MONO, fg=FG_TEXT, bg=BG_LOG,
            anchor='w', wraplength=500, justify='left'
        )
        self._tpl_desc_lbl.pack(fill='x')

        # Mise à jour de la description quand le modèle change
        self._tpl_var.trace_add('write', self._update_tpl_desc)
        self._update_tpl_desc()

    def _update_tpl_desc(self, *_):
        """Met à jour le label de description du modèle sélectionné."""
        if not hasattr(self, '_tpl_desc_lbl'):
            return
        name = self._tpl_var.get()
        tpl = self._tpl_manager.get(name)
        if tpl:
            cols = ', '.join(tpl.columns)
            self._tpl_desc_lbl.configure(
                text=f"{len(tpl.columns)} colonne(s) : {cols}"
            )
        else:
            self._tpl_desc_lbl.configure(text="")

    def _build_page_ocr(self, parent) -> tk.Frame:
        """Page Mode OCR : choix du moteur + journal d'exécution."""
        page = tk.Frame(parent, bg=BG_MAIN)

        tk.Label(page, text="Mode OCR", font=FONT_H2,
                 fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w', padx=24, pady=(16, 8))

        # ── Zone haute : Configuration du moteur ─────────────────────
        engine_frame = tk.LabelFrame(page, text="Moteur OCR",
                                     font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                     labelanchor='nw', bd=1, relief='groove')
        engine_frame.pack(fill='x', padx=16, pady=(0, 10))

        radio_row = tk.Frame(engine_frame, bg=BG_PANEL)
        radio_row.pack(fill='x', padx=12, pady=(10, 6))

        modes = [
            ("Tesseract (local)",               "tesseract"),
            ("Claude Vision (API)",             "claude"),
            ("Docling — IBM (local IA)",        "docling"),
            ("Ollama Vision (local IA)",        "ollama"),
            ("Hybride Ollama+Claude",           "hybrid"),
            ("Agent Image Data Extractor",      "agent"),
        ]
        for label, value in modes:
            tk.Radiobutton(
                radio_row, text=label, variable=self._ocr_mode, value=value,
                font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
                selectcolor=BG_CARD, activebackground=BG_PANEL,
                activeforeground=FG_TEXT,
                command=self._on_ocr_mode_change,
            ).pack(side='left', padx=(0, 18))

        # Ligne clé API (conditionnelle)
        self._api_key_frame = tk.Frame(engine_frame, bg=BG_PANEL)
        # NB : pack/pack_forget géré par _on_ocr_mode_change

        tk.Label(self._api_key_frame, text="Clé API Anthropic :",
                 font=FONT_BOLD, fg=FG_WARN, bg=BG_PANEL).pack(side='left',
                                                               padx=(12, 0))

        self._claude_key_entry = tk.Entry(
            self._api_key_frame, textvariable=self._claude_key,
            font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            width=48, show='*',
        )
        self._claude_key_entry.pack(side='left', padx=(8, 0))

        tk.Button(
            self._api_key_frame, text="\U0001f441", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_MUTED, relief='flat', padx=4,
            cursor='hand2',
            command=self._toggle_key_visibility,
        ).pack(side='left', padx=(4, 0))

        tk.Label(
            self._api_key_frame,
            text="  Obtenir sur console.anthropic.com",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left')

        # Ligne ID de session agent (conditionnelle — visible uniquement en mode "agent")
        self._agent_session_frame = tk.Frame(engine_frame, bg=BG_PANEL)

        tk.Label(
            self._agent_session_frame, text="ID de session agent :",
            font=FONT_BOLD, fg=FG_WARN, bg=BG_PANEL,
        ).pack(side='left', padx=(12, 0))

        tk.Entry(
            self._agent_session_frame, textvariable=self._agent_session_id,
            font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            width=44,
        ).pack(side='left', padx=(8, 0))

        tk.Label(
            self._agent_session_frame,
            text="  Format : sesn_XXXX…",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left')

        # Appliquer l'état initial
        self._on_ocr_mode_change()

        # Boutons journaux — accessibles même sans conversion préalable
        log_btn_row = tk.Frame(engine_frame, bg=BG_PANEL)
        log_btn_row.pack(fill='x', padx=12, pady=(0, 10))
        tk.Button(
            log_btn_row,
            text="📋  Voir logs Claude",
            font=FONT_MAIN,
            bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=12, pady=5, cursor='hand2',
            command=self._ouvrir_observateur,
        ).pack(side='left')
        tk.Button(
            log_btn_row,
            text="🦙  Voir logs Ollama",
            font=FONT_MAIN,
            bg='#1A5276', fg=FG_TEXT,
            activebackground='#154360', activeforeground="white",
            relief='flat', padx=12, pady=5, cursor='hand2',
            command=self._ouvrir_log_ollama,
        ).pack(side='left', padx=(8, 0))
        tk.Button(
            log_btn_row,
            text="📂  Dossier logs",
            font=FONT_MAIN,
            bg=BG_CARD, fg=FG_MUTED,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=8, pady=5, cursor='hand2',
            command=self._ouvrir_dossier_logs,
        ).pack(side='left', padx=(8, 0))
        tk.Button(
            log_btn_row,
            text="🧪  Tester Ollama",
            font=FONT_MAIN,
            bg='#1E8449', fg='white',
            activebackground='#145A32', activeforeground="white",
            relief='flat', padx=10, pady=5, cursor='hand2',
            command=self._tester_ollama,
        ).pack(side='left', padx=(8, 0))
        tk.Label(
            log_btn_row,
            text="  Journaux de debug des moteurs OCR",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left', padx=(8, 0))

        # ── Zone basse : Journal d'exécution ─────────────────────────
        log_frame = tk.Frame(page, bg=BG_MAIN)
        log_frame.pack(fill='both', expand=True, padx=16, pady=(0, 8))

        tk.Label(log_frame, text="Journal d'exécution",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_MAIN,
                 anchor='w').pack(fill='x', pady=(0, 5))

        self._log_box = scrolledtext.ScrolledText(
            log_frame, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', state='disabled', height=16,
            padx=10, pady=8
        )
        self._log_box.pack(fill='both', expand=True)
        self._log_box.tag_config('ok',    foreground=FG_OK)
        self._log_box.tag_config('err',   foreground=FG_ERR)
        self._log_box.tag_config('warn',  foreground=FG_WARN)
        self._log_box.tag_config('muted', foreground=FG_MUTED)
        self._log_box.tag_config('info',  foreground=FG_TEXT)

        return page

    def _build_page_format(self, parent) -> tk.Frame:
        """Page Formater Excel : reformate un Excel existant sans relancer l'OCR."""
        page = tk.Frame(parent, bg=BG_MAIN)

        tk.Label(page, text="Formater Excel", font=FONT_H2,
                 fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w', padx=24, pady=(16, 4))
        tk.Label(
            page,
            text="Prend un fichier Excel existant et applique les règles de mise en page "
                 "(59 lignes/tableau, hauteur 12,6 pt, ajustement automatique 1 page en largeur).",
            font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN, wraplength=680, justify='left',
        ).pack(anchor='w', padx=24, pady=(0, 12))

        # ── Sélection des fichiers ────────────────────────────────────
        self._format_files_frame = tk.LabelFrame(
            page, text="Fichiers",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        self._format_files_frame.pack(fill='x', padx=16, pady=(0, 10))
        self._format_files_frame.columnconfigure(0, weight=1)

        # Fichier Excel source
        tk.Label(
            self._format_files_frame, text="Fichier Excel à reformater :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=0, column=0, columnspan=2, sticky='w', padx=12, pady=(10, 3))

        tk.Entry(
            self._format_files_frame, textvariable=self._format_excel_path,
            font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=1, column=0, sticky='ew', padx=(12, 4), pady=(0, 8))

        tk.Button(
            self._format_files_frame, text="Choisir…", font=FONT_MAIN,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=10, pady=5, cursor='hand2',
            command=self._browse_format_excel,
        ).grid(row=1, column=1, padx=(0, 12), pady=(0, 8))

        # PDF source — espacement extrait du document d'origine
        tk.Label(
            self._format_files_frame,
            text="PDF source — espacements originaux (optionnel, remplace l'Excel) :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=2, column=0, columnspan=2, sticky='w', padx=12, pady=(4, 3))

        tk.Entry(
            self._format_files_frame, textvariable=self._format_pdf_path,
            font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=3, column=0, sticky='ew', padx=(12, 4), pady=(0, 8))

        tk.Button(
            self._format_files_frame, text="Choisir…", font=FONT_MAIN,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=10, pady=5, cursor='hand2',
            command=self._browse_format_pdf,
        ).grid(row=3, column=1, padx=(0, 12), pady=(0, 8))

        tk.Label(
            self._format_files_frame,
            text="Si un PDF est fourni, il est traité par le pipeline complet "
                 "(extraction + espacement) et produit directement le fichier reformaté.",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL, anchor='w',
            wraplength=560, justify='left',
        ).grid(row=4, column=0, columnspan=2, sticky='w', padx=12, pady=(0, 8))

        # Dossier de destination
        tk.Label(
            self._format_files_frame,
            text="Dossier de destination"
                 " (vide = même dossier que le fichier source) :",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL, anchor='w',
        ).grid(row=5, column=0, columnspan=2, sticky='w', padx=12, pady=(0, 3))

        tk.Entry(
            self._format_files_frame, textvariable=self._format_output_dir,
            font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', bd=5,
        ).grid(row=6, column=0, sticky='ew', padx=(12, 4), pady=(0, 12))

        tk.Button(
            self._format_files_frame, text="Choisir…", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=10, pady=5, cursor='hand2',
            command=self._browse_format_output,
        ).grid(row=6, column=1, padx=(0, 12), pady=(0, 12))

        # ── Sélection des feuilles (affiché uniquement si > 1 feuille) ─
        self._sheets_frame = tk.LabelFrame(
            page, text="Feuilles à reformater",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        # (caché par défaut ; affiché par _update_format_sheets si le fichier
        # contient plusieurs feuilles)
        self._sheets_inner = tk.Frame(self._sheets_frame, bg=BG_PANEL)
        self._sheets_inner.pack(fill='x', padx=12, pady=8)

        # ── Paramètres de mise en forme ──────────────────────────────
        self._format_params_frame = tk.LabelFrame(
            page, text="Paramètres de mise en forme",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        params_frame = self._format_params_frame
        params_frame.pack(fill='x', padx=16, pady=(0, 10))

        inner_p = tk.Frame(params_frame, bg=BG_PANEL)
        inner_p.pack(fill='x', padx=12, pady=10)

        _params = [
            ("Hauteur de ligne (pt) :", self._format_row_height,
             "12,6 pt = 59 lignes par page A4 portrait"),
            ("Largeur colonnes (défaut) :", self._format_col_default,
             "Toutes les colonnes sauf SIGNAL"),
            ("Largeur colonne SIGNAL :", self._format_col_signal,
             "Colonne SIGNAL uniquement"),
            ("Nombre de colonnes :", self._format_n_cols,
             "0 = détection automatique  |  ex : 4 pour forcer 4 colonnes"),
            ("Lignes par tableau :", self._format_page_size,
             "0 = valeur config.py (PAGE_SIZE)  |  ex : 48 pour 48 lignes/page"),
        ]
        for ri, (lbl_txt, var, hint) in enumerate(_params):
            tk.Label(
                inner_p, text=lbl_txt, font=FONT_MAIN,
                fg=FG_TEXT, bg=BG_PANEL, anchor='w',
            ).grid(row=ri, column=0, sticky='w', padx=(0, 6), pady=2)
            tk.Entry(
                inner_p, textvariable=var,
                font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat', width=8, bd=4,
            ).grid(row=ri, column=1, sticky='w', padx=(0, 16), pady=2)
            tk.Label(
                inner_p, text=hint, font=("Segoe UI", 8),
                fg=FG_MUTED, bg=BG_PANEL, anchor='w',
            ).grid(row=ri, column=2, sticky='w', pady=2)

        # ── Marges (en cm, comme Excel français) ──────────────────
        tk.Label(
            inner_p, text="Marges (cm) :", font=FONT_BOLD,
            fg=FG_MUTED, bg=BG_PANEL,
        ).grid(row=3, column=0, columnspan=3, sticky='w', pady=(10, 4))

        margins_row = tk.Frame(inner_p, bg=BG_PANEL)
        margins_row.grid(row=4, column=0, columnspan=3, sticky='w')

        _margins = [
            ("Haut :",     self._format_margin_top),
            ("Bas :",      self._format_margin_bottom),
            ("Gauche :",   self._format_margin_left),
            ("Droite :",   self._format_margin_right),
            ("En-tête :", self._format_margin_header),
            ("Pied :",     self._format_margin_footer),
        ]
        for lbl_txt, var in _margins:
            tk.Label(
                margins_row, text=lbl_txt, font=FONT_MAIN,
                fg=FG_TEXT, bg=BG_PANEL,
            ).pack(side='left', padx=(0, 4))
            tk.Entry(
                margins_row, textvariable=var,
                font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat', width=6, bd=4,
            ).pack(side='left', padx=(0, 14))

        # ── Bouton d'action ───────────────────────────────────────────
        action_row = tk.Frame(page, bg=BG_MAIN)
        action_row.pack(fill='x', padx=16, pady=(0, 10))

        self._btn_format = tk.Button(
            action_row,
            text="📐  Reformater",
            font=FONT_BOLD,
            bg=COL_ACC, fg="white",
            activebackground=BTN_HVR, activeforeground="white",
            relief='flat', padx=20, pady=8, cursor='hand2',
            command=self._start_format,
        )
        self._btn_format.pack(side='left')

        self._btn_spacing = tk.Button(
            action_row,
            text="Espacements PDF",
            font=FONT_BOLD,
            bg=COL_ACC2, fg="white",
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=14, pady=8, cursor='hand2',
            command=self._start_spacing_update,
        )
        self._btn_spacing.pack(side='left', padx=(10, 0))

        self._format_pbar = ttk.Progressbar(
            action_row, style="Trios.Horizontal.TProgressbar",
            orient='horizontal', mode='determinate', maximum=100,
            length=200,
        )
        self._format_pbar.pack(side='left', padx=(12, 0))

        self._format_status = tk.Label(
            action_row, text="",
            font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN, anchor='w',
        )
        self._format_status.pack(side='left', padx=(10, 0))

        # ── Journal de reformatage ────────────────────────────────────
        log_frame = tk.Frame(page, bg=BG_MAIN)
        log_frame.pack(fill='both', expand=True, padx=16, pady=(0, 8))

        tk.Label(log_frame, text="Journal",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_MAIN,
                 anchor='w').pack(fill='x', pady=(0, 5))

        self._format_log_box = scrolledtext.ScrolledText(
            log_frame, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', state='disabled', height=14,
            padx=10, pady=8,
        )
        self._format_log_box.pack(fill='both', expand=True)
        self._format_log_box.tag_config('ok',    foreground=FG_OK)
        self._format_log_box.tag_config('err',   foreground=FG_ERR)
        self._format_log_box.tag_config('warn',  foreground=FG_WARN)
        self._format_log_box.tag_config('muted', foreground=FG_MUTED)
        self._format_log_box.tag_config('info',  foreground=FG_TEXT)

        return page

    # ── Actions de la page Formater ───────────────────────────────────

    def _browse_format_excel(self):
        """Ouvre un sélecteur de fichier Excel source."""
        path = filedialog.askopenfilename(
            title="Choisir le fichier Excel à reformater",
            filetypes=[("Fichiers Excel", "*.xlsx *.xlsm"), ("Tous", "*.*")],
        )
        if path:
            self._format_excel_path.set(path)
            # Pré-remplir le dossier de destination si vide
            if not self._format_output_dir.get():
                self._format_output_dir.set(str(Path(path).parent))
            self._update_format_sheets(Path(path))

    def _browse_format_pdf(self):
        """Ouvre un sélecteur de PDF source (extraction des espacements)."""
        path = filedialog.askopenfilename(
            title="Choisir le PDF source (espacements originaux)",
            filetypes=[
                ("Fichiers PDF", "*.pdf"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self._format_pdf_path.set(path)
            if not self._format_output_dir.get():
                self._format_output_dir.set(str(Path(path).parent))

    def _update_format_sheets(self, path: Path):
        """Lit les noms de feuilles du fichier et crée les cases à cocher."""
        for widget in self._sheets_inner.winfo_children():
            widget.destroy()
        self._format_sheet_vars.clear()
        self._format_sheet_col_vars.clear()
        self._format_sheet_ps_vars.clear()

        try:
            import warnings
            from openpyxl import load_workbook
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='.*wmf image.*', category=UserWarning)
                wb = load_workbook(str(path), read_only=True)
            names = wb.sheetnames
            wb.close()
        except Exception:
            try:
                wb.close()
            except Exception:
                pass
            self._sheets_frame.pack_forget()
            return

        if len(names) <= 1:
            # Une seule feuille : sélection inutile
            self._sheets_frame.pack_forget()
            return

        # Plusieurs feuilles : une ligne par feuille avec case + colonnes + lignes/page
        try:
            default_cols = int(self._format_n_cols.get().strip() or '0')
        except ValueError:
            default_cols = 0
        try:
            default_ps = int(self._format_page_size.get().strip() or '0')
        except ValueError:
            default_ps = 0

        for name in names:
            var_check = tk.BooleanVar(value=True)
            var_cols = tk.StringVar(value=str(default_cols))
            var_ps = tk.StringVar(value=str(default_ps))
            self._format_sheet_vars[name] = var_check
            self._format_sheet_col_vars[name] = var_cols
            self._format_sheet_ps_vars[name] = var_ps

            row_f = tk.Frame(self._sheets_inner, bg=BG_PANEL)
            row_f.pack(side='top', fill='x', pady=2)
            tk.Checkbutton(
                row_f, text=name,
                variable=var_check, font=FONT_MAIN,
                fg=FG_TEXT, bg=BG_PANEL,
                activebackground=BG_PANEL, activeforeground=FG_TEXT,
                selectcolor=BG_CARD,
            ).pack(side='left', padx=(0, 8))
            tk.Label(
                row_f, text="colonnes :", font=("Segoe UI", 8),
                fg=FG_MUTED, bg=BG_PANEL,
            ).pack(side='left', padx=(8, 2))
            tk.Entry(
                row_f, textvariable=var_cols,
                font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat', width=3, bd=3,
            ).pack(side='left', padx=(0, 12))
            tk.Label(
                row_f, text="lignes/page :", font=("Segoe UI", 8),
                fg=FG_MUTED, bg=BG_PANEL,
            ).pack(side='left', padx=(0, 2))
            tk.Entry(
                row_f, textvariable=var_ps,
                font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat', width=4, bd=3,
            ).pack(side='left', padx=(0, 16))

        self._sheets_frame.pack(
            fill='x', padx=16, pady=(0, 10),
            after=self._format_files_frame,
        )

    def _browse_format_output(self):
        """Ouvre un sélecteur de dossier de destination."""
        path = filedialog.askdirectory(title="Choisir le dossier de destination")
        if path:
            self._format_output_dir.set(path)

    def _fmt_log(self, msg: str):
        """Écrit une ligne dans le journal de la page Formater (thread-safe)."""
        tag = _tag_from_msg(msg)

        def _write():
            self._format_log_box.configure(state='normal')
            self._format_log_box.insert('end', msg + '\n', tag)
            self._format_log_box.configure(state='disabled')
            self._format_log_box.see('end')

        if threading.current_thread() is threading.main_thread():
            _write()
        else:
            self.after(0, _write)

    def _start_format(self):
        """Valide les entrées et lance le reformatage dans un thread."""
        src = self._format_excel_path.get().strip()

        if not src:
            messagebox.showwarning(
                "Fichier manquant",
                "Choisissez un fichier Excel à reformater.",
            )
            return

        src_path = Path(src)
        if not src_path.exists():
            messagebox.showerror(
                "Fichier introuvable",
                f"Le fichier n'existe pas :\n{src}",
            )
            return

        out_dir_str = self._format_output_dir.get().strip()
        out_dir = Path(out_dir_str) if out_dir_str else src_path.parent

        out_path = out_dir / (src_path.stem + "_formaté.xlsx")

        # Réinitialiser le journal
        self._format_log_box.configure(state='normal')
        self._format_log_box.delete('1.0', 'end')
        self._format_log_box.configure(state='disabled')

        self._btn_format.configure(state='disabled', text="En cours…")
        self._format_status.configure(text="Reformatage en cours…", fg=FG_WARN)
        self._format_pbar['value'] = 0

        def _parse_float(var, default):
            try:
                return float(var.get().replace(',', '.') or default)
            except ValueError:
                return default

        rh = _parse_float(self._format_row_height,    12.6)
        cwd = _parse_float(self._format_col_default,   19.0)
        cws = _parse_float(self._format_col_signal,    33.0)
        mt = _parse_float(self._format_margin_top,     0.9)
        mb = _parse_float(self._format_margin_bottom,  0.9)
        ml = _parse_float(self._format_margin_left,   1.75)
        mr = _parse_float(self._format_margin_right,  1.75)
        mh = _parse_float(self._format_margin_header,  0.0)
        mf = _parse_float(self._format_margin_footer,  0.0)

        def _fmt_progress(current, total):
            pct = int(current / total * 100) if total else 0

            def _update():
                self._format_pbar['value'] = pct
                self._format_status.configure(
                    text=f"Tableau {current} / {total}",
                    fg=FG_WARN,
                )
            self.after(0, _update)

        # Overrides globaux (0 = auto)
        try:
            n_cols_ov = int(self._format_n_cols.get().strip() or '0')
        except ValueError:
            n_cols_ov = 0
        try:
            ps_ov = int(self._format_page_size.get().strip() or '0')
        except ValueError:
            ps_ov = 0

        # Feuilles sélectionnées + colonnes + lignes/page par feuille
        if self._format_sheet_vars:
            selected_sheets = [
                name for name, var in self._format_sheet_vars.items()
                if var.get()
            ]
            if not selected_sheets:
                messagebox.showwarning(
                    "Aucune feuille sélectionnée",
                    "Cochez au moins une feuille à reformater.",
                )
                self._btn_format.configure(state='normal', text="📐  Reformater")
                self._format_status.configure(text="", fg=FG_MUTED)
                return
            # Colonnes par feuille
            sheet_cols_map = {}
            for name, var_cols in self._format_sheet_col_vars.items():
                try:
                    v = int(var_cols.get().strip() or '0')
                except ValueError:
                    v = 0
                if v > 0:
                    sheet_cols_map[name] = v
            if not sheet_cols_map:
                sheet_cols_map = None
            # Lignes/page par feuille
            sheet_ps_map = {}
            for name, var_ps in self._format_sheet_ps_vars.items():
                try:
                    v = int(var_ps.get().strip() or '0')
                except ValueError:
                    v = 0
                if v > 0:
                    sheet_ps_map[name] = v
            if not sheet_ps_map:
                sheet_ps_map = None
        else:
            selected_sheets = None
            sheet_cols_map = None
            sheet_ps_map = None

        def _worker():
            try:
                from generer_classeur import reformatter_excel
                n = reformatter_excel(
                    input_path=src_path,
                    output_path=out_path,
                    on_log=self._fmt_log,
                    on_progress=_fmt_progress,
                    row_height=rh,
                    col_width_default=cwd,
                    col_width_signal=cws,
                    margin_top=mt,
                    margin_bottom=mb,
                    margin_left=ml,
                    margin_right=mr,
                    margin_header=mh,
                    margin_footer=mf,
                    sheets=selected_sheets,
                    n_cols_override=n_cols_ov,
                    sheet_cols=sheet_cols_map,
                    page_size_override=ps_ov,
                    sheet_page_sizes=sheet_ps_map,
                )
                self.after(0, lambda: self._on_format_done(n, out_path))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._on_format_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Mise à jour espacements depuis PDF ────────────────────────────

    def _start_spacing_update(self):
        """Valide les entrées et lance la mise à jour des espacements."""
        excel_src = self._format_excel_path.get().strip()
        pdf_src = self._format_pdf_path.get().strip()

        if not excel_src:
            messagebox.showwarning(
                "Excel manquant",
                "Choisissez d'abord le fichier Excel à mettre à jour.",
            )
            return
        if not pdf_src:
            messagebox.showwarning(
                "PDF manquant",
                "Choisissez le PDF source pour extraire les espacements.",
            )
            return

        excel_path = Path(excel_src)
        pdf_path = Path(pdf_src)

        if not excel_path.exists():
            messagebox.showerror("Introuvable", f"Excel introuvable :\n{excel_src}")
            return
        if not pdf_path.exists():
            messagebox.showerror("Introuvable", f"PDF introuvable :\n{pdf_src}")
            return

        out_dir_str = self._format_output_dir.get().strip()
        out_dir = Path(out_dir_str) if out_dir_str else excel_path.parent
        out_path = out_dir / (excel_path.stem + "_espacé.xlsx")

        self._format_log_box.configure(state='normal')
        self._format_log_box.delete('1.0', 'end')
        self._format_log_box.configure(state='disabled')

        self._btn_spacing.configure(state='disabled', text="En cours…")
        self._btn_format.configure(state='disabled')
        self._format_status.configure(text="Extraction espacements PDF…", fg=FG_WARN)
        self._format_pbar['value'] = 0

        tpl = self._tpl_manager.get(self._tpl_var.get())

        def _fmt_progress(current, total):
            pct = int(current / total * 100) if total else 0

            def _u():
                self._format_pbar['value'] = pct
            self.after(0, _u)

        def _worker():
            try:
                from generer_classeur import appliquer_espacements_pdf
                n = appliquer_espacements_pdf(
                    excel_path=excel_path,
                    pdf_path=pdf_path,
                    output_path=out_path,
                    template=tpl,
                    on_log=self._fmt_log,
                    on_progress=_fmt_progress,
                )
                self.after(0, lambda: self._on_spacing_done(n, out_path))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self._on_spacing_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_spacing_done(self, n_updated: int, out_path: Path):
        """Callback fin de mise à jour des espacements."""
        self._btn_spacing.configure(state='normal', text="Espacements PDF")
        self._btn_format.configure(state='normal')
        self._format_pbar['value'] = 100
        self._format_status.configure(
            text=f"{n_updated} cellule(s) espacée(s) -> {out_path.name}",
            fg=FG_OK,
        )
        if messagebox.askyesno(
            "Espacements appliqués",
            f"{n_updated} cellule(s) mise(s) à jour.\n\n"
            f"Fichier : {out_path.name}\n\nOuvrir le fichier Excel ?",
        ):
            try:
                os.startfile(str(out_path))
            except Exception:
                pass

    def _on_spacing_error(self, msg: str):
        """Callback erreur mise à jour espacements."""
        self._btn_spacing.configure(state='normal', text="Espacements PDF")
        self._btn_format.configure(state='normal')
        self._format_pbar['value'] = 0
        self._format_status.configure(text="Erreur — voir le journal", fg=FG_ERR)
        self._fmt_log(f"Erreur : {msg}")
        messagebox.showerror("Erreur espacements", msg)

    def _on_format_done(self, n_tables: int, out_path: Path):
        """Callback appelé dans le thread UI quand le reformatage est terminé."""
        self._btn_format.configure(state='normal', text="📐  Reformater")
        self._format_pbar['value'] = 100
        self._format_status.configure(
            text=f"✓ {n_tables} tableau(x) reformaté(s) → {out_path.name}",
            fg=FG_OK,
        )
        if messagebox.askyesno(
            "Reformatage terminé",
            f"{n_tables} tableau(x) reformaté(s).\n\n"
            f"Fichier : {out_path.name}\n\n"
            "Ouvrir le fichier Excel ?",
        ):
            try:
                os.startfile(str(out_path))
            except Exception:
                pass

    def _on_format_error(self, msg: str):
        """Callback appelé dans le thread UI en cas d'erreur."""
        self._btn_format.configure(state='normal', text="📐  Reformater")
        self._format_pbar['value'] = 0
        self._format_status.configure(text="Erreur — voir le journal", fg=FG_ERR)
        self._fmt_log(f"✗ Erreur : {msg}")
        messagebox.showerror("Erreur de reformatage", msg)

    def _build_page_options(self, parent) -> tk.Frame:
        """Page Options : validation, minuterie, dictionnaire."""
        page = tk.Frame(parent, bg=BG_MAIN)

        tk.Label(page, text="Options", font=FONT_H2,
                 fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w', padx=24, pady=(16, 8))

        # Section Validation
        lf_valid = tk.LabelFrame(page, text="Validation",
                                 font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                 labelanchor='nw', bd=1, relief='groove')
        lf_valid.pack(fill='x', padx=16, pady=(0, 12))

        tk.Radiobutton(
            lf_valid,
            text="Automatique — conversion sans interruption",
            variable=self._validation_interactive, value=False,
            font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            activeforeground=FG_TEXT,
        ).pack(anchor='w', padx=12, pady=(10, 4))

        tk.Radiobutton(
            lf_valid,
            text="Manuelle page par page — vérification à chaque page PDF",
            variable=self._validation_interactive, value=True,
            font=FONT_MAIN, fg=FG_TEXT, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            activeforeground=FG_TEXT,
        ).pack(anchor='w', padx=12, pady=(0, 10))

        # Section Minuterie
        lf_timer = tk.LabelFrame(page, text="Minuterie de conversion",
                                 font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                 labelanchor='nw', bd=1, relief='groove')
        lf_timer.pack(fill='x', padx=16, pady=(0, 12))

        timer_row = tk.Frame(lf_timer, bg=BG_PANEL)
        timer_row.pack(fill='x', padx=12, pady=10)

        tk.Label(timer_row, text="Temps de traitement :",
                 font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL).pack(side='left')

        self._timer_label = tk.Label(timer_row, text="--:--",
                                     font=("Consolas", 14, "bold"),
                                     fg=COL_ACC, bg=BG_PANEL)
        self._timer_label.pack(side='left', padx=(12, 0))

        # Section Dictionnaire OCR
        lf_dico = tk.LabelFrame(page, text="Dictionnaire OCR",
                                font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                                labelanchor='nw', bd=1, relief='groove')
        lf_dico.pack(fill='x', padx=16)

        tk.Label(
            lf_dico,
            text="Le dictionnaire mémorise les valeurs validées"
                 " pour corriger les futures erreurs OCR.",
            font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
            anchor='w', wraplength=600, justify='left'
        ).pack(fill='x', padx=12, pady=(10, 8))

        btns_dico = tk.Frame(lf_dico, bg=BG_PANEL)
        btns_dico.pack(anchor='w', padx=12, pady=(0, 12))

        tk.Button(
            btns_dico, text="Enrichir depuis Excel", font=FONT_BOLD,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=14, pady=6, cursor='hand2',
            command=self._enrich_dictionary,
        ).pack(side='left', padx=(0, 8))

        tk.Button(
            btns_dico, text="Consulter / modifier", font=FONT_BOLD,
            bg='#5D6D7E', fg='white',
            activebackground='#4A5568', activeforeground="white",
            relief='flat', padx=14, pady=6, cursor='hand2',
            command=self._ouvrir_dictionnaire,
        ).pack(side='left')

        return page

    def _build_page_aide(self, parent) -> tk.Frame:
        """Page Aide : guide rapide en lecture seule."""
        page = tk.Frame(parent, bg=BG_MAIN)

        tk.Label(page, text="Aide", font=FONT_H2,
                 fg=FG_TEXT, bg=BG_MAIN).pack(anchor='w', padx=24, pady=(16, 8))

        aide_box = scrolledtext.ScrolledText(
            page, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', state='normal', padx=16, pady=12
        )
        aide_box.pack(fill='both', expand=True, padx=16, pady=(0, 8))

        contenu = (
            "GUIDE RAPIDE — TriosSeconverter\n"
            "================================\n\n"
            "1. PRÉPARER VOS FICHIERS\n"
            "   → Placez votre PDF ou fichier Word dans un dossier accessible.\n"
            "   → Si vous avez un second fichier Word avec des tableaux"
            " structurés (Doc.2), préparez-le aussi.\n\n"
            "2. PARAMÈTRES\n"
            "   → Onglet \"Documents\" : sélectionnez vos fichiers et le dossier de sortie.\n"
            "   → Onglet \"Modèles\" : choisissez ou créez un modèle de tableau"
            " correspondant à vos documents.\n\n"
            "3. MODE OCR\n"
            "   → Tesseract : reconnaissance locale, rapide, sans internet.\n"
            "   → Claude Vision : IA Anthropic, meilleure précision, nécessite une clé API.\n"
            "   → Docling IBM : IA locale, installation lourde, pas de coût API.\n\n"
            "4. LANCER LA CONVERSION\n"
            "   → Cliquez sur \"▶ Lancer la conversion\" en bas de l'écran.\n"
            "   → Le journal d'exécution s'affiche dans Mode OCR.\n\n"
            "5. RÉSULTATS\n"
            "   → Cliquez sur \"Excel\" pour ouvrir le fichier généré.\n"
            "   → Cliquez sur \"Dossier\" pour ouvrir le dossier de sortie.\n"
            "   → Utilisez \"Audit\" pour analyser la qualité de l'extraction.\n\n"
            "RACCOURCIS\n"
            "   Ctrl+S    Lancer la conversion\n"
            "   Ctrl+O    Ouvrir le fichier source\n\n"
            "SUPPORT\n"
            "   En cas de problème, consultez le fichier CLAUDE.md ou\n"
            "   contactez l'équipe via le système de tickets.\n"
        )
        aide_box.insert('end', contenu)
        aide_box.configure(state='disabled')

        return page

    # ── Helpers de construction ───────────────────────────────────────

    def _make_file_row(self, parent, label_text, var, cmd, row, is_dir=False):
        tk.Label(parent, text=label_text, font=FONT_BOLD,
                 fg=FG_TEXT, bg=BG_PANEL, anchor='w'
                 ).grid(row=row * 2, column=0, columnspan=2,
                        sticky='w', pady=(8 if row else 0, 3))

        entry = tk.Entry(parent, textvariable=var, font=FONT_MAIN,
                         bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                         relief='flat', bd=5)
        entry.grid(row=row * 2 + 1, column=0, sticky='ew',
                   padx=(0, 10), pady=(0, 10 if row else 8))

        btn = tk.Button(parent, text="Parcourir…", font=FONT_MAIN,
                        bg=COL_ACC2, fg=FG_TEXT,
                        activebackground=COL_ACC, activeforeground="white",
                        relief='flat', padx=12, pady=5,
                        cursor='hand2', command=cmd)
        btn.grid(row=row * 2 + 1, column=1, pady=(0, 10 if row else 8))
        parent.columnconfigure(0, weight=1)

    # ── Gestion du mode OCR ───────────────────────────────────────────

    def _on_ocr_mode_change(self):
        """Affiche/masque clé API et ID session dans la page OCR ET dans le stepper."""
        mode = self._ocr_mode.get()
        needs_api = mode in ('claude', 'hybrid', 'agent')
        needs_agent = mode == 'agent'

        # Page OCR (onglet développeur — peut ne pas exister encore au build)
        if hasattr(self, '_api_key_frame'):
            if needs_api:
                self._api_key_frame.pack(fill='x', padx=0, pady=(0, 4))
            else:
                self._api_key_frame.pack_forget()
        if hasattr(self, '_agent_session_frame'):
            if needs_agent:
                self._agent_session_frame.pack(fill='x', padx=0, pady=(0, 8))
            else:
                self._agent_session_frame.pack_forget()

        # Stepper step 2 (même logique sur les frames du stepper)
        if hasattr(self, '_stepper_api_key_frame'):
            if needs_api:
                self._stepper_api_key_frame.pack(
                    fill='x', padx=12, pady=(0, 4))
            else:
                self._stepper_api_key_frame.pack_forget()
        if hasattr(self, '_stepper_agent_frame'):
            if needs_agent:
                self._stepper_agent_frame.pack(
                    fill='x', padx=12, pady=(0, 8))
            else:
                self._stepper_agent_frame.pack_forget()

    def _toggle_key_visibility(self):
        """Alterne l'affichage masqué/visible de la clé API."""
        entry = self._claude_key_entry
        entry.config(show='' if entry['show'] == '*' else '*')

    # ── Gestion des modèles de tableau ────────────────────────────────

    def _refresh_template_combo(self):
        names = self._tpl_manager.names()
        self._tpl_combo['values'] = names
        if self._tpl_var.get() not in names:
            self._tpl_var.set(names[0] if names else '')

    def _new_template(self):
        tpl = TableTemplate(name="Nouveau modèle", columns=["COL1", "COL2"])
        dlg = TemplateEditorDialog(self, tpl, self._tpl_manager)
        self.wait_window(dlg)
        self._refresh_template_combo()
        if dlg._saved and dlg._saved_name in self._tpl_manager.names():
            self._tpl_var.set(dlg._saved_name)

    def _edit_template(self):
        name = self._tpl_var.get()
        tpl = self._tpl_manager.get(name)
        import copy
        dlg = TemplateEditorDialog(self, copy.deepcopy(tpl), self._tpl_manager)
        self.wait_window(dlg)
        self._refresh_template_combo()
        target = dlg._saved_name if (dlg._saved and dlg._saved_name) else name
        if target in self._tpl_manager.names():
            self._tpl_var.set(target)

    def _delete_template(self):
        name = self._tpl_var.get()
        protected = ("Bornier standard", "Répartiteur", "REPARTITEUR")
        if name in protected:
            messagebox.showinfo("Modèle protégé",
                                f"Le modèle '{name}' ne peut pas être supprimé.")
            return
        if messagebox.askyesno("Supprimer le modèle",
                               f"Supprimer « {name} » ?"):
            self._tpl_manager.delete(name)
            new_names = self._tpl_manager.names()
            self._tpl_combo['values'] = new_names
            self._tpl_var.set(new_names[0] if new_names else '')
            self._tpl_combo.update_idletasks()

    # ── Actions fichiers ──────────────────────────────────────────────

    def _browse_word(self):
        path = filedialog.askopenfilename(
            title="Sélectionner le fichier source",
            filetypes=[
                ("Fichiers supportés", "*.docx *.pdf *.jsonl"),
                ("Documents Word", "*.docx"),
                ("Fichiers PDF", "*.pdf"),
                ("Journaux Claude", "*.jsonl"),
                ("Tous les fichiers", "*.*"),
            ]
        )
        if path:
            self._word_file.set(path)

    def _browse_log_jsonl(self):
        """Sélectionne un journal Claude/Hybrid (.jsonl) pour régénérer l'Excel sans API."""
        path = filedialog.askopenfilename(
            title="Sélectionner un journal Claude/Hybrid pour régénérer l'Excel",
            filetypes=[
                ("Journaux Claude / Hybrid", "*.jsonl"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self._word_file.set(path)

    def _browse_images_folder(self):
        path = filedialog.askdirectory(
            title="Sélectionner le dossier contenant les images de borniers"
        )
        if path:
            self._word_file.set(path)

    def _browse_tables_word(self):
        path = filedialog.askopenfilename(
            title="Sélectionner le fichier Word avec tableaux structurés",
            filetypes=[("Documents Word", "*.docx"), ("Tous les fichiers", "*.*")]
        )
        if path:
            self._tables_word_file.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(
            title="Sélectionner le dossier de destination"
        )
        if path:
            self._output_dir.set(path)

    # ── Lancement de la conversion ────────────────────────────────────

    def _start(self):
        word = self._word_file.get().strip()
        outdir = self._output_dir.get().strip()

        if not word:
            messagebox.showwarning("Champ manquant",
                                   "Veuillez sélectionner le fichier source (Word ou PDF).")
            return
        word_path = Path(word)
        if not word_path.exists():
            messagebox.showerror("Introuvable",
                                 f"Le chemin suivant est introuvable :\n{word}")
            return
        if word_path.is_file() and word_path.suffix.lower() not in ('.docx', '.pdf', '.jsonl'):
            messagebox.showerror(
                "Format non supporté",
                "Formats acceptés pour Doc. 1 :\n"
                "  • .docx  (Word avec images)\n"
                "  • .pdf\n"
                "  • .jsonl (journal Claude à rejouer)\n"
                "  • Dossier d'images (bouton 📁 Images…)",
            )
            return
        if not outdir:
            messagebox.showwarning("Champ manquant",
                                   "Veuillez sélectionner le dossier de destination.")
            return

        # Réinitialiser l'état
        self._result = None
        self.configure(cursor="watch")
        self._btn_start.configure_state('disabled')
        self._btn_start.set_text("⏳  Conversion en cours…")
        for b in self._result_btns:
            b.configure_state('disabled')

        tpl = self._tpl_manager.get(self._tpl_var.get())
        tables_word = self._tables_word_file.get().strip() or None

        # Appliquer le mode OCR sélectionné
        from config import Config
        ocr_mode = self._ocr_mode.get()
        Config.OCR_MODE = ocr_mode
        if ocr_mode in ('claude', 'hybrid', 'agent'):
            api_key = self._claude_key.get().strip()
            if not api_key:
                messagebox.showwarning(
                    "Clé API manquante",
                    "Le mode Claude Vision (ou Hybride ou Agent) nécessite"
                    " une clé API Anthropic.\n"
                    "Renseignez-la dans le champ 'Clé API Anthropic'"
                    " (page Mode OCR).",
                )
                self._btn_start.configure_state('normal')
                self._btn_start.set_text("▶  Lancer la conversion")
                self.configure(cursor="")
                return
            Config.CLAUDE_API_KEY = api_key
        if ocr_mode == 'agent':
            session_id = self._agent_session_id.get().strip()
            if not session_id:
                messagebox.showwarning(
                    "ID de session manquant",
                    "Le mode Agent nécessite un ID de session Managed Agents.\n"
                    "Renseignez-le dans le champ 'ID de session agent' (page Mode OCR).\n"
                    "Format : sesn_XXXXXXXXXXXXXXXXXXXX",
                )
                self._btn_start.configure_state('normal')
                self._btn_start.set_text("▶  Lancer la conversion")
                self.configure(cursor="")
                return
            Config.CLAUDE_AGENT_SESSION_ID = session_id

        self._log_clear()
        self._set_progress(0.0, "Démarrage de la conversion…")
        self._log("═" * 54, 'muted')
        self._log("  TriosSeconverter  —  Conversion démarrée", 'ok')
        wp = Path(word)
        if wp.is_dir():
            mode = "Images"
        elif word.lower().endswith('.pdf'):
            mode = "PDF"
        elif word.lower().endswith('.jsonl'):
            mode = "Log Claude"
        else:
            mode = "Word"
        self._log(f"  Doc.1 ({mode})  : {word}", 'muted')
        if tables_word:
            self._log(f"  Doc.2 (tableaux): {tables_word}", 'muted')
        self._log(f"  Sortie  : {outdir}", 'muted')
        self._log(f"  Modèle  : {self._tpl_var.get()}", 'muted')
        _om = getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')
        _cm = getattr(Config, 'CLAUDE_OCR_MODEL', 'haiku')
        _sid = getattr(Config, 'CLAUDE_AGENT_SESSION_ID', '')
        ocr_labels = {
            'tesseract': 'Tesseract',
            'claude': 'Claude Vision (API)',
            'docling': 'Docling IBM',
            'ollama': f"Ollama Vision local ({_om})",
            'hybrid': f"Hybride Ollama+Claude ({_om} + {_cm})",
            'agent': f"Agent Image Data Extractor (…{_sid[-8:] if _sid else '?'})",
        }
        self._log(f"  Moteur OCR  : {ocr_labels.get(ocr_mode, ocr_mode)}", 'muted')
        self._log("═" * 54, 'muted')

        # Préparer et afficher le dashboard de conversion
        self._dashboard_reset()
        self._show_page('dashboard')

        # Timer de conversion
        self._start_timer()

        # Callback de validation interactive
        self._validation_auto_skip = False   # réinitialiser à chaque conversion
        validation_cb = None
        if self._validation_interactive.get():
            def _on_validation(page_done, page_total, result, image_path):
                if self._validation_auto_skip:
                    return None

                # Un event LOCAL par appel élimine toute race condition entre
                # deux validations consécutives sur la même instance partagée.
                local_event = threading.Event()
                local_result_box = [None]

                def _callback(comment, is_problem, retry=False, auto=False):
                    if retry:
                        local_result_box[0] = ('retry', comment or '')
                    elif auto:
                        self._validation_auto_skip = True
                        local_result_box[0] = comment or None
                    else:
                        if comment and outdir:
                            try:
                                rows_count = sum(
                                    1 for r in result.get('rows', [])
                                    if r.get('type') == 'data'
                                )
                                entry = {
                                    'ts':       datetime.datetime.now().isoformat(
                                                    timespec='seconds'),
                                    'page':     page_done,
                                    'template': result.get('template', ''),
                                    'rows':     rows_count,
                                    'comment':  comment,
                                    'image':    (Path(image_path).name
                                                 if image_path else ''),
                                    'attempt':  result.get('_attempt', 1),
                                }
                                with open(
                                    Path(outdir) / 'feedback_log.jsonl',
                                    'a', encoding='utf-8'
                                ) as fh:
                                    fh.write(
                                        json.dumps(entry, ensure_ascii=False) + '\n'
                                    )
                            except Exception:
                                pass
                        local_result_box[0] = comment if comment else None
                    local_event.set()

                self.after(0, lambda: self._montrer_validation_dialog(
                    page_done, page_total, result, image_path, _callback
                ))
                # timeout=300 s : si la fenêtre est fermée brutalement, le
                # thread de travail ne reste pas bloqué indéfiniment.
                local_event.wait(timeout=300)
                if self._validation_auto_skip and local_result_box[0] is None:
                    return None
                return local_result_box[0]
            validation_cb = _on_validation

        def _worker():
            try:
                conv = Converter(
                    word_file=Path(word),
                    output_dir=Path(outdir),
                    template=tpl,
                    tables_word_file=Path(tables_word) if tables_word else None,
                    on_progress=lambda p, m: self._queue.put(('progress', p, m)),
                    on_log=lambda m:         self._queue.put(('log', m, _tag_from_msg(m))),
                    on_validation=validation_cb,
                )
                result = conv.run()
                self._queue.put(('done', result))
            except Exception as exc:
                self._queue.put(('error', str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Timer ─────────────────────────────────────────────────────────

    def _start_timer(self):
        import time
        self._conv_start_time = time.time()
        self._tick_timer()

    def _tick_timer(self):
        if self._conv_start_time is None:
            return
        import time
        elapsed = int(time.time() - self._conv_start_time)
        m, s = divmod(elapsed, 60)
        if hasattr(self, '_timer_label'):
            self._timer_label.configure(text=f"{m:02d}:{s:02d}")
        # Mettre à jour le timer du dashboard + avancer l'animation spinner
        if hasattr(self, '_dash_timer_lbl'):
            self._dash_timer_lbl.configure(text=f"⏱  {m:02d}:{s:02d}")
        if hasattr(self, '_dash_anim_lbl') and self._conv_start_time is not None:
            _SPIN = ("◐", "◓", "◑", "◒")
            self._dash_anim_idx = (self._dash_anim_idx + 1) % len(_SPIN)
            self._dash_anim_lbl.configure(text=_SPIN[self._dash_anim_idx])
        self._timer_id = self.after(1000, self._tick_timer)

    def _stop_timer(self):
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._conv_start_time = None

    # ── Résultats ─────────────────────────────────────────────────────

    def _open_excel(self):
        if self._result:
            try:
                os.startfile(str(self._result['excel']))
            except Exception as e:
                messagebox.showerror("Impossible d'ouvrir", str(e))

    def _open_folder(self):
        if self._result:
            try:
                os.startfile(str(self._result['excel'].parent))
            except Exception as e:
                messagebox.showerror("Impossible d'ouvrir", str(e))

    # ── Mise à jour UI depuis la queue ────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == 'progress':
                    self._set_progress(item[1], item[2])
                elif kind == 'log':
                    self._log(item[1], item[2])
                elif kind == 'done':
                    self._on_done(item[1])
                elif kind == 'error':
                    self._on_error(item[1])
                elif kind == 'audit_done':
                    self._on_audit_done(item[1])
        except Exception:
            pass
        self.after(80, self._poll_queue)

    def _set_progress(self, pct: float, msg: str):
        self._pbar['value'] = pct * 100
        self._status_lbl.configure(text=msg)
        # Mettre à jour le dashboard
        if hasattr(self, '_dash_pbar'):
            self._dash_pbar['value'] = pct * 100
            self._dash_page_lbl.configure(text=msg if msg else "…")
            self._dash_status_lbl.configure(text=msg)

    def _log(self, msg: str, tag: str = 'info'):
        self._log_box.configure(state='normal')
        self._log_box.insert('end', msg + '\n', tag)
        self._log_box.see('end')
        self._log_box.configure(state='disabled')
        # Miroir dans le dashboard
        if hasattr(self, '_dash_log_box'):
            self._dash_log_box.configure(state='normal')
            self._dash_log_box.insert('end', msg + '\n', tag)
            self._dash_log_box.see('end')
            self._dash_log_box.configure(state='disabled')
            # Mettre à jour le compteur de borniers sur les lignes de succès
            if tag == 'ok' and 'bornier' in msg.lower():
                self._dash_borniers_lbl.configure(text=msg.strip())

    def _log_clear(self):
        self._log_box.configure(state='normal')
        self._log_box.delete('1.0', 'end')
        self._log_box.configure(state='disabled')

    def _on_done(self, result: dict):
        self._result = result
        self._stop_timer()
        self.configure(cursor="")
        self._log("═" * 54, 'ok')
        self._log(f"  ✓ {result['tableaux']}/{result['total']} bornier(s) converti(s)", 'ok')
        p = result.get('excel')
        if p and Path(p).exists():
            size_ko = Path(p).stat().st_size // 1024
            self._log(f"  ✓ {Path(p).name}  ({size_ko} Ko)", 'ok')
        log_p = result.get('log')
        if log_p and Path(log_p).exists():
            size_log = Path(log_p).stat().st_size // 1024
            self._log("─" * 54, 'muted')
            self._log(
                f"  📋 Journal Claude : {Path(log_p).name}  ({size_log} Ko)",
                'ok',
            )
            self._log(
                "     → Cliquez «📋 Log…» pour régénérer l'Excel sans appel API.",
                'muted',
            )

        log_ol = result.get('log_ollama')
        if log_ol:
            log_ol = Path(log_ol)
            self._log("─" * 54, 'muted')
            if log_ol.exists():
                size_ol = log_ol.stat().st_size // 1024
                # Compter les entrées de page (type != 'session')
                n_pages = 0
                n_erreurs = 0
                try:
                    with open(log_ol, encoding='utf-8') as _f:
                        for _l in _f:
                            try:
                                _e = json.loads(_l.strip())
                                if _e.get('type') == 'page':
                                    n_pages += 1
                                    if not _e.get('success'):
                                        n_erreurs += 1
                            except Exception:
                                pass
                except Exception:
                    pass
                self._log(
                    f"  🦙 Journal Ollama : {log_ol.name}  "
                    f"({size_ol} Ko — {n_pages} pages",
                    'ok',
                )
                if n_erreurs:
                    self._log(
                        f"     ⚠ {n_erreurs} page(s) en erreur — "
                        "consultez «🦙 Voir logs Ollama» pour le détail.",
                        'warn',
                    )
                self._log(f"     📁 {log_ol.parent}", 'muted')
                self._log(
                    "     → Cliquez «🦙 Voir logs Ollama» pour inspecter.",
                    'muted',
                )
            else:
                self._log(
                    f"  ⚠ Journal Ollama attendu mais absent : {log_ol.name}",
                    'warn',
                )
                self._log(
                    "     Ollama n'a peut-être répondu à aucune page.",
                    'warn',
                )

        self._log("═" * 54, 'ok')
        self._set_progress(1.0, f"Terminé — {result['tableaux']} bornier(s) converti(s).")
        self._btn_start.configure_state('normal')
        self._btn_start.set_text("▶  Lancer la conversion")
        for b in self._result_btns:
            b.configure_state('normal')
        self._update_ctx_btn_states()
        self._dashboard_done(result)

    def _on_error(self, msg: str):
        self._stop_timer()
        self.configure(cursor="")
        self._log(f"\n  ✗ ERREUR : {msg}", 'err')
        self._set_progress(0.0, "Échec — consultez le journal.")
        self._btn_start.configure_state('normal')
        self._btn_start.set_text("▶  Lancer la conversion")
        # Afficher l'erreur dans le dashboard
        if hasattr(self, '_dash_title_lbl'):
            self._dash_title_lbl.configure(text="✗  Échec de la conversion", fg=FG_ERR)
            self._dash_anim_lbl.configure(text="✗", fg=FG_ERR)
        messagebox.showerror("Erreur de conversion", msg)

    def _on_audit_done(self, result: dict):
        self.configure(cursor="")
        self._btn_audit.configure_state('normal')
        self._btn_audit.set_text("  Audit  ")
        if not result.get('ok'):
            messagebox.showerror("Erreur d'audit", result.get('erreur', 'Erreur inconnue'))
            return
        AuditDialog(self, result)

    def _enrich_dictionary(self):
        """
        Importe un classeur Excel vers le dictionnaire EN ATTENTE.
        Les valeurs ne sont actives qu'après validation dans 'Dictionnaire OCR'.
        """
        path = filedialog.askopenfilename(
            title="Sélectionner le classeur Excel à importer",
            filetypes=[("Classeur Excel", "*.xlsx *.xls"), ("Tous les fichiers", "*.*")],
        )
        if not path:
            return
        try:
            from data_dictionary import get_pending_dictionary
            pending = get_pending_dictionary()
            counts = pending.update_from_excel(Path(path))
            nouveaux = sum(counts.values())
            if nouveaux > 0:
                messagebox.showinfo(
                    "Import réussi",
                    f"✓ {nouveaux} valeur(s) ajoutée(s) au dictionnaire EN ATTENTE.\n\n"
                    f"Ouvrez 'Dictionnaire OCR' → onglet 'À valider'\n"
                    f"pour reviewer et valider vers le dictionnaire final.",
                )
            else:
                messagebox.showinfo(
                    "Aucune nouveauté",
                    "Aucune nouvelle valeur trouvée dans ce fichier\n"
                    "(déjà présentes ou invalides).",
                )
        except Exception as exc:
            messagebox.showerror("Erreur d'import", f"Impossible de lire le fichier :\n{exc}")

    def _ouvrir_dictionnaire(self):
        """Ouvre le visionneur / éditeur du dictionnaire OCR."""
        DictionnaireDialog(self)

    def _ouvrir_observateur(self, log_path: Path = None):
        """Ouvre le visualiseur des données API brutes vs traitées.

        Si log_path est fourni, l'ouvre directement.
        Sinon, cherche le log de la dernière conversion ou demande à l'utilisateur.
        """
        if log_path is None:
            # Essayer de trouver le log de la dernière conversion
            if self._result:
                excel_path = self._result.get('excel')
                if excel_path:
                    candidate = Path(excel_path).parent / 'claude_api_log.jsonl'
                    if candidate.exists():
                        log_path = candidate

            # Si toujours rien, demander à l'utilisateur
            if log_path is None:
                path = filedialog.askopenfilename(
                    title="Sélectionner un journal API Claude",
                    filetypes=[
                        ("Journaux Claude", "*.jsonl"),
                        ("Tous les fichiers", "*.*"),
                    ],
                )
                if not path:
                    return
                log_path = Path(path)

        if not log_path.exists():
            messagebox.showerror("Fichier introuvable",
                                 f"Journal introuvable :\n{log_path}")
            return
        ObservateurAPIDialog(self, log_path)

    def _ouvrir_log_ollama(self):
        """Ouvre le journal Ollama dans un visualiseur texte simplifié."""
        log_path = None

        # 1. Résultat de la dernière conversion
        if self._result:
            p = self._result.get('log_ollama')
            if p and Path(p).exists():
                log_path = Path(p)

        # 2. Chercher dans le dossier de sortie courant
        if log_path is None:
            outdir = self._output_dir.get().strip()
            if outdir:
                for f in Path(outdir).glob('*_ollama.jsonl'):
                    log_path = f
                    break

        # 3. Demander à l'utilisateur
        if log_path is None:
            path = filedialog.askopenfilename(
                title="Sélectionner un journal Ollama",
                filetypes=[
                    ("Journaux Ollama", "*_ollama.jsonl"),
                    ("Journaux JSONL", "*.jsonl"),
                    ("Tous les fichiers", "*.*"),
                ],
            )
            if not path:
                return
            log_path = Path(path)

        if not log_path.exists():
            messagebox.showerror("Fichier introuvable",
                                 f"Journal Ollama introuvable :\n{log_path}")
            return

        # Afficher dans une fenêtre texte
        OllamaLogDialog(self, log_path)

    def _ouvrir_dossier_logs(self):
        """Ouvre dans l'Explorateur le dossier de sortie contenant les logs."""
        # Priorité : dossier du dernier résultat
        folder = None
        if self._result:
            for key in ('log_ollama', 'log', 'excel'):
                p = self._result.get(key)
                if p and Path(p).exists():
                    folder = Path(p).parent
                    break

        # Sinon : dossier de sortie configuré
        if folder is None:
            outdir = self._output_dir.get().strip()
            if outdir and Path(outdir).exists():
                folder = Path(outdir)

        if folder is None:
            messagebox.showinfo(
                "Dossier introuvable",
                "Aucun dossier de sortie connu pour l'instant.\n"
                "Lancez une conversion d'abord.",
            )
            return

        try:
            os.startfile(str(folder))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le dossier :\n{e}")

    def _tester_ollama(self):
        """Ouvre le dialogue de diagnostic Ollama."""
        OllamaTestDialog(self)

    def _montrer_validation_dialog(
        self, page_done: int, page_total: int, result: dict, image_path: str,
        on_validated_callback=None,
    ):
        """Crée le dialog de validation dans le thread UI (appelé via after(0,...))."""
        if on_validated_callback is None:
            return
        can_retry = bool(image_path)
        ValidationPageDialog(
            self, page_done, page_total, result, image_path,
            on_validated_callback, can_retry=can_retry,
        )

    def _lancer_audit(self):
        """Lance l'audit du dernier classeur Excel généré."""
        excel_path = self._result.get('excel') if self._result else None
        if not excel_path or not Path(excel_path).exists():
            messagebox.showwarning(
                "Classeur introuvable",
                "Aucun classeur Excel disponible.\n"
                "Lancez d'abord une conversion pour générer le fichier.",
            )
            return

        api_key = ""
        if getattr(self, '_ocr_mode', None) and self._ocr_mode.get() == 'claude':
            api_key = self._claude_key.get().strip()
        if not api_key:
            from config import Config
            api_key = getattr(Config, 'CLAUDE_API_KEY', '')

        self._btn_audit.configure_state('disabled')
        self._btn_audit.set_text("⏳  Audit…")
        self.configure(cursor="watch")

        def _worker():
            from audit_claude import auditer
            result = auditer(Path(excel_path), api_key=api_key)
            self._queue.put(('audit_done', result))

        threading.Thread(target=_worker, daemon=True).start()


# ── Fenêtre de validation page par page ──────────────────────────────

class ValidationPageDialog(tk.Toplevel):
    """
    Dialog modal de validation manuelle après extraction d'une page.

    Zone gauche  : données extraites (lignes et colonnes du tableau)
    Zone droite haute : métadonnées (PAGE, BORNIER, PET, etc.)
    Zone droite basse : champ commentaire + radio OK / Problème détecté
    Bouton "Valider et continuer" → appelle _on_validated(comment, is_problem)

    Le dialog est non-bloquant côté Tkinter (grab_set sans wait_window) :
    c'est threading.Event dans l'appelant qui bloque le thread travail.
    """

    def __init__(
        self, parent,
        page_done: int, page_total: int,
        result: dict, image_path: str,
        on_validated,
        can_retry: bool = True,
    ):
        super().__init__(parent)
        self._result = result
        self._image_path = image_path
        self._on_validated = on_validated
        self._can_retry = can_retry

        attempt = result.get('_attempt', 1)
        attempt_txt = f" — Tentative {attempt}" if attempt > 1 else ""
        self.title(f"Page {page_done}/{page_total}{attempt_txt} — Validation")
        self.geometry("1160x680")
        self.minsize(900, 520)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()

        # Fermer via la croix = approuver sans commentaire
        self.protocol("WM_DELETE_WINDOW", self._valider_accepter)

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._build(page_done, page_total, attempt)

    def _build(self, page_done: int, page_total: int, attempt: int = 1):
        # En-tête
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        meta = self._result.get('metadata', {})
        bornier = meta.get('BORNIER', '—')
        rows_count = sum(
            1 for r in self._result.get('rows', []) if r.get('type') == 'data'
        )
        attempt_txt = f"  —  Tentative {attempt}" if attempt > 1 else ""
        retry_err = self._result.get('_retry_error', '')
        hdr_fg = FG_ERR if retry_err else FG_TEXT
        hdr_text = (
            f"Validation page {page_done}/{page_total}"
            f"  —  Bornier : {bornier}"
            f"  —  {rows_count} lignes{attempt_txt}"
        )
        tk.Label(
            hdr, text=hdr_text,
            font=FONT_H2, fg=hdr_fg, bg=BG_CARD,
        ).pack(side='left', padx=16, pady=10)
        if retry_err:
            tk.Label(
                hdr,
                text=f"⚠ Tentative précédente échouée : {retry_err[:80]}",
                font=("Segoe UI", 8), fg=FG_ERR, bg=BG_CARD,
            ).pack(side='left', padx=(0, 16))

        # Corps principal — deux colonnes
        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=10, pady=8)

        # Colonne gauche : aperçu image + données extraites
        left = tk.Frame(body, bg=BG_PANEL, width=460)
        left.pack(side='left', fill='both', padx=(0, 6))
        left.pack_propagate(False)

        # ── Aperçu image source ──────────────────────────────────────
        if self._image_path and Path(self._image_path).exists():
            try:
                from PIL import Image, ImageTk
                img_pil = Image.open(self._image_path)
                # Redimensionner pour tenir dans 440×180 px
                img_pil.thumbnail((440, 180), Image.LANCZOS)
                self._preview_img = ImageTk.PhotoImage(img_pil)
                img_frame = tk.Frame(left, bg='#000000', height=184)
                img_frame.pack(fill='x', padx=4, pady=(4, 0))
                img_frame.pack_propagate(False)
                tk.Label(
                    img_frame, image=self._preview_img, bg='#000000',
                ).pack(expand=True)
            except Exception:
                self._preview_img = None
        else:
            self._preview_img = None
            tk.Label(
                left,
                text="(aperçu non disponible)",
                font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
            ).pack(padx=8, pady=(6, 0))

        tk.Label(
            left, text="Données extraites",
            font=FONT_BOLD, fg=COL_ACC, bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(4, 4))

        data_box = scrolledtext.ScrolledText(
            left, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='none', state='disabled', padx=8, pady=6,
        )
        data_box.pack(fill='both', expand=True, padx=4, pady=(0, 6))

        # Tags de couleur : orange = confiance < 60 %, rouge = < 35 %
        data_box.tag_configure('conf_warn',  background='#E67E22', foreground='white')
        data_box.tag_configure('conf_bad',   background='#C0392B', foreground='white')
        data_box.tag_configure('hdr',        foreground=COL_ACC, font=FONT_BOLD)
        data_box.tag_configure('sep',        foreground=FG_MUTED)

        headers = self._result.get('headers', [])
        rows = [r for r in self._result.get('rows', []) if r.get('type') == 'data']
        data_box.configure(state='normal')
        if headers:
            data_box.insert('end',
                            ' | '.join(f'{h:12}' for h in headers) + '\n', 'hdr')
            data_box.insert('end', '─' * 60 + '\n', 'sep')
        for row in rows:
            cells = row.get('cells', [])
            confs = row.get('confidence', [100] * len(cells))
            for i, cell in enumerate(cells):
                if i > 0:
                    data_box.insert('end', ' | ')
                txt = f'{str(cell):12}'
                c_val = confs[i] if i < len(confs) else 100
                tag = ('conf_bad' if c_val < 35
                       else 'conf_warn' if c_val < 60
                       else '')
                if tag:
                    data_box.insert('end', txt, tag)
                else:
                    data_box.insert('end', txt)
            data_box.insert('end', '\n')
        if not rows:
            data_box.insert('end', '(aucune ligne extraite)')
        data_box.configure(state='disabled')

        # Légende de confiance (sous le tableau)
        tk.Label(
            left,
            text="■ orange < 60 %   ■ rouge < 35 %   (confiance OCR Tesseract)",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(0, 4))

        # Colonne droite : métadonnées + commentaire
        right = tk.Frame(body, bg=BG_MAIN)
        right.pack(side='left', fill='both', expand=True)

        # Métadonnées
        lf_meta = tk.LabelFrame(
            right, text="Métadonnées",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        lf_meta.pack(fill='x', pady=(0, 8))

        for key, val in meta.items():
            row_f = tk.Frame(lf_meta, bg=BG_PANEL)
            row_f.pack(fill='x', padx=8, pady=2)
            tk.Label(row_f, text=f"{key} :", font=FONT_BOLD,
                     fg=FG_MUTED, bg=BG_PANEL, width=12, anchor='w').pack(side='left')
            tk.Label(row_f, text=str(val), font=FONT_MONO,
                     fg=FG_TEXT, bg=BG_PANEL, anchor='w').pack(side='left')

        if self._image_path:
            img_name = Path(self._image_path).name
            tk.Label(
                lf_meta,
                text=f"Fichier : {img_name}",
                font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL, anchor='w',
            ).pack(fill='x', padx=8, pady=(2, 6))

        # Zone commentaire + statut
        lf_comment = tk.LabelFrame(
            right, text="Commentaire (optionnel)",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        lf_comment.pack(fill='both', expand=True)

        self._status_var = tk.StringVar(value='ok')
        status_row = tk.Frame(lf_comment, bg=BG_PANEL)
        status_row.pack(fill='x', padx=8, pady=(8, 4))
        tk.Radiobutton(
            status_row, text="OK — page correcte",
            variable=self._status_var, value='ok',
            font=FONT_MAIN, fg=FG_OK, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
        ).pack(side='left')
        tk.Radiobutton(
            status_row, text="Problème détecté",
            variable=self._status_var, value='probleme',
            font=FONT_MAIN, fg=FG_ERR, bg=BG_PANEL,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
        ).pack(side='left', padx=(20, 0))

        self._comment_entry = tk.Text(
            lf_comment, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat',
            wrap='word', height=5, padx=6, pady=4,
        )
        self._comment_entry.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self._comment_entry.focus_set()

        # Barre de boutons
        btn_bar = tk.Frame(self, bg=BG_MAIN)
        btn_bar.pack(pady=(4, 10))

        tk.Button(
            btn_bar, text="Valider et continuer",
            font=FONT_BOLD, bg=COL_ACC, fg='white',
            activebackground=BTN_HVR, activeforeground='white',
            relief='flat', padx=24, pady=8, cursor='hand2',
            command=self._valider_accepter,
        ).pack(side='left', padx=(0, 6))

        tk.Button(
            btn_bar, text="Continuer automatiquement",
            font=FONT_BOLD, bg='#27AE60', fg='white',
            activebackground='#1E8449', activeforeground='white',
            relief='flat', padx=18, pady=8, cursor='hand2',
            command=self._valider_auto,
        ).pack(side='left', padx=(0, 12))

        if self._can_retry:
            self._btn_retry = tk.Button(
                btn_bar, text="Relancer l'OCR avec ce feedback",
                font=FONT_BOLD, bg='#E67E22', fg='white',
                activebackground='#D35400', activeforeground='white',
                relief='flat', padx=24, pady=8, cursor='hand2',
                command=self._valider_relancer,
            )
            self._btn_retry.pack(side='left')
            try:
                from config import Config as _Cfg
                _mode = getattr(_Cfg, 'OCR_MODE', 'tesseract')
            except Exception:
                _mode = 'tesseract'
            note_txt = (
                "Le feedback est transmis à Claude Vision."
                if _mode == 'claude'
                else "Relancer l'OCR sur la même image (mode Tesseract)."
            )
            tk.Label(
                btn_bar, text=note_txt,
                font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_MAIN,
            ).pack(side='left', padx=(8, 0))

    def _valider_accepter(self):
        comment = self._comment_entry.get('1.0', 'end').strip()
        is_problem = self._status_var.get() == 'probleme'
        # Appeler le callback AVANT destroy : garantit event.set() même si
        # une exception Tkinter se produit lors de la fermeture du Toplevel.
        self._on_validated(comment, is_problem, retry=False, auto=False)
        self.destroy()

    def _valider_auto(self):
        """Accepte la page courante ET désactive le mode manuel pour la suite."""
        comment = self._comment_entry.get('1.0', 'end').strip()
        self._on_validated(comment, False, retry=False, auto=True)
        self.destroy()

    def _valider_relancer(self):
        comment = self._comment_entry.get('1.0', 'end').strip()
        if not comment:
            import tkinter.messagebox as mb
            mb.showwarning(
                "Feedback requis",
                "Décrivez le problème dans le champ commentaire\n"
                "avant de relancer l'OCR.",
                parent=self,
            )
            return
        self._on_validated(comment, True, retry=True)
        self.destroy()


# ── Fenêtre d'audit ───────────────────────────────────────────────────

class AuditDialog(tk.Toplevel):
    """
    Fenêtre affichant le rapport d'audit du classeur Excel.

    Panneau supérieur : statistiques globales.
    Liste centrale    : problèmes classés par sévérité (critique/attention/info).
    Bas               : analyse IA Claude (si disponible).
    """

    _SEV_COLOR = {
        'critique': FG_ERR,
        'attention': FG_WARN,
        'info':      FG_MUTED,
    }
    _SEV_LABEL = {
        'critique': '⛔ CRITIQUE',
        'attention': '⚠ ATTENTION',
        'info':      'ℹ INFO',
    }

    def __init__(self, parent, audit_result: dict):
        super().__init__(parent)
        self._res = audit_result
        self.title("Rapport d'audit — Borniers")
        self.geometry("860x640")
        self.minsize(700, 480)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._build()

    def _build(self):
        # En-tête
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="Rapport d'audit automatique",
            font=FONT_H2, fg=FG_TEXT, bg=BG_CARD,
        ).pack(side='left', padx=16, pady=10)

        stats = self._res.get('stats', {})
        mode_txt = "Claude API" if self._res.get('mode') == 'claude_api' else "Hors ligne"
        tk.Label(
            hdr,
            text=f"Mode : {mode_txt}  |  {stats.get('borniers', 0)} borniers  |  "
                 f"{stats.get('lignes', 0)} lignes  |  "
                 f"{stats.get('problemes', 0)} problème(s) détecté(s)",
            font=FONT_MAIN, fg=FG_MUTED, bg=BG_CARD,
        ).pack(side='right', padx=16)

        # Corps
        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=14, pady=10)

        problemes = self._res.get('problemes', [])
        analyse_ia = self._res.get('analyse_ia', '')

        # Liste des problèmes
        lf_prob = tk.LabelFrame(
            body, text="Problèmes détectés",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        lf_prob.pack(fill='both', expand=True, pady=(0, 8))

        if not problemes:
            tk.Label(
                lf_prob,
                text="✓  Aucun problème détecté — le classeur semble conforme.",
                font=FONT_MAIN, fg=FG_OK, bg=BG_PANEL,
            ).pack(padx=12, pady=16)
        else:
            box = scrolledtext.ScrolledText(
                lf_prob, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat',
                wrap='word', state='disabled', height=14,
                padx=10, pady=8,
            )
            box.pack(fill='both', expand=True)
            box.tag_config('critique', foreground=FG_ERR)
            box.tag_config('attention', foreground=FG_WARN)
            box.tag_config('info', foreground=FG_MUTED)
            box.tag_config('correction', foreground=FG_OK)
            box.tag_config('sep', foreground=BG_CARD)

            box.configure(state='normal')
            _ordre = {'critique': 0, 'attention': 1, 'info': 2}
            for pb in sorted(problemes, key=lambda p: _ordre.get(p['severite'], 9)):
                sev = pb['severite']
                tag = sev
                label = self._SEV_LABEL.get(sev, sev.upper())
                lignes_txt = (
                    f"  lignes Excel : {pb['lignes']}" if pb.get('lignes') else ""
                )
                box.insert('end', f"{label}  [{pb['code']}]\n", tag)
                box.insert('end', f"  Bornier : {pb['bornier']}\n", tag)
                box.insert('end', f"  {pb['message']}{lignes_txt}\n", tag)
                if pb.get('correction'):
                    box.insert('end', f"  → {pb['correction']}\n", 'correction')
                box.insert('end', "─" * 70 + "\n", 'sep')
            box.configure(state='disabled')

        # Analyse IA
        if analyse_ia:
            lf_ia = tk.LabelFrame(
                body, text="Analyse approfondie (Claude API)",
                font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
                labelanchor='nw', bd=1, relief='groove',
            )
            lf_ia.pack(fill='both', expand=True)

            ia_box = scrolledtext.ScrolledText(
                lf_ia, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
                insertbackground=FG_TEXT, relief='flat',
                wrap='word', state='disabled', height=10,
                padx=10, pady=8,
            )
            ia_box.pack(fill='both', expand=True)
            ia_box.configure(state='normal')
            ia_box.insert('end', analyse_ia)
            ia_box.configure(state='disabled')
        elif self._res.get('mode') == 'hors_ligne':
            tk.Label(
                body,
                text="Astuce : ajoutez une clé API Anthropic dans l'interface pour obtenir\n"
                     "une analyse approfondie par intelligence artificielle.",
                font=FONT_MAIN, fg=FG_MUTED, bg=BG_MAIN, justify='left',
            ).pack(anchor='w', pady=(0, 4))

        # Bouton Fermer
        tk.Button(
            self, text="Fermer", font=FONT_BOLD,
            bg=COL_ACC, fg="white",
            activebackground=BTN_HVR, activeforeground="white",
            relief='flat', padx=24, pady=7, cursor='hand2',
            command=self.destroy,
        ).pack(pady=(0, 10))


# ── Visionneur / éditeur du dictionnaire OCR ─────────────────────────

# Colonne → modèle de tableau associé (informatif, non stocké en JSON)
_COL_TEMPLATE_HINT = {
    'BORNE':       'Bornier standard',
    'COULEUR':     'Bornier standard',
    'SIGNAL':      'Bornier standard',
    'JARRETIERES': 'Bornier standard',
    'TENANT':      'Répartiteur',
    'ABOUTISSANT': 'Répartiteur',
    'REPERE':      'Répartiteur',
    'CABLE':       'Répartiteur',
}


class DictionnaireDialog(tk.Toplevel):
    """
    Visionneur et éditeur du dictionnaire OCR (data_dictionary.json).

    Onglets : un par colonne connue dans le dictionnaire.
    Chaque onglet affiche les valeurs triées avec recherche,
    ajout, modification et suppression.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Dictionnaire OCR")
        self.geometry("760x540")
        self.minsize(600, 420)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._dico    = get_dictionary()
        self._pending = get_pending_dictionary()
        self._trees_final:   dict = {}
        self._trees_pending: dict = {}
        self._search_final:  dict = {}
        self._search_pending: dict = {}
        self._nb_main    = None
        self._nb_final   = None
        self._nb_pending = None
        self._lbl_stats  = None
        self._build()

    # ── Construction principale ───────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(
            hdr,
            text="Dictionnaire OCR — deux niveaux",
            font=FONT_H2, fg=FG_TEXT, bg=BG_CARD,
        ).pack(side='left', padx=16, pady=10)
        self._lbl_stats = tk.Label(
            hdr, text='', font=FONT_MAIN, fg=FG_MUTED, bg=BG_CARD
        )
        self._lbl_stats.pack(side='right', padx=16)
        self._refresh_stats()

        self._nb_main = ttk.Notebook(self)
        self._nb_main.pack(fill='both', expand=True, padx=10, pady=8)

        self._frame_final = tk.Frame(self._nb_main, bg=BG_PANEL)
        self._nb_main.add(self._frame_final, text=self._tab_title_final())
        self._build_final_tab(self._frame_final)

        self._frame_pending = tk.Frame(self._nb_main, bg=BG_PANEL)
        self._nb_main.add(self._frame_pending, text=self._tab_title_pending())
        self._build_pending_tab(self._frame_pending)

        foot = tk.Frame(self, bg=BG_MAIN)
        foot.pack(fill='x', padx=10, pady=(0, 10))
        tk.Button(
            foot, text="Fermer",
            font=FONT_BOLD, bg=BG_CARD, fg=FG_TEXT,
            relief='flat', padx=20, pady=6, cursor='hand2',
            command=self.destroy,
        ).pack(side='right')

    # ── Titres et stats ───────────────────────────────────────────────

    def _tab_title_final(self) -> str:
        n = sum(self._dico.stats().values())
        return f"  Valide ({n})  "

    def _tab_title_pending(self) -> str:
        n = self._pending.total()
        return f"  A valider ({n})  "

    def _refresh_stats(self):
        if self._lbl_stats is None:
            return
        nf = sum(self._dico.stats().values())
        np_ = self._pending.total()
        self._lbl_stats.configure(
            text=f"Valide : {nf}   |   En attente : {np_}"
        )

    def _refresh_main_tab_titles(self):
        if self._nb_main is None:
            return
        self._nb_main.tab(0, text=self._tab_title_final())
        self._nb_main.tab(1, text=self._tab_title_pending())
        self._refresh_stats()

    # ── Onglet 1 : Valide (lecture seule) ────────────────────────────

    def _build_final_tab(self, parent):
        tk.Label(
            parent,
            text="  Protege — uniquement modifiable via validation depuis l'onglet 'A valider'.",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(6, 2))

        stats = self._dico.stats()
        if not stats:
            tk.Label(
                parent,
                text="Dictionnaire final vide.\n"
                     "Validez des valeurs depuis l'onglet 'A valider'.",
                font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL, justify='center',
            ).pack(expand=True)
            return

        self._nb_final = ttk.Notebook(parent)
        self._nb_final.pack(fill='both', expand=True, padx=8, pady=4)
        for col_name in sorted(stats.keys()):
            self._build_col_tab_readonly(col_name)

    def _build_col_tab_readonly(self, col_name: str):
        nb = self._nb_final
        n = len(self._dico.get_all(col_name))
        hint = _COL_TEMPLATE_HINT.get(col_name, 'Autre')
        frame = tk.Frame(nb, bg=BG_PANEL)
        nb.add(frame, text=f"{col_name}  ({n})")
        tk.Label(
            frame,
            text=f"Modele : {hint}   —   {n} valeur(s)   [lecture seule]",
            font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(6, 2))
        sr = tk.Frame(frame, bg=BG_PANEL)
        sr.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(sr, text="Rechercher :", font=FONT_MAIN,
                 fg=FG_MUTED, bg=BG_PANEL).pack(side='left')
        var = tk.StringVar()
        self._search_final[col_name] = var
        tk.Entry(sr, textvariable=var, font=FONT_MONO,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', width=26).pack(side='left', padx=(4, 0))
        var.trace_add('write', lambda *_, c=col_name: self._filter_final(c))
        tk.Button(sr, text="X", font=FONT_MAIN, bg=BG_PANEL, fg=FG_MUTED,
                  relief='flat', cursor='hand2',
                  command=lambda v=var: v.set('')).pack(side='left', padx=2)
        tf = tk.Frame(frame, bg=BG_PANEL)
        tf.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        vsb = ttk.Scrollbar(tf, orient='vertical')
        tree = ttk.Treeview(tf, columns=('valeur',), show='headings',
                            yscrollcommand=vsb.set, selectmode='none')
        vsb.configure(command=tree.yview)
        vsb.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        tree.heading('valeur', text='Valeur validee', anchor='w')
        tree.column('valeur', anchor='w', stretch=True)
        self._trees_final[col_name] = tree
        self._fill_tree_final(col_name)

    def _fill_tree_final(self, col_name: str, filtre: str = ''):
        tree = self._trees_final.get(col_name)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for val in self._dico.get_all(col_name):
            if filtre.upper() in val.upper():
                tree.insert('', 'end', iid=val, values=(val,))

    def _filter_final(self, col_name: str):
        f = self._search_final.get(col_name, tk.StringVar()).get()
        self._fill_tree_final(col_name, f)

    def _refresh_final_tree(self, col_name: str):
        f = self._search_final.get(col_name, tk.StringVar()).get()
        self._fill_tree_final(col_name, f)

    def _refresh_final_tab_title(self, col_name: str):
        nb = self._nb_final
        if nb is None:
            return
        n = len(self._dico.get_all(col_name))
        for idx in range(nb.index('end')):
            if nb.tab(idx, 'text').strip().startswith(col_name):
                nb.tab(idx, text=f"{col_name}  ({n})")
                break

    # ── Onglet 2 : A valider (modifiable) ────────────────────────────

    def _build_pending_tab(self, parent):
        tk.Label(
            parent,
            text="  Valeurs issues de l'import Excel et de la validation manuelle."
                 " Reviewez, puis validez vers le dictionnaire final.",
            font=("Segoe UI", 8), fg='#F0A500', bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(6, 2))

        action_bar = tk.Frame(parent, bg=BG_PANEL)
        action_bar.pack(fill='x', padx=8, pady=(0, 4))
        tk.Button(
            action_bar,
            text="OK Valider tout le dictionnaire",
            font=FONT_MAIN, bg='#1E8449', fg='white',
            activebackground='#145A32', activeforeground='white',
            relief='flat', padx=12, pady=4, cursor='hand2',
            command=self._valider_tout,
        ).pack(side='left')
        tk.Label(
            action_bar,
            text="   Deplace toutes les valeurs en attente vers le dictionnaire valide.",
            font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
        ).pack(side='left')

        stats = self._pending.stats()
        if not stats:
            tk.Label(
                parent,
                text="Aucune valeur en attente.\n"
                     "Importez un fichier Excel (bouton 'Alimenter dictionnaire').",
                font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL, justify='center',
            ).pack(expand=True)
            return

        self._nb_pending = ttk.Notebook(parent)
        self._nb_pending.pack(fill='both', expand=True, padx=8, pady=4)
        for col_name in sorted(stats.keys()):
            self._build_col_tab_pending(col_name)

    def _build_col_tab_pending(self, col_name: str):
        nb = self._nb_pending
        n = len(self._pending.get_all(col_name))
        hint = _COL_TEMPLATE_HINT.get(col_name, 'Autre')
        frame = tk.Frame(nb, bg=BG_PANEL)
        nb.add(frame, text=f"{col_name}  ({n})")
        tk.Label(
            frame,
            text=f"Modele : {hint}   —   {n} valeur(s) en attente",
            font=("Segoe UI", 9), fg='#F0A500', bg=BG_PANEL, anchor='w',
        ).pack(fill='x', padx=8, pady=(6, 2))
        sr = tk.Frame(frame, bg=BG_PANEL)
        sr.pack(fill='x', padx=8, pady=(0, 4))
        tk.Label(sr, text="Rechercher :", font=FONT_MAIN,
                 fg=FG_MUTED, bg=BG_PANEL).pack(side='left')
        var = tk.StringVar()
        self._search_pending[col_name] = var
        tk.Entry(sr, textvariable=var, font=FONT_MONO,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', width=26).pack(side='left', padx=(4, 0))
        var.trace_add('write', lambda *_, c=col_name: self._filter_pending(c))
        tk.Button(sr, text="X", font=FONT_MAIN, bg=BG_PANEL, fg=FG_MUTED,
                  relief='flat', cursor='hand2',
                  command=lambda v=var: v.set('')).pack(side='left', padx=2)
        tf = tk.Frame(frame, bg=BG_PANEL)
        tf.pack(fill='both', expand=True, padx=8, pady=(0, 4))
        vsb = ttk.Scrollbar(tf, orient='vertical')
        tree = ttk.Treeview(tf, columns=('valeur',), show='headings',
                            yscrollcommand=vsb.set, selectmode='browse')
        vsb.configure(command=tree.yview)
        vsb.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)
        tree.heading('valeur', text='Valeur a valider', anchor='w')
        tree.column('valeur', anchor='w', stretch=True)
        self._trees_pending[col_name] = tree
        self._fill_tree_pending(col_name)
        btns = tk.Frame(frame, bg=BG_PANEL)
        btns.pack(fill='x', padx=8, pady=(0, 8))
        for label, cmd, bg_col, fg_col in [
            ("Ajouter", lambda c=col_name: self._ajouter_pending(c), BG_CARD, FG_TEXT),
            ("Modifier", lambda c=col_name: self._modifier_pending(c), COL_ACC, 'white'),
            ("Supprimer", lambda c=col_name: self._supprimer_pending(c), '#C0392B', 'white'),
        ]:
            tk.Button(btns, text=label, font=FONT_MAIN, bg=bg_col, fg=fg_col,
                      relief='flat', padx=10, pady=4, cursor='hand2',
                      command=cmd).pack(side='left', padx=(0, 4))
        tk.Frame(btns, bg=BG_CARD, width=2).pack(side='left', fill='y', padx=6)
        for label, cmd, bg_col in [
            ("OK Valider sel.", lambda c=col_name: self._valider_selection(c), '#1E8449'),
            ("OK Valider colonne", lambda c=col_name: self._valider_colonne(c), '#1A5276'),
            ("X  Rejeter sel.", lambda c=col_name: self._rejeter_selection(c), '#784212'),
        ]:
            tk.Button(btns, text=label, font=FONT_MAIN, bg=bg_col, fg='white',
                      relief='flat', padx=10, pady=4, cursor='hand2',
                      command=cmd).pack(side='left', padx=(0, 4))

    def _fill_tree_pending(self, col_name: str, filtre: str = ''):
        tree = self._trees_pending.get(col_name)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for val in self._pending.get_all(col_name):
            if filtre.upper() in val.upper():
                tree.insert('', 'end', iid=val, values=(val,))

    def _filter_pending(self, col_name: str):
        f = self._search_pending.get(col_name, tk.StringVar()).get()
        self._fill_tree_pending(col_name, f)

    def _selected_pending(self, col_name: str):
        tree = self._trees_pending.get(col_name)
        if tree is None:
            return None
        sel = tree.selection()
        return sel[0] if sel else None

    def _refresh_pending_tab_title(self, col_name: str):
        nb = self._nb_pending
        if nb is None:
            return
        n = len(self._pending.get_all(col_name))
        for idx in range(nb.index('end')):
            if nb.tab(idx, 'text').strip().startswith(col_name):
                nb.tab(idx, text=f"{col_name}  ({n})")
                break

    # ── CRUD sur le pending ───────────────────────────────────────────

    def _ajouter_pending(self, col_name: str):
        dlg = _SimpleInput(self, title="Ajouter une valeur",
                           label=f"Nouvelle valeur pour {col_name} :")
        self.wait_window(dlg)
        val = dlg.result
        if not val:
            return
        if self._pending.add_value(col_name, val):
            self._pending.save()
            self._fill_tree_pending(col_name)
            self._refresh_pending_tab_title(col_name)
            self._refresh_main_tab_titles()
            messagebox.showinfo("Ajoute", f"OK  '{val}' ajoute.", parent=self)
        else:
            messagebox.showwarning("Non ajoute",
                                   f"'{val}' est invalide ou deja present.",
                                   parent=self)

    def _modifier_pending(self, col_name: str):
        old = self._selected_pending(col_name)
        if not old:
            messagebox.showwarning("Selection requise",
                                   "Selectionnez d'abord une valeur.", parent=self)
            return
        dlg = _SimpleInput(self, title="Modifier la valeur",
                           label=f"Nouvelle valeur (remplace '{old}') :",
                           default=old)
        self.wait_window(dlg)
        new_val = dlg.result
        if not new_val or new_val == old:
            return
        if self._pending.update_value(col_name, old, new_val):
            self._pending.save()
            self._fill_tree_pending(col_name)
        else:
            messagebox.showwarning("Non modifie",
                                   f"'{new_val}' est invalide.", parent=self)

    def _supprimer_pending(self, col_name: str):
        val = self._selected_pending(col_name)
        if not val:
            messagebox.showwarning("Selection requise",
                                   "Selectionnez d'abord une valeur.", parent=self)
            return
        if messagebox.askyesno("Confirmer",
                               f"Supprimer '{val}' de {col_name} ?",
                               parent=self):
            self._pending.remove_value(col_name, val)
            self._pending.save()
            self._fill_tree_pending(col_name)
            self._refresh_pending_tab_title(col_name)
            self._refresh_main_tab_titles()

    # ── Validation / rejet ────────────────────────────────────────────

    def _valider_selection(self, col_name: str):
        val = self._selected_pending(col_name)
        if not val:
            messagebox.showwarning("Selection requise",
                                   "Selectionnez une valeur a valider.", parent=self)
            return
        n = self._pending.validate_values(self._dico, col_name, [val])
        if n:
            messagebox.showinfo("Valide",
                                f"OK  '{val}' ajoute au dictionnaire final.",
                                parent=self)
        else:
            messagebox.showwarning("Rejete",
                                   f"'{val}' n'est pas accepte (invalide ou deja present).",
                                   parent=self)
        self._fill_tree_pending(col_name)
        self._refresh_pending_tab_title(col_name)
        self._refresh_final_tree(col_name)
        self._refresh_final_tab_title(col_name)
        self._refresh_main_tab_titles()

    def _valider_colonne(self, col_name: str):
        n_pending = len(self._pending.get_all(col_name))
        if not n_pending:
            messagebox.showinfo("Colonne vide",
                                f"Aucune valeur en attente pour {col_name}.",
                                parent=self)
            return
        if not messagebox.askyesno(
            "Valider la colonne",
            f"Valider les {n_pending} valeurs de '{col_name}' vers le dictionnaire final ?",
            parent=self,
        ):
            return
        n = self._pending.validate_values(self._dico, col_name)
        messagebox.showinfo("Termine",
                            f"OK  {n} valeur(s) ajoutee(s) au dictionnaire final.",
                            parent=self)
        self._fill_tree_pending(col_name)
        self._refresh_pending_tab_title(col_name)
        self._refresh_final_tree(col_name)
        self._refresh_final_tab_title(col_name)
        self._refresh_main_tab_titles()

    def _valider_tout(self):
        total_pending = self._pending.total()
        if not total_pending:
            messagebox.showinfo("Rien a valider",
                                "Le dictionnaire en attente est vide.", parent=self)
            return
        if not messagebox.askyesno(
            "Valider tout",
            f"Valider les {total_pending} valeurs en attente vers le dictionnaire final ?\n\n"
            "Les valeurs invalides seront automatiquement rejetees.",
            parent=self,
        ):
            return
        n = self._pending.validate_values(self._dico)
        messagebox.showinfo(
            "Termine",
            f"OK  {n} valeur(s) ajoutee(s) au dictionnaire final.\n"
            f"    {total_pending - n} rejetee(s) (invalides).",
            parent=self,
        )
        for col in list(self._trees_final.keys()):
            self._refresh_final_tree(col)
            self._refresh_final_tab_title(col)
        for col in list(self._trees_pending.keys()):
            self._fill_tree_pending(col)
            self._refresh_pending_tab_title(col)
        self._refresh_main_tab_titles()

    def _rejeter_selection(self, col_name: str):
        val = self._selected_pending(col_name)
        if not val:
            messagebox.showwarning("Selection requise",
                                   "Selectionnez une valeur a rejeter.", parent=self)
            return
        if messagebox.askyesno(
            "Rejeter",
            f"Rejeter definitvement '{val}' ?\nElle ne sera pas ajoutee au dictionnaire final.",
            parent=self,
        ):
            self._pending.remove_value(col_name, val)
            self._pending.save()
            self._fill_tree_pending(col_name)
            self._refresh_pending_tab_title(col_name)
            self._refresh_main_tab_titles()


# ── Dialogue de test / diagnostic Ollama ─────────────────────────────

class OllamaTestDialog(tk.Toplevel):
    """
    Diagnostic Ollama en 4 étapes :
      1. Serveur accessible
      2. Modèle installé
      3. Modèle vision (supporte les images)
      4. Test avec une image réelle (optionnel)

    Lance le diagnostic automatiquement à l'ouverture.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("🧪 Test Ollama")
        self.geometry("640x520")
        self.minsize(560, 440)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._result = None
        self._build()
        self.after(200, self._lancer_tests_connection)

    def _build(self):
        from config import Config
        model = getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')
        raw_url = getattr(Config, 'OLLAMA_URL', 'http://localhost:11434')
        host = raw_url.split('/v1/')[0] if '/v1/' in raw_url else raw_url

        # En-tête
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🧪 Diagnostic Ollama Vision",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD).pack(
            side='left', padx=16, pady=10)
        tk.Label(hdr, text=f"{model}  @  {host}",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_CARD).pack(
            side='right', padx=16)

        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=16, pady=10)

        # Checklist diagnostic
        checks_frame = tk.LabelFrame(
            body, text="Diagnostic de connexion",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        checks_frame.pack(fill='x', pady=(0, 10))

        self._check_icons = {}
        checks = [
            ('server', f"Serveur Ollama accessible ({host})"),
            ('model',  f"Modèle '{model}' installé"),
            ('vision', "Modèle vision (supporte les images)"),
            ('sdk',    "SDK Python officiel (ollama)"),
        ]
        for key, label in checks:
            row = tk.Frame(checks_frame, bg=BG_PANEL)
            row.pack(fill='x', padx=12, pady=5)
            icon = tk.Label(row, text="⏳", font=FONT_MONO,
                            fg=FG_MUTED, bg=BG_PANEL, width=3)
            icon.pack(side='left')
            tk.Label(row, text=label, font=FONT_MAIN,
                     fg=FG_TEXT, bg=BG_PANEL).pack(side='left', padx=(6, 0))
            self._check_icons[key] = icon

        self._err_label = tk.Label(
            body, text="", font=FONT_MAIN,
            fg=FG_ERR, bg=BG_MAIN, wraplength=560, justify='left',
        )
        self._err_label.pack(fill='x')

        # Zone test image
        img_frame = tk.LabelFrame(
            body, text="Test avec une image réelle (optionnel)",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
            labelanchor='nw', bd=1, relief='groove',
        )
        img_frame.pack(fill='both', expand=True, pady=(6, 0))

        img_top = tk.Frame(img_frame, bg=BG_PANEL)
        img_top.pack(fill='x', padx=10, pady=8)

        self._img_path_var = tk.StringVar()
        tk.Entry(
            img_top, textvariable=self._img_path_var, font=FONT_MONO,
            bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
            relief='flat', bd=4,
        ).pack(side='left', fill='x', expand=True)

        tk.Button(
            img_top, text="Parcourir…", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground='white',
            relief='flat', padx=8, pady=4, cursor='hand2',
            command=self._choisir_image,
        ).pack(side='left', padx=(8, 0))

        self._btn_test_img = tk.Button(
            img_top, text="Envoyer →",
            font=FONT_BOLD, bg='#1A5276', fg='white',
            activebackground='#154360', activeforeground='white',
            relief='flat', padx=10, pady=4, cursor='hand2',
            state='disabled',
            command=self._tester_image,
        )
        self._btn_test_img.pack(side='left', padx=(6, 0))

        tk.Label(img_frame, text="Réponse brute Ollama :",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x', padx=10)

        self._raw_box = scrolledtext.ScrolledText(
            img_frame, font=FONT_MONO, bg=BG_LOG, fg='#a0c0a0',
            insertbackground=FG_TEXT, relief='flat', height=7,
            state='disabled', padx=8, pady=6,
        )
        self._raw_box.pack(fill='both', expand=True, padx=10, pady=(0, 8))

        # Boutons bas
        footer = tk.Frame(self, bg=BG_MAIN)
        footer.pack(fill='x', padx=16, pady=(0, 12))

        self._btn_relancer = tk.Button(
            footer, text="↻  Relancer le diagnostic",
            font=FONT_MAIN, bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground='white',
            relief='flat', padx=14, pady=6, cursor='hand2',
            command=self._lancer_tests_connection,
        )
        self._btn_relancer.pack(side='left')

        tk.Button(
            footer, text="Fermer",
            font=FONT_BOLD, bg=COL_ACC, fg='white',
            activebackground=BTN_HVR, activeforeground='white',
            relief='flat', padx=24, pady=6, cursor='hand2',
            command=self.destroy,
        ).pack(side='right')

    # ── Diagnostic connexion ──────────────────────────────────────────

    def _set_check(self, key: str, ok):
        widget = self._check_icons.get(key)
        if widget is None:
            return
        if ok is None:
            widget.configure(text="⏳", fg=FG_MUTED)
        elif ok:
            widget.configure(text="✓ ", fg=FG_OK)
        else:
            widget.configure(text="✗ ", fg=FG_ERR)

    def _lancer_tests_connection(self):
        self._btn_relancer.configure(state='disabled')
        self._btn_test_img.configure(state='disabled')
        self._err_label.configure(text="")
        for key in self._check_icons:
            self._set_check(key, None)
        self._set_raw("Diagnostic en cours…")

        def _worker():
            try:
                import ollama_ocr
                result = ollama_ocr.test_ollama_connection()
            except Exception as exc:
                result = {
                    'ok': False, 'erreur': str(exc),
                    'server_running': False, 'model_found': False,
                    'model_vision': False, 'sdk': False, 'models': [],
                }
            self.after(0, lambda r=result: self._afficher_resultats(r))

        threading.Thread(target=_worker, daemon=True).start()

    def _afficher_resultats(self, r: dict):
        self._result = r
        self._set_check('server', r.get('server_running', False))
        self._set_check('model',  r.get('model_found', False))
        self._set_check('vision', r.get('model_vision', False))
        self._set_check('sdk',    r.get('sdk', False))

        err = r.get('erreur', '')
        if err:
            self._err_label.configure(text=f"⚠  {err}")

        models = r.get('models', [])
        if models:
            self._set_raw(
                "Modèles Ollama installés :\n" +
                "\n".join(f"  • {m}" for m in models)
            )
        elif not r.get('server_running'):
            self._set_raw(
                "Serveur Ollama inaccessible.\n\n"
                "Pour démarrer Ollama :\n"
                "  1. Ouvrez Ollama (icône dans la barre système)\n"
                "  2. Attendez que l'icône soit active\n"
                "  3. Cliquez ↻ Relancer le diagnostic\n\n"
                "Si Ollama n'est pas installé :\n"
                "  → https://ollama.com"
            )

        can_test = (r.get('server_running') and
                    r.get('model_found') and
                    r.get('model_vision'))
        self._btn_test_img.configure(state='normal' if can_test else 'disabled')
        self._btn_relancer.configure(state='normal')

    # ── Test image ────────────────────────────────────────────────────

    def _choisir_image(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choisir une image de test (bornier scanné)",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.bmp"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self._img_path_var.set(path)

    # Timeouts dédiés au test image (distincts du pipeline de conversion)
    _TM_WARMUP = 60   # préchauffage texte seul (s)
    _TM_IMAGE = 300  # envoi image réelle     (s)

    def _tester_image(self):
        img_path = self._img_path_var.get().strip()
        if not img_path or not Path(img_path).exists():
            messagebox.showwarning("Image manquante",
                                   "Choisissez une image à tester.",
                                   parent=self)
            return

        self._btn_test_img.configure(state='disabled', text="⏳  Envoi…")
        self._set_raw(
            "Étape 1/3 — Préchauffage du modèle...\n"
            "La première requête peut prendre 1 à 3 minutes."
        )

        tm_warmup = self._TM_WARMUP
        tm_image = self._TM_IMAGE

        def _worker():
            import time
            import ollama_ocr
            from config import Config

            model = getattr(Config, 'OLLAMA_MODEL', 'qwen2.5vl:7b')
            url = getattr(Config, 'OLLAMA_URL',
                          'http://localhost:11434/v1/chat/completions')

            # ── Info de départ ────────────────────────────────────
            orig_path = Path(img_path)
            try:
                from PIL import Image as _PILImg
                with _PILImg.open(orig_path) as _pim:
                    w0, h0 = _pim.size
                orig_info = f"{w0}x{h0} px"
            except Exception:
                w0, h0 = 0, 0
                orig_info = "(taille inconnue)"

            sep = "─" * 46
            header = (
                f"Modele  : {model}\n"
                f"Image   : {orig_path.name}  ({orig_info})\n"
                f"Timeout : {tm_image} s\n"
                f"SDK     : {'oui' if ollama_ocr._SDK_DISPONIBLE else 'non (HTTP)'}\n"
                f"{sep}\n"
            )
            self.after(0, lambda h=header: self._set_raw(
                h + "Etape 1/3 — Préchauffage du modèle...\n"
                "La première requête peut prendre 1 à 3 minutes."
            ))

            # ── Étape 1 : préchauffage ────────────────────────────
            t_start = time.time()
            ok_wup, err_wup = ollama_ocr._prechauffer_modele(
                model, url, tm_warmup
            )
            dur_wup = time.time() - t_start

            if not ok_wup:
                e_lower = err_wup.lower()
                if 'timeout' in e_lower or 'timed out' in e_lower:
                    msg = (
                        header +
                        f"X  Préchauffage : timeout après {tm_warmup} s\n\n"
                        "Le modèle est en cours de chargement (RAM/GPU).\n"
                        "La première requête peut prendre 1 à 3 minutes.\n\n"
                        "Conseil : dans PowerShell, tapez :\n"
                        f"  ollama run {model}\n"
                        "Attendez la réponse, puis relancez le test image."
                    )
                else:
                    msg = header + f"X  Préchauffage échoué :\n{err_wup}"
                self.after(0, lambda m=msg: self._fin_test_image(m))
                return

            u1 = (
                header +
                f"OK  Modèle actif ({dur_wup:.1f} s)\n\n"
                "Etape 2/3 — Redimensionnement de l'image..."
            )
            self.after(0, lambda m=u1: self._set_raw(m))

            # ── Étape 2 : redimensionnement ───────────────────────
            img_to_send = orig_path
            resize_info = ""
            _MAX_W, _MAX_H = 1600, 2200
            if w0 > _MAX_W or h0 > _MAX_H:
                try:
                    from PIL import Image as _PILImg2
                    import tempfile
                    with _PILImg2.open(orig_path) as _pim2:
                        _pim2.thumbnail((_MAX_W, _MAX_H), _PILImg2.LANCZOS)
                        tmp = tempfile.NamedTemporaryFile(
                            suffix='.jpg', delete=False,
                            prefix='ollama_test_',
                        )
                        _pim2.save(tmp.name, 'JPEG', quality=85)
                        img_to_send = Path(tmp.name)
                        w1, h1 = _pim2.size
                    resize_info = (
                        f"Redimensionne : {w0}x{h0} → {w1}x{h1} px\n"
                    )
                except Exception as re_err:
                    resize_info = f"Redimensionnement ignoré ({re_err})\n"

            u2 = (
                header +
                f"OK  Modèle actif ({dur_wup:.1f} s)\n" +
                resize_info +
                f"\nEtape 3/3 — Envoi de l'image (timeout {tm_image} s)..."
            )
            self.after(0, lambda m=u2: self._set_raw(m))

            # ── Étape 3 : envoi de l'image ────────────────────────
            prompt = (
                "Lis ce tableau de borniers electriques. "
                "Renvoie chaque ligne du tableau en separant "
                "les colonnes par ' | '. "
                "Réponse uniquement : les lignes de données, "
                "une par ligne."
            )
            t_img = time.time()
            try:
                raw = ollama_ocr._appeler_ollama(
                    model, prompt, img_to_send, url, tm_image,
                )
                dur_img = time.time() - t_img
                dur_tot = time.time() - t_start
                result = (
                    header +
                    f"OK  Modèle actif ({dur_wup:.1f} s)\n" +
                    resize_info +
                    f"OK  Réponse reçue en {dur_img:.1f} s"
                    f"  (total {dur_tot:.1f} s)\n"
                    f"{sep}\n" +
                    (raw.strip() if raw.strip() else "(réponse vide)")
                )
                self.after(0, lambda m=result: self._fin_test_image(m))
            except Exception as exc:
                dur_fail = time.time() - t_img
                err_msg = str(exc)
                e2_lower = err_msg.lower()
                if 'timeout' in e2_lower or 'timed out' in e2_lower:
                    msg = (
                        header +
                        f"OK  Modèle actif ({dur_wup:.1f} s)\n" +
                        resize_info +
                        f"X  Ollama trop lent après {dur_fail:.0f} s\n\n"
                        "Causes possibles :\n"
                        "  - Modèle trop lourd (essayez qwen2.5vl:3b)\n"
                        "  - Image encore trop grande\n"
                        "  - Ollama saturé par un appel précédent\n\n"
                        "Solutions :\n"
                        f"  1. ollama run {model}  (préchauffage manuel)\n"
                        "  2. Testez avec une image plus petite\n"
                        "  3. Redémarrez Ollama\n\n"
                        f"Erreur exacte : {err_msg}"
                    )
                else:
                    msg = (
                        header +
                        f"OK  Modèle actif ({dur_wup:.1f} s)\n" +
                        resize_info +
                        f"X  Erreur envoi image :\n{err_msg}"
                    )
                self.after(0, lambda m=msg: self._fin_test_image(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _fin_test_image(self, text: str):
        """Affiche le résultat final du test image et réactive le bouton."""
        self._set_raw(text)
        self._btn_test_img.configure(state='normal', text="Envoyer →")

    def _on_image_done(self, text: str):
        self._fin_test_image(text)

    def _on_image_error(self, msg: str):
        self._fin_test_image(msg)

    def _set_raw(self, text: str):
        self._raw_box.configure(state='normal')
        self._raw_box.delete('1.0', 'end')
        self._raw_box.insert('end', text)
        self._raw_box.configure(state='disabled')


# ── Visualiseur journal Ollama ────────────────────────────────────────

class OllamaLogDialog(tk.Toplevel):
    """Fenêtre de visualisation du journal Ollama (_ollama.jsonl).

    Affiche pour chaque image :
      - le nom de l'image traitée
      - les lignes extraites (une ligne = val1 | val2 | val3 | val4)
      - la réponse brute complète d'Ollama (raw)
    """

    def __init__(self, parent, log_path: Path):
        super().__init__(parent)
        self.title(f"🦙 Journal Ollama — {log_path.name}")
        self.geometry("900x650")
        self.configure(bg=BG_MAIN)
        self.resizable(True, True)

        # Lecture du JSONL
        entries = []
        try:
            with open(log_path, encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de lire le journal :\n{e}",
                                 parent=self)
            self.destroy()
            return

        # ── En-tête ───────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG_PANEL, pady=8)
        hdr.pack(fill='x')
        tk.Label(
            hdr,
            text=f"  🦙 Journal Ollama  —  {len(entries)} pages  —  {log_path.name}",
            font=FONT_BOLD, fg=FG_TEXT, bg=BG_PANEL,
        ).pack(side='left', padx=12)

        # ── Sélecteur de page (liste gauche) ──────────────────────────
        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True)

        list_frame = tk.Frame(body, bg=BG_PANEL, width=200)
        list_frame.pack(side='left', fill='y')
        list_frame.pack_propagate(False)

        tk.Label(list_frame, text="Pages traitées",
                 font=FONT_BOLD, fg=FG_MUTED, bg=BG_PANEL).pack(pady=(8, 4))

        self._listbox = tk.Listbox(
            list_frame, bg=BG_CARD, fg=FG_TEXT,
            selectbackground=COL_ACC2, font=FONT_MONO,
            relief='flat', bd=0,
        )
        self._listbox.pack(fill='both', expand=True, padx=4, pady=4)
        for e in entries:
            img = e.get('image', '?')
            n = e.get('rows', 0)
            ok = '✓' if e.get('success') else '✗'
            self._listbox.insert('end', f"{ok} {img}  ({n}L)")

        # ── Zone de détail (droite) ───────────────────────────────────
        detail_frame = tk.Frame(body, bg=BG_MAIN)
        detail_frame.pack(side='left', fill='both', expand=True)

        # Onglets : Données structurées | Réponse brute
        nb = ttk.Notebook(detail_frame)
        nb.pack(fill='both', expand=True, padx=8, pady=8)

        self._txt_data = scrolledtext.ScrolledText(
            nb, bg=BG_LOG, fg=FG_TEXT, font=FONT_MONO,
            relief='flat', state='disabled',
        )
        self._txt_raw = scrolledtext.ScrolledText(
            nb, bg=BG_LOG, fg='#a0c0a0', font=FONT_MONO,
            relief='flat', state='disabled',
        )
        nb.add(self._txt_data, text="  Données structurées  ")
        nb.add(self._txt_raw,  text="  Réponse brute Ollama  ")

        self._entries = entries
        self._listbox.bind('<<ListboxSelect>>', self._on_select)
        if entries:
            self._listbox.selection_set(0)
            self._show_entry(entries[0])

    def _on_select(self, _event):
        sel = self._listbox.curselection()
        if sel:
            self._show_entry(self._entries[sel[0]])

    def _show_entry(self, entry: dict):
        # ── Données structurées ───────────────────────────────────────
        lines = []
        lines.append(f"Image   : {entry.get('image', '?')}")
        lines.append(f"Modèle  : {entry.get('model', '?')}")
        lines.append(f"Succès  : {entry.get('success', False)}")
        lines.append(f"Lignes  : {entry.get('rows', 0)}")
        meta = entry.get('metadata', {})
        if meta:
            lines.append(f"Métadonnées : {meta}")
        lines.append("")

        rows_data = entry.get('rows_data', [])
        if rows_data:
            lines.append("─── Tableau extrait par Ollama ───────────────────────")
            for i, row in enumerate(rows_data, 1):
                cells = row.get('cells', [])
                lines.append(f"  L{i:02d} : {' | '.join(str(c) for c in cells)}")
        elif not entry.get('success'):
            lines.append(f"Erreur : {entry.get('error', '—')}")

        self._txt_data.configure(state='normal')
        self._txt_data.delete('1.0', 'end')
        self._txt_data.insert('end', '\n'.join(lines))
        self._txt_data.configure(state='disabled')

        # ── Réponse brute ─────────────────────────────────────────────
        self._txt_raw.configure(state='normal')
        self._txt_raw.delete('1.0', 'end')
        self._txt_raw.insert('end', entry.get('raw', '(vide)'))
        self._txt_raw.configure(state='disabled')


# ── Visualiseur données API brutes vs traitées ────────────────────────

class ObservateurAPIDialog(tk.Toplevel):
    """Visualiseur des données brutes API vs données traitées par page."""

    def __init__(self, parent, log_path: Path):
        super().__init__(parent)
        self._log_path = log_path
        self._entries = self._load_log()
        self.title(f"Observation données API — {len(self._entries)} pages")
        self.geometry("1100x680")
        self.minsize(900, 500)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()
        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass
        self._build()

    def _load_log(self):
        import json as _json
        entries = []
        try:
            with open(self._log_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(_json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
        return entries

    def _build(self):
        # En-tête
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Observation données API  ←→  données traitées",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD).pack(side='left', padx=16, pady=10)
        tk.Label(hdr, text=f"{len(self._entries)} pages enregistrées",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_CARD).pack(side='right', padx=16)

        # Corps principal
        body = tk.Frame(self, bg=BG_MAIN)
        body.pack(fill='both', expand=True, padx=10, pady=8)

        # Colonne gauche : liste des pages
        left = tk.Frame(body, bg=BG_PANEL, width=200)
        left.pack(side='left', fill='y', padx=(0, 6))
        left.pack_propagate(False)

        tk.Label(left, text="Pages", font=FONT_BOLD, fg=FG_MUTED, bg=BG_PANEL
                 ).pack(anchor='w', padx=8, pady=(8, 4))

        self._listbox = tk.Listbox(
            left, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            selectbackground=COL_ACC, selectforeground='white',
            relief='flat', borderwidth=0, activestyle='none',
        )
        self._listbox.pack(fill='both', expand=True, padx=4, pady=(0, 4))
        for e in self._entries:
            img = e.get('image', '?')
            rows = e.get('rows', 0)
            ok = '✓' if e.get('success') else '✗'
            self._listbox.insert('end', f"{ok} {img}  ({rows}L)")
        self._listbox.bind('<<ListboxSelect>>', self._on_select)

        # Colonne droite : deux zones de texte
        right = tk.Frame(body, bg=BG_MAIN)
        right.pack(side='left', fill='both', expand=True)

        # Panneau brut
        lf_raw = tk.LabelFrame(right, text="Réponse brute API Claude",
                               font=FONT_BOLD, fg=FG_WARN, bg=BG_PANEL,
                               labelanchor='nw', bd=1, relief='groove')
        lf_raw.pack(fill='both', expand=True, pady=(0, 6))
        self._raw_box = scrolledtext.ScrolledText(
            lf_raw, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', wrap='none',
            state='disabled', height=14, padx=8, pady=6)
        self._raw_box.pack(fill='both', expand=True)

        # Panneau traité
        lf_proc = tk.LabelFrame(right, text="Données après traitement (Excel)",
                                font=FONT_BOLD, fg=FG_OK, bg=BG_PANEL,
                                labelanchor='nw', bd=1, relief='groove')
        lf_proc.pack(fill='both', expand=True)
        self._proc_box = scrolledtext.ScrolledText(
            lf_proc, font=FONT_MONO, bg=BG_LOG, fg=FG_TEXT,
            insertbackground=FG_TEXT, relief='flat', wrap='none',
            state='disabled', height=10, padx=8, pady=6)
        self._proc_box.pack(fill='both', expand=True)

        # Barre de statut régénération
        self._status_bar = tk.Label(
            self, text="", font=FONT_MONO,
            fg=FG_MUTED, bg=BG_PANEL,
            anchor='w', padx=10, pady=4,
        )
        self._status_bar.pack(fill='x')

        # Barre de boutons bas
        footer = tk.Frame(self, bg=BG_MAIN)
        footer.pack(fill='x', pady=(0, 8), padx=10)

        tk.Button(
            footer, text="📂  Ouvrir un autre log…", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_TEXT,
            activebackground=COL_ACC2, activeforeground="white",
            relief='flat', padx=14, pady=7, cursor='hand2',
            command=self._charger_autre_log,
        ).pack(side='left')

        self._btn_regen = tk.Button(
            footer, text="⟳  Régénérer Excel depuis ce log", font=FONT_MAIN,
            bg=COL_ACC2, fg=FG_TEXT,
            activebackground=COL_ACC, activeforeground="white",
            relief='flat', padx=14, pady=7, cursor='hand2',
            command=self._regenerer_excel,
        )
        self._btn_regen.pack(side='left', padx=(8, 0))

        tk.Button(
            footer, text="Fermer", font=FONT_BOLD,
            bg=COL_ACC, fg='white', activebackground=BTN_HVR,
            activeforeground='white', relief='flat', padx=24, pady=7,
            cursor='hand2', command=self.destroy,
        ).pack(side='right')

        # Sélectionner la première entrée
        if self._entries:
            self._listbox.selection_set(0)
            self._on_select(None)

    def _on_select(self, _event):
        sel = self._listbox.curselection()
        if not sel:
            return
        entry = self._entries[sel[0]]

        self._set_text(self._raw_box, entry.get('raw', '(aucune réponse enregistrée)'))

        import json as _json
        meta = entry.get('metadata', {})
        rows = entry.get('rows', 0)
        ts = entry.get('ts', '')
        err = entry.get('error', '')
        lines = [
            f"Image    : {entry.get('image', '?')}",
            f"Horodatage : {ts}",
            f"Modèle   : {entry.get('model', '?')}",
            f"Succès   : {'Oui' if entry.get('success') else 'Non — ' + err}",
            f"Lignes   : {rows}",
            f"Métadonnées : {_json.dumps(meta, ensure_ascii=False)}",
        ]
        self._set_text(self._proc_box, '\n'.join(lines))

    def _charger_autre_log(self):
        """Ouvre un sélecteur de fichier et recharge le visualiseur."""
        path = filedialog.askopenfilename(
            title="Sélectionner un journal API Claude",
            filetypes=[("Journaux Claude", "*.jsonl"), ("Tous les fichiers", "*.*")],
            parent=self,
        )
        if not path:
            return
        self._log_path = Path(path)
        self._entries = self._load_log()
        self.title(f"Observation données API — {len(self._entries)} pages")
        # Vider et repeupler la listbox
        self._listbox.delete(0, 'end')
        for e in self._entries:
            img = e.get('image', '?')
            rows = e.get('rows', 0)
            ok = '✓' if e.get('success') else '✗'
            self._listbox.insert('end', f"{ok} {img}  ({rows}L)")
        self._set_text(self._raw_box,  '')
        self._set_text(self._proc_box, '')
        if self._entries:
            self._listbox.selection_set(0)
            self._on_select(None)

    def _regenerer_excel(self):
        """Régénère le classeur Excel depuis le log sélectionné, sans appeler l'API."""
        outdir = filedialog.askdirectory(
            title="Dossier de destination pour l'Excel régénéré",
            parent=self,
        )
        if not outdir:
            return

        # Récupérer le modèle de tableau actif dans la fenêtre principale
        main = self.master
        tpl = None
        try:
            tpl = main._tpl_manager.get(main._tpl_var.get())
        except Exception:
            pass

        self._btn_regen.configure(state='disabled', text="⏳  Régénération…")
        self._set_status("Régénération en cours…", FG_WARN)
        self.configure(cursor='watch')

        def _worker():
            try:
                from converter import Converter
                conv = Converter(
                    word_file=self._log_path,
                    output_dir=Path(outdir),
                    template=tpl,
                    on_progress=lambda p, m: self.after(
                        0, lambda: self._set_status(f"{int(p*100):3d}%  {m}", FG_WARN)
                    ),
                    on_log=lambda m: None,
                )
                result = conv.run()
                self.after(0, lambda r=result: self._on_regen_done(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_regen_error(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_status(self, msg: str, color: str = None):
        """Met à jour la barre de statut (thread-safe si appelé via after())."""
        self._status_bar.configure(
            text=msg,
            fg=color or FG_MUTED,
        )

    def _on_regen_done(self, result: dict):
        excel = result.get('excel')
        self._btn_regen.configure(state='normal', text="⟳  Régénérer Excel depuis ce log")
        self.configure(cursor='')
        nb = result.get('tableaux', 0)
        self._set_status(
            f"✓  {nb} bornier(s) — {Path(excel).name}" if excel else f"✓  {nb} bornier(s)",
            FG_OK,
        )
        if excel and Path(excel).exists():
            if messagebox.askyesno(
                "Régénération terminée",
                f"{nb} bornier(s) converti(s).\n\nOuvrir {Path(excel).name} ?",
                parent=self,
            ):
                os.startfile(str(excel))

    def _on_regen_error(self, msg: str):
        self._btn_regen.configure(state='normal', text="⟳  Régénérer Excel depuis ce log")
        self.configure(cursor='')
        self._set_status(f"✗  Erreur : {msg[:80]}", FG_ERR)
        messagebox.showerror("Erreur de régénération", msg, parent=self)

    @staticmethod
    def _set_text(widget, text: str):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('end', text)
        widget.configure(state='disabled')


# ── Éditeur de modèle de tableau ─────────────────────────────────────

class TemplateEditorDialog(tk.Toplevel):
    """
    Boîte de dialogue pour créer ou modifier un modèle de tableau.

    Panneau gauche  : configuration (colonnes, pied de page, séparateur).
    Panneau droite  : aperçu Canvas mis à jour en temps réel montrant
                      l'en-tête + 10 lignes minimum + pied de page.
    """

    def __init__(self, parent, template: TableTemplate,
                 manager: TemplateManager):
        super().__init__(parent)
        self._tpl = template
        self._mgr = manager
        self._saved = False
        self._saved_name = None

        self.title("Éditeur de modèle")
        self.geometry("980x660")
        self.minsize(800, 560)
        self.resizable(True, True)
        self.configure(bg=BG_MAIN)
        self.grab_set()

        ico = _resource("icon.ico")
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self._build()

    # ── Construction principale ───────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=BG_CARD, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Éditeur de modèle de tableau",
                 font=FONT_H2, fg=FG_TEXT, bg=BG_CARD
                 ).pack(side='left', padx=16, pady=10)

        main = tk.Frame(self, bg=BG_MAIN)
        main.pack(fill='both', expand=True)

        # Panneau gauche : éditeur (largeur fixe)
        left = tk.Frame(main, bg=BG_MAIN, width=440)
        left.pack(side='left', fill='both', padx=(18, 6), pady=14)
        left.pack_propagate(False)

        # Séparateur vertical
        tk.Frame(main, bg=BG_CARD, width=2).pack(
            side='left', fill='y', pady=14)

        # Panneau droit : aperçu (s'étend avec la fenêtre)
        right = tk.Frame(main, bg=BG_PANEL)
        right.pack(side='left', fill='both', expand=True,
                   padx=(6, 18), pady=14)

        self._build_editor(left)
        self._build_preview_panel(right)
        self._toggle_footer()
        self.after(120, self._refresh_preview)

    # ── Panneau éditeur (gauche) ──────────────────────────────────────

    def _build_editor(self, parent):
        # Boutons en bas
        btn_row = tk.Frame(parent, bg=BG_MAIN)
        btn_row.pack(fill='x', side='bottom', pady=(8, 4))
        tk.Button(
            btn_row, text="Enregistrer", font=FONT_BOLD,
            bg=COL_ACC, fg="white",
            activebackground=BTN_HVR, activeforeground="white",
            relief='flat', padx=18, pady=7, cursor='hand2',
            command=self._save,
        ).pack(side='left')
        tk.Button(
            btn_row, text="Annuler", font=FONT_MAIN,
            bg=BG_CARD, fg=FG_MUTED,
            relief='flat', padx=12, pady=7, cursor='hand2',
            command=self.destroy,
        ).pack(side='left', padx=(10, 0))
        tk.Frame(parent, bg=BG_CARD, height=1).pack(
            fill='x', side='bottom', pady=(0, 2))

        # Nom du modèle
        self._section(parent, "Nom du modèle")
        self._name_var = tk.StringVar(value=self._tpl.name)
        tk.Entry(parent, textvariable=self._name_var, font=FONT_MAIN,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', bd=5
                 ).pack(fill='x', pady=(0, 10))

        # Colonnes
        self._section(parent, "Colonnes du tableau (une par ligne)")

        col_frame = tk.Frame(parent, bg=BG_PANEL)
        col_frame.pack(fill='both', expand=True, pady=(0, 6))

        self._col_listbox = tk.Listbox(
            col_frame, font=FONT_MONO,
            bg=BG_LOG, fg=FG_TEXT,
            selectbackground=COL_ACC, selectforeground="white",
            relief='flat', bd=0, height=6,
        )
        self._col_listbox.pack(side='left', fill='both',
                               expand=True, padx=(8, 0), pady=8)
        for c in self._tpl.columns:
            self._col_listbox.insert('end', c)

        col_btns = tk.Frame(col_frame, bg=BG_PANEL)
        col_btns.pack(side='left', fill='y', padx=8, pady=8)

        for txt, cmd in [
            ("▲ Monter",    self._col_up),
            ("▼ Descendre", self._col_down),
            ("+ Ajouter",        self._col_add),
            ("✕ Retirer",   self._col_remove),
        ]:
            tk.Button(col_btns, text=txt, font=("Segoe UI", 8),
                      bg=BG_CARD, fg=FG_TEXT,
                      activebackground=COL_ACC2,
                      relief='flat', padx=6, pady=4,
                      cursor='hand2', command=cmd,
                      ).pack(fill='x', pady=2)

        # Séparateur de section
        self._section(parent, "Mot-clé de ligne de séparation")
        self._sect_kw_var = tk.StringVar(value=self._tpl.section_keyword)
        tk.Entry(parent, textvariable=self._sect_kw_var, font=FONT_MAIN,
                 bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                 relief='flat', bd=5
                 ).pack(fill='x', pady=(0, 8))

        # Pied de page
        self._section(parent, "Pied de page")

        foot_frame = tk.Frame(parent, bg=BG_PANEL, padx=10, pady=8)
        foot_frame.pack(fill='x', pady=(0, 10))

        self._has_footer_var = tk.BooleanVar(value=self._tpl.has_footer)
        tk.Checkbutton(
            foot_frame, text="Activer le pied de page",
            variable=self._has_footer_var,
            font=FONT_MAIN, bg=BG_PANEL, fg=FG_TEXT,
            selectcolor=BG_LOG, activebackground=BG_PANEL,
            command=self._toggle_footer,
        ).pack(anchor='w')

        self._foot_inner = tk.Frame(foot_frame, bg=BG_PANEL)
        self._foot_inner.pack(fill='x', pady=(6, 0))

        tk.Label(self._foot_inner, text="Étiquette gauche :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_left_var = tk.StringVar(value=self._tpl.footer_left_label)
        tk.Entry(self._foot_inner, textvariable=self._foot_left_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x', pady=(0, 4))

        tk.Label(self._foot_inner,
                 text="Ligne 1 ({PET}, {BORNIER}…) :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_r1_var = tk.StringVar(value=self._tpl.footer_row1_format)
        tk.Entry(self._foot_inner, textvariable=self._foot_r1_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x', pady=(0, 4))

        tk.Label(self._foot_inner,
                 text="Ligne 2 ({NO_PLAN}, {INDICE}, {PAGE}…) :",
                 font=FONT_MAIN, fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x')
        self._foot_r2_var = tk.StringVar(value=self._tpl.footer_row2_format)
        tk.Entry(self._foot_inner, textvariable=self._foot_r2_var,
                 font=FONT_MAIN, bg=BG_LOG, fg=FG_TEXT,
                 insertbackground=FG_TEXT, relief='flat', bd=4,
                 ).pack(fill='x')

        # Rafraîchir l'aperçu à chaque frappe
        for var in (self._foot_left_var, self._foot_r1_var,
                    self._foot_r2_var, self._sect_kw_var):
            var.trace_add('write', lambda *_: self._refresh_preview())

        # Champs personnalisés à extraire du pied de page
        self._section(parent, "Champs du pied à extraire (label → {CLÉ})")
        tk.Label(parent,
                 text="Ex : CABLE : → {CABLE}   TYPE : → {TYPE}",
                 font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_MAIN,
                 anchor='w').pack(fill='x', pady=(0, 2))

        fld_frame = tk.Frame(parent, bg=BG_PANEL)
        fld_frame.pack(fill='x', pady=(0, 6))

        self._fld_listbox = tk.Listbox(
            fld_frame, font=FONT_MONO,
            bg=BG_LOG, fg=FG_TEXT,
            selectbackground=COL_ACC, selectforeground="white",
            relief='flat', bd=0, height=4,
        )
        self._fld_listbox.pack(side='left', fill='both',
                               expand=True, padx=(8, 0), pady=6)
        for fdef in self._tpl.footer_extract_fields:
            lbl = fdef.get('label', '')
            key = fdef.get('key', '')
            self._fld_listbox.insert('end', f"{lbl} → {{{key}}}")

        fld_btns = tk.Frame(fld_frame, bg=BG_PANEL)
        fld_btns.pack(side='left', fill='y', padx=8, pady=6)
        tk.Button(fld_btns, text="+ Ajouter",
                  font=("Segoe UI", 8), bg=BG_CARD, fg=FG_TEXT,
                  activebackground=COL_ACC2, relief='flat',
                  padx=6, pady=4, cursor='hand2',
                  command=self._fld_add,
                  ).pack(fill='x', pady=2)
        tk.Button(fld_btns, text="✕ Retirer",
                  font=("Segoe UI", 8), bg=BG_CARD, fg=FG_TEXT,
                  activebackground="#5a1010", relief='flat',
                  padx=6, pady=4, cursor='hand2',
                  command=self._fld_remove,
                  ).pack(fill='x', pady=2)

    # ── Panneau aperçu (droite) ───────────────────────────────────────

    def _build_preview_panel(self, parent):
        tk.Label(parent, text="Aperçu en temps réel",
                 font=FONT_BOLD, fg=COL_ACC, bg=BG_PANEL,
                 anchor='w').pack(fill='x', pady=(0, 2))
        tk.Label(parent,
                 text="En-tête  ·  10 lignes min  ·  pied de page",
                 font=("Segoe UI", 8), fg=FG_MUTED, bg=BG_PANEL,
                 anchor='w').pack(fill='x', pady=(0, 6))

        cf = tk.Frame(parent, bg=BG_PANEL)
        cf.pack(fill='both', expand=True)

        self._preview_canvas = tk.Canvas(
            cf, bg=BG_LOG, highlightthickness=0
        )
        vsb = ttk.Scrollbar(cf, orient='vertical',
                            command=self._preview_canvas.yview)
        self._preview_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._preview_canvas.pack(side='left', fill='both', expand=True)

        self._preview_canvas.bind(
            '<Configure>', lambda _: self._refresh_preview())

    def _refresh_preview(self, *_):
        """Redessine le tableau d'aperçu à partir des paramètres actuels."""
        if not hasattr(self, '_preview_canvas'):
            return
        c = self._preview_canvas
        c.delete('all')

        cols = [self._col_listbox.get(i)
                for i in range(self._col_listbox.size())]
        cw = max(c.winfo_width() - 4, 220)

        if not cols:
            c.create_text(
                cw // 2, 80,
                text="Ajoutez des colonnes\npour voir l'aperçu",
                fill=FG_MUTED, font=FONT_MAIN, justify='center',
            )
            return

        n = len(cols)
        has_footer = self._has_footer_var.get()
        col_w = (cw - 2) // n
        rh = 22
        x0, y = 1, 4

        # En-tête
        for i, name in enumerate(cols):
            x = x0 + i * col_w
            c.create_rectangle(x, y, x + col_w, y + rh,
                               fill='#2a3f6f', outline='#4a6090')
            c.create_text(x + col_w // 2, y + rh // 2,
                          text=name[:16], fill=FG_TEXT,
                          font=FONT_BOLD, anchor='center')
        y += rh

        # Lignes de données (10 minimum)
        for r in range(10):
            fill = BG_PANEL if r % 2 == 0 else BG_MAIN
            for i in range(n):
                x = x0 + i * col_w
                c.create_rectangle(x, y, x + col_w, y + rh,
                                   fill=fill, outline='#2a4080')
            c.create_text(x0 + 3, y + rh // 2,
                          text=str(r + 1), fill=FG_MUTED,
                          font=("Consolas", 7), anchor='w')
            y += rh

        # Ligne de séparation (exemple)
        kw = self._sect_kw_var.get() or "NOM DU CABLE"
        c.create_rectangle(x0, y, x0 + col_w * n, y + rh,
                           fill='#1a1a30', outline='#3a4a70',
                           dash=(4, 3))
        c.create_text(x0 + 4, y + rh // 2,
                      text=f"  ↳ {kw}", fill=FG_MUTED,
                      font=("Segoe UI", 7, "italic"), anchor='w')
        y += rh

        # Pied de page
        if has_footer:
            lbl = self._foot_left_var.get() or "M  T  I"
            r1 = (self._foot_r1_var.get() or
                  "P.E.T. : {PET}   BORNIER : {BORNIER}")
            r2 = (self._foot_r2_var.get() or
                  "NO PLAN : {NO_PLAN}  |  INDICE : {INDICE}  |  PAGE : {PAGE}")

            _examples = {
                'PET':     'EPEULE',
                'BORNIER': 'B702A',
                'NO_PLAN': 'VD23111 PE 162',
                'INDICE':  '0',
                'PAGE':    '92',
            }
            for i in range(self._fld_listbox.size()):
                import re as _re2
                m2 = _re2.match(r'^(.+?)\s*→\s*\{(.+?)\}$',
                                self._fld_listbox.get(i))
                if m2:
                    _examples.setdefault(m2.group(2).strip(), m2.group(1).strip())
            for key, ex in _examples.items():
                r1 = r1.replace(f'{{{key}}}', ex)
                r2 = r2.replace(f'{{{key}}}', ex)
            import re as _re3
            r1 = _re3.sub(r'\{[A-Z_]+:[^}]*\}', lambda m: m.group(0).split(':')[0][1:] + '}', r1)
            r2 = _re3.sub(r'\{[A-Z_]+:[^}]*\}', lambda m: m.group(0).split(':')[0][1:] + '}', r2)
            for key, ex in _examples.items():
                r1 = r1.replace(f'{{{key}}}', ex)
                r2 = r2.replace(f'{{{key}}}', ex)

            mti_w = col_w
            content_w = col_w * (n - 1)
            ff = '#162040'
            fo = '#4a6090'

            c.create_rectangle(x0, y, x0 + mti_w, y + rh * 2,
                               fill=ff, outline=fo)
            c.create_text(x0 + mti_w // 2, y + rh,
                          text=lbl, fill=FG_TEXT,
                          font=FONT_BOLD, anchor='center')

            c.create_rectangle(x0 + mti_w, y,
                               x0 + mti_w + content_w, y + rh,
                               fill=ff, outline=fo)
            c.create_text(x0 + mti_w + 5, y + rh // 2,
                          text=r1[:60], fill=FG_TEXT,
                          font=("Consolas", 7), anchor='w')

            c.create_rectangle(x0 + mti_w, y + rh,
                               x0 + mti_w + content_w, y + rh * 2,
                               fill=ff, outline=fo)
            c.create_text(x0 + mti_w + 5, y + rh + rh // 2,
                          text=r2[:60], fill=FG_TEXT,
                          font=("Consolas", 7), anchor='w')

            y += rh * 2
        else:
            c.create_text(cw // 2, y + 10,
                          text="(aucun pied de page)",
                          fill=FG_MUTED, font=("Segoe UI", 7, "italic"))
            y += 22

        c.configure(scrollregion=(0, 0, cw, y + 8))

    # ── Helpers UI ────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=FONT_BOLD,
                 fg=COL_ACC, bg=BG_MAIN, anchor='w'
                 ).pack(fill='x', pady=(6, 2))

    def _toggle_footer(self):
        state = 'normal' if self._has_footer_var.get() else 'disabled'
        for w in self._foot_inner.winfo_children():
            try:
                w.configure(state=state)
            except Exception:
                pass
        self._refresh_preview()

    # ── Actions sur les colonnes ──────────────────────────────────────

    def _col_up(self):
        sel = self._col_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self._col_listbox.get(i)
        self._col_listbox.delete(i)
        self._col_listbox.insert(i - 1, val)
        self._col_listbox.selection_set(i - 1)
        self._refresh_preview()

    def _col_down(self):
        sel = self._col_listbox.curselection()
        if not sel or sel[0] >= self._col_listbox.size() - 1:
            return
        i = sel[0]
        val = self._col_listbox.get(i)
        self._col_listbox.delete(i)
        self._col_listbox.insert(i + 1, val)
        self._col_listbox.selection_set(i + 1)
        self._refresh_preview()

    def _col_add(self):
        dlg = _SimpleInput(self, "Nom de la colonne",
                           "Entrez le nom du mot-clé de colonne :")
        self.wait_window(dlg)
        val = dlg.result
        if val:
            self._col_listbox.insert('end', val.upper().strip())
            self._refresh_preview()

    def _col_remove(self):
        sel = self._col_listbox.curselection()
        if sel:
            self._col_listbox.delete(sel[0])
            self._refresh_preview()

    # ── Actions sur les champs de pied ───────────────────────────────

    def _fld_add(self):
        """Ajoute un champ personnalisé : demande le label puis la clé."""
        dlg_lbl = _SimpleInput(self, "Label dans le pied",
                               "Label à rechercher dans le pied\n(ex : CABLE, TYPE) :")
        self.wait_window(dlg_lbl)
        label = dlg_lbl.result.strip()
        if not label:
            return
        dlg_key = _SimpleInput(self, "Clé metadata",
                               "Nom de la clé pour {...} dans le format\n"
                               "(ex : CABLE → {CABLE}) :")
        self.wait_window(dlg_key)
        key = dlg_key.result.strip().upper().replace(' ', '_')
        if not key:
            return
        self._fld_listbox.insert('end', f"{label} → {{{key}}}")
        self._refresh_preview()

    def _fld_remove(self):
        sel = self._fld_listbox.curselection()
        if sel:
            self._fld_listbox.delete(sel[0])
            self._refresh_preview()

    def _get_footer_extract_fields(self) -> list:
        """Reconstruit la liste footer_extract_fields depuis le listbox."""
        import re as _re
        fields = []
        for i in range(self._fld_listbox.size()):
            entry = self._fld_listbox.get(i)
            # Accepte aussi bien → (unicode) que -> (ASCII)
            m = _re.match(r'^(.+?)\s*(?:→|->)\s*\{(.+?)\}$', entry)
            if m:
                fields.append({"label": m.group(1).strip(),
                               "key":   m.group(2).strip()})
        return fields

    # ── Sauvegarde ───────────────────────────────────────────────────

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Nom manquant",
                                   "Veuillez saisir un nom pour le modèle.",
                                   parent=self)
            return
        cols = [self._col_listbox.get(i)
                for i in range(self._col_listbox.size())]
        if not cols:
            messagebox.showwarning("Colonnes manquantes",
                                   "Ajoutez au moins une colonne.",
                                   parent=self)
            return

        fld_fields = self._get_footer_extract_fields()
        detect_kw = list(dict.fromkeys(
            [f['label'] for f in fld_fields] +
            self._tpl.footer_detect_keywords
        ))

        tpl = TableTemplate(
            name=name,
            columns=cols,
            section_keyword=self._sect_kw_var.get().strip(),
            has_footer=self._has_footer_var.get(),
            footer_left_label=self._foot_left_var.get(),
            footer_row1_format=self._foot_r1_var.get(),
            footer_row2_format=self._foot_r2_var.get(),
            footer_detect_keywords=detect_kw,
            footer_mti_tokens=self._tpl.footer_mti_tokens,
            footer_extract_fields=fld_fields,
            col_widths={c: 20.0 for c in cols},
            description="",
        )
        self._mgr.add_or_update(tpl)
        self._saved = True
        self._saved_name = name
        self.destroy()


class _SimpleInput(tk.Toplevel):
    """Mini-boîte de dialogue pour saisir une valeur texte.

    Paramètres :
        title   — titre de la fenêtre
        prompt  — texte affiché au-dessus du champ  (positional ou kwarg)
        label   — alias pour prompt (kwarg uniquement)
        default — valeur pré-remplie dans le champ
    """

    def __init__(self, parent, title="", prompt="", label=None, default=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("380x130")
        self.resizable(False, False)
        self.configure(bg=BG_MAIN)
        self.grab_set()
        self.result = ""

        text = label if label is not None else prompt
        tk.Label(self, text=text, font=FONT_MAIN,
                 fg=FG_TEXT, bg=BG_MAIN, wraplength=350,
                 justify='left').pack(padx=14, pady=(14, 4), anchor='w')
        self._var = tk.StringVar(value=default)
        e = tk.Entry(self, textvariable=self._var, font=FONT_MAIN,
                     bg=BG_LOG, fg=FG_TEXT, insertbackground=FG_TEXT,
                     relief='flat', bd=5)
        e.pack(fill='x', padx=14)
        e.focus_set()
        e.icursor('end')
        e.bind("<Return>", lambda _: self._ok())

        tk.Button(self, text="OK", font=FONT_BOLD,
                  bg=COL_ACC, fg="white", relief='flat',
                  padx=16, pady=4, cursor='hand2',
                  command=self._ok).pack(pady=10)

    def _ok(self):
        self.result = self._var.get().strip()
        self.destroy()


# ── Point d'entrée ────────────────────────────────────────────────────

if __name__ == '__main__':
    app = TriosSeconverterApp()
    app.mainloop()
