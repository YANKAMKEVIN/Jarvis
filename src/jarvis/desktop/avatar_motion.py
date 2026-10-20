"""Deterministic, bounded 2D choreography; no audio capture or session ownership."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MotionProfile:
    description: str
    accent: str
    effect: str
    speed: float = 1.0


PROFILES = {
    'nova_bot': MotionProfile('Lévitation douce et balancement du robot', '#85e7ff', 'thruster'),
    'neo_guide': MotionProfile('Inclinaison attentive et balises discrètes', '#c4b5ff', 'beacons', .8),
    'kitsune': MotionProfile('Flottement félin et lucioles ascendantes', '#b9dfff', 'fireflies', .9),
    'digital_avatar': MotionProfile('Respiration holographique et balayage vertical', '#bda6ff', 'scan', .85),
    'synth_companion': MotionProfile('Respiration mécanique et segments synchronisés', '#b4e5ed', 'segments', .7),
    'holo_face': MotionProfile('Dérive holographique et lignes de transmission', '#75ddff', 'transmission', .65),
    'orbital_atlas': MotionProfile('Orbites elliptiques et satellites', '#edc57b', 'satellites', .75),
    'aurora_light': MotionProfile('Ondulation lumineuse et voiles boréaux', '#d9f5f2', 'curtains', .65),
    'liquid_chrome': MotionProfile('Déformation fluide et reflets mobiles', '#c3d5ff', 'reflections', .8),
    'vector_grid': MotionProfile('Respiration de la grille et paquets de données', '#68ecc7', 'packets', .9),
    'prism_core': MotionProfile('Oscillation cristalline et rayons réfractés', '#d7b2ff', 'rays', .7),
    'event_horizon': MotionProfile('Précession lente et arcs d’accrétion', '#9acfff', 'accretion', .55),
    'solar_forge': MotionProfile('Pulsation solaire et éjections de braises', '#ffc678', 'embers', 1.1),
    'command_deck': MotionProfile('Stabilisation du noyau et repères de navigation', '#8bdcff', 'reticle', .6),
    'neural_entity': MotionProfile('Contraction organique et connexions neuronales', '#cca4ff', 'synapses', .85),
    'arc_reactor': MotionProfile('Pulsation du réacteur et couronne de charge', '#81e5ff', 'charge', 1.2),
}


@dataclass(frozen=True)
class MotionFrame:
    x: float = 0
    y: float = 0
    rotation: float = 0
    sx: float = 1
    sy: float = 1


def sample_motion(appearance, phase, energy, state, enabled=True):
    """Normalized translation, degrees, scale. A still frame is exactly neutral."""
    if not enabled:
        return MotionFrame()
    t = phase * 2.75 * PROFILES[appearance].speed
    e = max(0, min(1, energy))
    # States alter the choreography without sudden large displacements.
    gain = {'off': .65, 'muted': .4, 'error': .45, 'success': 1.1}.get(state, 1)
    a, b = math.sin(t), math.sin(t * 2)
    pulse = e * .018
    poses = {
        'nova_bot': (a*.004, -b*.015, a*1.1, pulse, pulse),
        'neo_guide': (a*.003, b*.005, math.sin(t*.7)*1.9, pulse*.4, pulse*.6),
        'kitsune': (a*.012, -math.sin(t*1.5)*.012, b*.8, pulse*.6, pulse),
        'digital_avatar': (0, a*.004, 0, b*.004+ pulse, -b*.004+pulse),
        'synth_companion': (0, b*.003, a*.35, a*.006+pulse*.5, a*.009+pulse),
        'holo_face': (a*.007, math.cos(t*.8)*.005, a*.6, b*.003+pulse*.3, pulse*.3),
        'orbital_atlas': (0, a*.004, a*2.3, pulse*.4, pulse*.4),
        'aurora_light': (a*.006, b*.008, a*1.6, b*.012+pulse, -b*.009+pulse),
        'liquid_chrome': (b*.004, a*.004, b*1.2, a*.018+pulse, -a*.014+pulse),
        'vector_grid': (0, a*.003, 0, b*.006+pulse*.5, b*.006+pulse*.5),
        'prism_core': (0, -a*.012, b*2.8, a*.005+pulse, pulse),
        'event_horizon': (0, b*.003, a*1.8, a*.006+pulse*.5, -a*.01+pulse*.5),
        'solar_forge': (0, 0, a*.5, b*.012+pulse, b*.012+pulse),
        'command_deck': (a*.002, b*.003, a*.7, pulse*.3, pulse*.3),
        'neural_entity': (a*.006, b*.006, a*1.4, b*.014+pulse, -a*.012+pulse),
        'arc_reactor': (0, 0, b*.4, a*.008+pulse*1.2, a*.008+pulse*1.2),
    }
    x, y, rotation, sx, sy = poses[appearance]
    return MotionFrame(x*gain, y*gain, rotation*gain, 1+sx*gain, 1+sy*gain)


def paint_details(p, appearance, phase, energy, state, side):
    """Small decorative marks outside the artwork; bounded cost at all sizes."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QPen
    profile = PROFILES[appearance]
    t = phase * 2.75 * profile.speed
    e = max(0, min(1, energy))
    color = QColor('#f0a7ba' if state == 'error' else '#8af0be' if state == 'success' else profile.accent)
    color.setAlpha(round(65 + 65*e))
    p.save()
    p.scale(side, side)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(color, .002))
    effect = profile.effect
    def dot(x, y, radius=.004):
        p.setBrush(color)
        p.drawEllipse(QPointF(x, y), radius, radius)
        p.setBrush(Qt.BrushStyle.NoBrush)
    def arc(radius, angle, span):
        p.drawArc(QRectF(-radius, -radius, radius*2, radius*2), round(angle*16), round(span*16))
    if effect == 'thruster':
        for i in range(3):
            w = .045 + i*.022 + math.sin(t*2)*.004
            p.drawEllipse(QRectF(-w, .385+i*.018, w*2, .008))
    elif effect == 'beacons':
        for sign in (-1, 1):
            dot(sign*.36, math.sin(t)*.015)
            p.drawLine(QPointF(sign*.36, -.05), QPointF(sign*.36, .05))
    elif effect == 'fireflies':
        for i in range(7):
            u = (t*.08+i/7) % 1
            dot(math.sin(i*2.4+t*.6)*.36, .4-u*.76, .002+math.sin(u*math.pi)*.002)
    elif effect == 'scan':
        y = math.sin(t*.7)*.32
        for sign in (-1, 1):
            p.drawLine(QPointF(sign*.33,y), QPointF(sign*.41,y))
            dot(sign*.39, y+.018, .002)
    elif effect == 'segments':
        for i in range(4):
            arc(.43, i*90+math.sin(t)*4, 12+6*(1+math.sin(t*2+i)))
    elif effect == 'transmission':
        for i in range(4):
            y = -.27+i*.17
            x = .34 + math.sin(t+i)*.012
            p.drawLine(QPointF(x,y), QPointF(x+.035,y))
            p.drawLine(QPointF(-x,y+.04), QPointF(-x-.02,y+.04))
    elif effect == 'satellites':
        p.drawEllipse(QRectF(-.44,-.15,.88,.3))
        for i in range(3):
            a = t*.4+i*2.094
            dot(math.cos(a)*.44,math.sin(a)*.15,.005)
    elif effect == 'curtains':
        for i in range(3):
            arc(.37+i*.025, 35+math.sin(t+i)*12, 26)
            arc(.37+i*.025, 215+math.sin(t+i)*12, 26)
    elif effect == 'reflections':
        for i in range(2):
            arc(.4+i*.03, t*14+i*180, 28)
    elif effect == 'packets':
        for i in range(4):
            u = (t*.1+i*.25)%1
            x,y = (-.4+u*.8, -.37 if i%2 else .37)
            p.drawRect(QRectF(x-.005,y-.005,.01,.01))
    elif effect == 'rays':
        for i in range(6):
            a = i*math.pi/3+math.sin(t)*.04
            r = .36+(1+math.sin(t+i))*.01
            p.drawLine(QPointF(math.cos(a)*r,math.sin(a)*r), QPointF(math.cos(a)*(r+.035),math.sin(a)*(r+.035)))
    elif effect == 'accretion':
        p.save()
        p.scale(1,.36)
        for i in range(3):
            arc(.41+i*.018, t*18+i*120, 55)
        p.restore()
    elif effect == 'embers':
        for i in range(9):
            u = (t*.12+i/9)%1
            a = i*2.399
            r = .33+u*.11
            dot(math.cos(a)*r,math.sin(a)*r,.003*(1-u)+.001)
    elif effect == 'reticle':
        for i in range(4):
            p.save()
            p.rotate(i*90)
            d = .39+math.sin(t)*.005
            p.drawLine(QPointF(d,-.035),QPointF(d,.035))
            p.drawLine(QPointF(d,0),QPointF(d+.025,0))
            p.restore()
        arc(.45, t*9, 15)
    elif effect == 'synapses':
        nodes = [QPointF(math.cos(i*1.256)*(.37+.012*math.sin(t+i)),math.sin(i*1.256)*(.37+.012*math.sin(t+i))) for i in range(5)]
        for i, node in enumerate(nodes):
            dot(node.x(),node.y(),.004)
            if math.sin(t+i) > .35:
                p.drawLine(node,nodes[(i+2)%5])
    elif effect == 'charge':
        for i in range(8):
            arc(.41, i*45+t*10, 14+e*10)
        arc(.445, -t*18, 25)
    p.restore()
