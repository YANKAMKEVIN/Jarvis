"""Optional original vector humanoids with actual shoulder/elbow/hip/knee joints.

The approved raster appearances remain untouched. This is a drawn 2D mode,
not a claim that the original bust images have acquired a 3D skeleton.
"""
import math
from PySide6.QtCore import QPointF,QRectF,Qt
from PySide6.QtGui import QColor,QPainterPath,QPen,QLinearGradient

RIG_IDS=frozenset({'nova_bot','neo_guide','digital_avatar','synth_companion','holo_face'})
PALETTES={
 'nova_bot':('#e9edf1','#e3b664','#152e42','#67deff'),
 'neo_guide':('#245782','#9b604a','#523029','#e7ba81'),
 'digital_avatar':('#443c86','#c3a0d0','#291d51','#b7f7ff'),
 'synth_companion':('#c7e0df','#97b1c2','#133743','#9bffff'),
 'holo_face':('#215b7c','#5596b9','#102f54','#79edff'),
}


def endpoint(origin,length,angle):
    return QPointF(origin.x()+math.sin(angle)*length,origin.y()+math.cos(angle)*length)


def pose(phase,dancing=False,state='off',wave=False):
    beat=phase*6 if not dancing else phase*2*math.pi*2
    amount=1 if dancing else .09
    return {'bounce':(-.022*abs(math.sin(beat)) if dancing else .003*math.sin(beat)),
            'arms':(-.4+amount*.65*math.sin(beat),.4+amount*.65*math.sin(beat+math.pi)),
            'knees':(.1+amount*.65*max(0,math.sin(beat)),.1+amount*.65*max(0,-math.sin(beat))),
            'hips':(-amount*.3*math.sin(beat),amount*.3*math.sin(beat)),
            'head':(.07*math.sin(beat/2) if dancing else .015*math.sin(beat)),
            'wave':wave,'waiting':state=='waiting'}


def paint_rig(p,appearance,side,phase,state,gaze=(0,0),dancing=False,wave=False):
    if appearance not in RIG_IDS:return False
    body,skin,hair,light=PALETTES[appearance]
    motion=pose(phase,dancing,state,wave);bounce=motion['bounce']
    p.save();p.scale(side,side);p.translate(0,bounce)
    def pen(color,width):return QPen(QColor(color),width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin)
    def capsule(a,b,width,color):
        p.setPen(pen('#102333',width+.012));p.drawLine(a,b);p.setPen(pen(color,width));p.drawLine(a,b)
    # A softly grounded shadow makes alternating knee bends read as footsteps.
    p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(40,105,136,75));p.drawEllipse(QRectF(-.16,.415-bounce,.32,.025))
    for i,sign in enumerate((-1,1)):
        hip=QPointF(sign*.053,.18);knee=endpoint(hip,.11,motion['hips'][i])
        foot=endpoint(knee,.12,motion['hips'][i]-sign*motion['knees'][i])
        capsule(hip,knee,.055,body);capsule(knee,foot,.043,body)
        p.setPen(pen(hair,.035));p.drawLine(foot+QPointF(-.018,0),foot+QPointF(.027,0))
        p.setPen(pen(light,.008));p.drawEllipse(knee,.016,.016)
    # Torso is a separate articulated segment, with shoulders and hip anchors.
    torso=QPainterPath();torso.moveTo(-.095,-.025);torso.quadTo(0,-.06,.095,-.025)
    torso.lineTo(.072,.19);torso.quadTo(0,.215,-.072,.19);torso.closeSubpath()
    gradient=QLinearGradient(-.10,0,.10,.2);gradient.setColorAt(0,QColor(body).lighter(120));gradient.setColorAt(1,QColor(body).darker(125))
    p.setPen(pen(hair,.008));p.setBrush(gradient);p.drawPath(torso)
    p.setPen(pen(light,.009));p.drawLine(QPointF(-.057,.025),QPointF(.057,.025))
    p.setBrush(QColor(light));p.drawEllipse(QPointF(0,.085),.023,.023)
    for i,sign in enumerate((-1,1)):
        shoulder=QPointF(sign*.10,-.015);angle=motion['arms'][i]
        elbow_angle=angle-sign*(1.25 if dancing else .25)
        if motion['wave'] and sign==1:angle=2.0+.16*math.sin(phase*18);elbow_angle=2.8+.3*math.sin(phase*18)
        if motion['waiting']:angle=sign*.85;elbow_angle=sign*2.2
        elbow=endpoint(shoulder,.105,angle);hand=endpoint(elbow,.10,elbow_angle)
        capsule(shoulder,elbow,.046,body);capsule(elbow,hand,.038,body)
        p.setPen(pen(hair,.005));p.setBrush(QColor(skin));p.drawEllipse(hand,.025,.028)
        p.setBrush(QColor(light));p.drawEllipse(elbow,.014,.014)
    # Neck and head have their own transform; the eyes follow the pointer.
    p.setPen(pen(skin,.047));p.drawLine(QPointF(0,-.022),QPointF(0,-.075))
    p.save();p.translate(0,-.16);p.rotate(math.degrees(motion['head']))
    robot=appearance in {'nova_bot','synth_companion','holo_face'}
    p.setPen(pen(hair,.009));p.setBrush(QColor(skin if not robot else body))
    p.drawRoundedRect(QRectF(-.125,-.11,.25,.21),.07,.07)
    if robot:
        p.setBrush(QColor(hair));p.drawRoundedRect(QRectF(-.105,-.085,.21,.15),.045,.045)
        p.setPen(pen(light,.009));p.drawArc(QRectF(-.11,-.09,.22,.16),0,180*16)
    else:
        p.setBrush(QColor(hair));p.setPen(Qt.PenStyle.NoPen)
        for x,y,radius in ((-.09,-.09,.04),(-.05,-.117,.04),(0,-.12,.045),(.05,-.115,.04),(.09,-.09,.04)):
            p.drawEllipse(QPointF(x,y),radius,radius)
    blink=math.sin(phase*1.7)>.997
    gx,gy=(max(-1,min(1,gaze[0]))*.012,max(-1,min(1,gaze[1]))*.009)
    for sign in (-1,1):
        eye=QPointF(sign*.047+gx,-.015+gy)
        p.setPen(pen(light if robot else '#172c3e',.012));p.setBrush(QColor(light if robot else '#172c3e'))
        if blink:p.drawLine(eye-QPointF(.012,0),eye+QPointF(.012,0))
        else:p.drawEllipse(eye,.013,.018)
    p.setPen(pen(light if robot else hair,.008));p.setBrush(Qt.BrushStyle.NoBrush)
    mouth=QPainterPath();mouth.moveTo(-.025,.036)
    mouth.quadTo(0,.06 if state in {'success','speaking'} or dancing or wave else .04,.025,.036)
    p.drawPath(mouth)
    if state=='thinking':
        p.setPen(pen(light,.008));p.drawLine(QPointF(-.07,-.055),QPointF(-.025,-.064))
    if appearance=='nova_bot':
        p.setPen(pen(light,.01));p.drawLine(QPointF(0,-.11),QPointF(0,-.145));p.setBrush(QColor(light));p.drawEllipse(QPointF(0,-.15),.015,.015)
    p.restore();p.restore();return True
