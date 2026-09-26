"""Explicit curated reference designs for reproducible offline demonstrations."""
from .models import Design, Part


def p(id,name,group,route,shape,size,position,**kw):
    return Part(id=id,name=name,group=group,route=route,shape=shape,size=size,position=position,**kw)


def reference(family):
    parts=[]
    if family=='phone':
        title='模块化手持终端'
        parts=[
            p('case','打印后壳','外壳与支撑','print','shell',[86,164,24],[0,0,0],wall=2,color='#d9e2e9'),
            p('display','5寸触摸显示模组','人机界面','catalog','box',[72,130,5],[0,0,11],catalog_ref='Waveshare 5inch DSI LCD (D)',color='#172c44'),
            p('carrier','电路承载板 / 定位孔后加工','外壳与支撑','machine','box',[70,145,3],[0,0,-5],material='aluminum',color='#b2bdc4',purpose='钻削模块安装孔；几何文件目前为毛坯'),
            p('compute','计算模块','计算与通信','catalog','box',[55,40,5],[0,40,0],catalog_ref='Raspberry Pi Compute Module 4',color='#447965'),
            p('modem','蜂窝通信模块','计算与通信','catalog','box',[30,30,5],[19,-4,0],catalog_ref='Quectel EG25-G',color='#799c8a'),
            p('battery','锂电池单元','电源','catalog','box',[42,65,8],[-12,-32,0],catalog_ref='LiPo 404265 3.7V (supplier qualification pending)',color='#464f61'),
            p('camera','摄像模组','人机界面','catalog','box',[25,24,9],[24,63,2],catalog_ref='Raspberry Pi Camera Module 3',color='#252e38'),
            p('speaker','扬声器','人机界面','catalog','box',[15,10,4],[20,-65,1],catalog_ref='8 ohm 1 W 15x10 mm speaker (supplier pending)',color='#343c47'),
            p('button','侧面按键','人机界面','print','box',[4,20,5],[44,35,4],color='#8d9aab'),
            p('cover','电池固定盖','外壳与支撑','print','box',[46,70,1.4],[-12,-32,5],color='#b2c8d0'),
        ]
        for i,(x,y) in enumerate([(-34,-65),(34,-65),(-34,65),(34,65)]):
            parts.append(p(f'standoff-{i}',f'安装柱 {i+1}','外壳与支撑','print','tube',[6,6,12],[x,y,0],wall=1.5,color='#d8a964'))
    elif family=='car':
        title='模块化电动车 / 概念结构'
        parts=[p('body','轻量化车身壳体','车身','print','car_body',[4200,1750,1200],[0,0,950],wall=12,color='#d9e1e8'),
            p('chassis','底盘安装平台毛坯','底盘','machine','box',[3100,1400,65],[0,0,450],material='aluminum',color='#5a6574'),
            p('battery','电池包包络','动力与电源','catalog','box',[1600,1100,200],[0,0,280],catalog_ref='EV traction battery pack, 400 V (model qualification pending)',color='#486877'),
            p('drive','电驱动总成包络','动力与电源','catalog','box',[600,800,350],[1200,0,500],catalog_ref='Dana TM4 SUMO LD (variant qualification pending)',color='#658d87'),
            p('seat-left','座椅骨架','乘员舱','print','shell',[500,480,480],[100,-430,850],wall=15,color='#ac9274'),
            p('seat-right','座椅骨架','乘员舱','print','shell',[500,480,480],[100,430,850],wall=15,color='#ac9274')]
        for i,(x,y) in enumerate([(-1300,-875),(-1300,875),(1300,-875),(1300,875)]):
            parts.append(p(f'wheel-{i}',f'轮胎轮辋总成 {i+1}','行走机构','catalog','tube',[620,620,210],[x,y,330],rotation=[90,0,0],wall=110,catalog_ref='205/55 R16 tire + 6.5Jx16 rim (supplier pending)',color='#26323d'))
            parts.append(p(f'bracket-{i}',f'悬架安装座 {i+1}','底盘','machine','box',[160,180,110],[x,y*.72,490],material='aluminum',color='#91a0ad'))
    else:
        title='固定翼飞机 / 概念结构'
        parts=[p('fuselage','分段薄壁机身','机身','print','fuselage',[6200,900,1100],[0,0,300],wall=10,color='#dce4eb'),
            p('spar','机翼连接梁 / 配合孔后加工','机翼','machine','box',[220,6800,120],[0,0,400],material='aluminum',color='#bd9960'),
            p('wing-left','左机翼蒙皮','机翼','print','wing',[1550,3300,85],[-150,-2050,500],wall=3,color='#becdd8'),
            p('wing-right','右机翼蒙皮','机翼','print','wing',[1550,3300,85],[-150,2050,500],rotation=[0,0,180],wall=3,color='#becdd8'),
            p('tail','水平尾翼','尾翼','print','wing',[800,2400,55],[-2550,0,600],color='#bccad5'),
            p('fin','垂直尾翼','尾翼','print','wing',[850,1050,45],[-2500,0,1100],rotation=[90,0,0],color='#8ba5b9'),
            p('engine','动力装置包络','动力与航电','catalog','cylinder',[650,650,750],[2600,0,300],rotation=[0,90,0],catalog_ref='Rotax 912 series (variant/integration pending)',color='#526f79'),
            p('avionics','飞控计算单元包络','动力与航电','catalog','box',[160,100,70],[700,0,450],catalog_ref='CubePilot Cube Orange+ (integration pending)',color='#d79d64')]
        for i in range(5):
            for side in [-1,1]:
                parts.append(p(f'rib-{side+1}-{i}',f'{"左" if side<0 else "右"}翼肋 {i+1}','机翼','print','box',[1100,18,68],[-150,side*(700+i*600),500],color='#8caeb9'))
    return Design(title=title,family=family,summary='可复现的参考架构。具名部件、制造毛坯及设备展开用于演示规划与证据闭环。',
        observations=[{'text':'此方案为人工编写的参考架构，用于离线回放，不是本次图片识别结果。','source':'selected'}],
        assumptions=['给定不限成型尺寸、可执行指定材料工艺的打印资源；能力属于外部前提。',
            '目录件几何为布局包络，型号适配、采购可得性和物理性能仍需验证。',
            '定制件为概念几何；后加工零件当前导出的是毛坯，工装精度与刀路待验证。'],
        requirements=['保留该类产品的主要功能分组与装配层级','所有制造分支提供采购、打印或显式后加工路线','展开一轮加工设备并检查先后依赖'],
        parts=parts,unresolved=['结构、热、电与运动性能未进行实物验证','目录件接口与供应商资料需逐项核实','打印支撑、局部壁厚及加工刀路仍需工艺验证'])


def equipment_parts(workpieces=None):
    """A one-generation gantry concept sized to the declared machining blanks.

    This is a parameterized equipment proposal, not a qualified CNC machine.
    Long axes use purchased rack sections, avoiding a fictional infinite screw.
    """
    blanks=workpieces or []
    x=max([p.size[0] for p in blanks]+[140.0]);y=max([p.size[1] for p in blanks]+[160.0]);z=max([p.size[2] for p in blanks]+[25.0])
    margin=max(80,min(x,y)*.15);travel_x=x+margin;travel_y=y+margin
    width=travel_x+2*margin;length=travel_y+2*margin;clearance=z+max(120,min(x,y)*.12)
    beam=max(60,min(300,width*.06));bed=max(25,min(150,length*.025));top=clearance+bed+beam
    common={'purpose':'设备概念部件；承载、精度、装配和供应商接口尚待验证。'}
    parts=[
      p('cell-bed','打印机床底座','加工设备 · 结构','print','box',[width,length,bed],[0,0,0],material='steel',color='#7892a7',**common),
      p('cell-bridge','打印龙门横梁','加工设备 · 结构','print','box',[width,beam,beam],[0,0,top],material='steel',color='#879eae',**common),
      p('cell-carriage','打印横向滑座','加工设备 · 运动','print','shell',[beam*1.4,beam*1.3,beam],[0,-beam,top],wall=max(4,beam*.1),material='aluminum',color='#aec3ce',**common),
      p('cell-fixture','打印工件定位夹具','加工设备 · 工装','print','shell',[x+margin,y+margin,max(20,margin*.25)],[0,0,bed/2+max(20,margin*.25)/2],wall=5,material='aluminum',color='#d5ae6e',**common),
      p('cell-xrail','X 轴标准导轨包络','加工设备 · 运动','catalog','box',[travel_x,25,25],[0,-beam*.6,top],catalog_ref='HIWIN HGW25 linear guide family; length/section joints pending',color='#c8d7db',**common),
      p('cell-zrail','Z 轴标准导轨包络','加工设备 · 运动','catalog','box',[25,25,clearance*.7],[0,-beam*1.4,top-clearance*.25],catalog_ref='HIWIN HGW25 linear guide family; length/accuracy pending',color='#c8d7db',**common),
      p('cell-spindle','ER20 主轴采购候选','加工设备 · 主轴','catalog','cylinder',[80,80,180],[0,-beam*1.7,top-clearance*.5],catalog_ref='ER20 80 mm spindle assembly; power/runout qualification pending',color='#5b877a',**common),
      p('cell-controller','运动控制器包络','加工设备 · 电控','catalog','box',[140,100,40],[width*.3,-length*.4,bed/2+30],catalog_ref='Mesa 7i96S Ethernet motion controller; LinuxCNC host external',color='#40566a',**common),
      p('cell-drivers','标准电机驱动器套装包络','加工设备 · 电控','catalog','box',[180,100,60],[width*.3,length*.4,bed/2+40],catalog_ref='Leadshine DM860T drivers; current and motor matching pending',color='#516879',**common),
      p('cell-fasteners','导轨与结构紧固件包络','加工设备 · 装配','catalog','box',[80,60,20],[-width*.3,-length*.4,bed/2+20],catalog_ref='ISO 4762 M8/M12 bolts and ISO 4032 nuts; lengths pending',color='#b4c3ca',**common),
    ]
    for side in [-1,1]:
      label='左' if side<0 else '右';sid='left' if side<0 else 'right'
      parts += [p('cell-column-'+sid,label+'打印龙门立柱','加工设备 · 结构','print','box',[beam,beam,clearance],[side*(width-beam)/2,0,bed+clearance/2],material='steel',color='#879eae',**common),
        p('cell-yrail-'+sid,label+'纵向导轨','加工设备 · 运动','catalog','box',[25,travel_y,25],[side*(width-beam)/2,0,bed/2+20],catalog_ref='HIWIN HGW25 guide sections; segment alignment pending',color='#c8d7db',**common),
        p('cell-yrack-'+sid,label+'标准齿条与小齿轮包络','加工设备 · 运动','catalog','box',[20,travel_y,20],[side*(width-beam)/2+35,0,bed/2+20],catalog_ref='Module 2 steel rack sections + mating pinion; supplier pending',color='#a8bbc5',**common)]
    for axis,pos in [('x',[width*.35,-beam,top]),('y',[-width*.45,0,bed+80]),('z',[0,-beam*1.4,top+80])]:
      parts.append(p('cell-motor-'+axis,axis.upper()+' 轴标准步进电机','加工设备 · 运动','catalog','box',[86,86,100],pos,catalog_ref='NEMA 34 stepper motor; torque/inertia qualification pending',color='#405466',**common))
    parts.append(p('cell-xz-drive','X/Z 标准传动组件包络','加工设备 · 运动','catalog','box',[50,50,clearance*.7],[beam,-beam*1.4,top-clearance*.25],catalog_ref='SFU2005 screw/nut for Z; module 2 rack for X; couplings pending',color='#a8bbc5',**common))
    return parts
