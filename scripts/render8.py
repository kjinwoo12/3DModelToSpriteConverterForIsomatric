# 애니메이션 FBX(Mixamo 등, 스킨 포함)를 쿼터뷰 정사영으로 8방향 렌더한다. Blender 안에서 실행.
#
#   blender -b -P scripts/render8.py -- --out work/hero_frames --clips-dir models/hero/anims
#   blender -b -P scripts/render8.py -- --out work/hero_frames --clip idle=idle.fbx --clip run=run.fbx --res 192
#   blender -b -P scripts/render8.py -- --out work/rogue_frames --clip "idle=Rogue.fbx#Idle" --clip "run=Rogue.fbx#Running_A"
#   blender -b -P scripts/render8.py -- --list-actions Rogue.fbx      (FBX 안의 동작 목록)
#
# 출력: {out}/{동작}_{방향}_{번호}.png (방향 S,SW,W,NW,N,NE,E,SE) + {out}/meta.json
# 이어서 pixelize.py로 도트 시트를 만든다. 자세한 사용법은 저장소 README.md.
import argparse, glob, json, math, os, sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shading  # noqa: E402

DIRS = ['S', 'SW', 'W', 'NW', 'N', 'NE', 'E', 'SE']


def parse():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='render8.py', description='애니메이션 FBX → 8방향 PNG 프레임')
    p.add_argument('--out', help='프레임 PNG를 쓸 폴더')
    p.add_argument('--clip', action='append', default=[], metavar='NAME=FILE.fbx[#ACTION]',
                   help='동작 이름=FBX 경로 (여러 번). 동작이 여러 개 든 FBX는 #액션이름으로 고름 (예: idle=Rogue.fbx#Idle)')
    p.add_argument('--clips-dir', help='이 폴더의 *.fbx 전부. 동작 이름 = 파일 이름(소문자, 공백→_)')
    p.add_argument('--res', type=int, default=192, help='렌더 크기(px, 정사각). 칸 크기의 2배 권장 (기본 192)')
    p.add_argument('--step', type=int, default=1, help='몇 프레임마다 찍을지. 30fps 원본을 10fps로 = 3 (기본 1)')
    p.add_argument('--elev', type=float, default=30, help='카메라 고각(도). 게임 쿼터뷰와 맞출 것 (기본 30)')
    p.add_argument('--face', type=float, default=0, help='모델이 S(카메라 쪽)를 보도록 돌릴 각도(도). Mixamo는 0, VRM 직접 임포트는 180')
    p.add_argument('--ortho', type=float, default=3.2, help='정사영 화면 폭(m). 클수록 캐릭터가 작게 찍힘 (기본 3.2)')
    p.add_argument('--target-z', type=float, default=0.75, help='카메라가 겨누는 높이(m). 키의 절반쯤 (기본 0.75)')
    p.add_argument('--samples', type=int, default=8, help='Cycles 샘플 수 (기본 8)')
    p.add_argument('--rim', type=float, default=3, help='테두리 조명 세기, 0이면 끔 (기본 3)')
    p.add_argument('--rim-color', default='0.55,0.95,1.0', help='테두리 조명 색 r,g,b 0~1')
    p.add_argument('--emission', type=float, default=0.6, help='평평한 발광 비율. 높을수록 음영이 약함 (기본 0.6)')
    p.add_argument('--flat-prefix', action='append', default=[], help='뒷면을 어둡게 하지 않을 머티리얼 이름 접두어 (여러 번)')
    p.add_argument('--lockz', default='', help='높이 이동도 없앨 동작 이름, 쉼표 구분 (예: climb,wallrun)')
    p.add_argument('--root-bone', default='', help='제자리 고정 기준 뼈. 기본: 이름이 Hips로 끝나는 뼈')
    p.add_argument('--keep-root-motion', action='store_true', help='제자리 고정을 하지 않음')
    p.add_argument('--hide', action='append', default=[], metavar='PREFIX', help='이름이 PREFIX로 시작하는 오브젝트를 렌더에서 숨김 (여러 번, 예: 무기)')
    p.add_argument('--gpu', action='store_true', help='Cycles를 GPU로 렌더')
    p.add_argument('--preview', metavar='FILE.png', help='첫 동작의 첫 프레임을 S방향으로 한 장만 찍어 이 경로에 저장 (값 맞추기용)')
    p.add_argument('--list-actions', metavar='FILE.fbx', help='FBX 안의 동작 목록만 출력하고 끝냄')
    a = p.parse_args(argv)
    if a.list_actions:
        return a
    clips = [c.split('=', 1) for c in a.clip]
    if a.clips_dir:
        for f in sorted(glob.glob(os.path.join(a.clips_dir, '*.fbx'))):
            clips.append((os.path.splitext(os.path.basename(f))[0].lower().replace(' ', '_'), f))
    if not clips:
        p.error('--clip 또는 --clips-dir가 필요합니다')
    if not a.out and not a.preview:
        p.error('--out이 필요합니다')
    a.clips = clips
    a.lockz = {s for s in a.lockz.split(',') if s}
    a.rim_color = tuple(float(x) for x in a.rim_color.split(','))
    return a


def fix_alpha():
    # Mixamo FBX는 Alpha가 빈 텍스처에 연결돼 투명해지는 경우가 있음 → 베이스 텍스처 알파로 다시 연결
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not b:
            continue
        for l in list(b.inputs['Alpha'].links):
            nt.links.remove(l)
        bc = b.inputs['Base Color'].links
        if bc and bc[0].from_node.type == 'TEX_IMAGE':
            nt.links.new(bc[0].from_node.outputs['Alpha'], b.inputs['Alpha'])
        else:
            b.inputs['Alpha'].default_value = 1


def find_root(arm, name):
    if name:
        return arm.pose.bones[name]
    return next((pb for pb in arm.pose.bones if pb.name.split(':')[-1].lower().endswith('hips')),
                next(pb for pb in arm.pose.bones if pb.parent is None))


def action_name(act):
    return act.name.split('|')[-1]  # FBX 임포트는 '아마추어|동작' 이름을 붙임


def set_action(arm, want):
    act = next((x for x in bpy.data.actions if x.name == want or action_name(x) == want), None)
    if act is None:
        raise SystemExit(f'동작 "{want}"이 없습니다. 있는 것: {", ".join(action_name(x) for x in bpy.data.actions)}')
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if hasattr(ad, 'action_slot') and ad.action_slot is None and len(act.slots):  # 4.4+ 슬롯 액션
        ad.action_slot = act.slots[0]


def list_actions(fbx):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(fbx))
    for act in bpy.data.actions:
        f0, f1 = map(int, act.frame_range)
        print(f'ACTION {action_name(act)}	{f0}	{f1}', flush=True)


def render_clip(a, name, fbx, preview=None):
    fbx, want = fbx.rsplit('#', 1) if '#' in fbx else (fbx, '')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.abspath(fbx))
    bpy.ops.file.find_missing_files(directory=os.path.dirname(os.path.abspath(fbx)))  # 텍스처 경로가 다른 PC 기준일 때
    for o in bpy.data.objects:
        if a.hide and o.name.startswith(tuple(a.hide)):
            o.hide_render = True
    fix_alpha()
    shading.apply(emission=a.emission, flat_prefixes=a.flat_prefix)
    sc = bpy.context.scene
    sc.cycles.samples = a.samples
    if a.gpu:
        sc.cycles.device = 'GPU'
    sc.render.resolution_x = sc.render.resolution_y = a.res
    sc.render.filter_size = 0.01  # 픽셀화할 때 가장자리가 흐리지 않게
    sc.render.image_settings.color_mode = 'RGBA'
    shading.add_rim(a.rim, a.rim_color)

    arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
    if want and arm:
        set_action(arm, want)
    act = arm.animation_data.action if arm and arm.animation_data else None
    f0, f1 = map(int, act.frame_range) if act else (1, 1)

    # 회전 받침: 모든 최상위 오브젝트를 여기에 붙이고 Z로 돌려 8방향을 찍는다
    pivot = bpy.data.objects.new('pivot', None); sc.collection.objects.link(pivot)
    tops = [o for o in bpy.data.objects if o.parent is None and o.type in ('ARMATURE', 'MESH', 'EMPTY') and o is not pivot]

    # 제자리 고정: 루트 뼈의 월드 XY(+lockz 동작은 Z) 이동을 아마추어 위치로 상쇄
    if arm and act and not a.keep_root_motion:
        root = find_root(arm, a.root_bone); base = arm.location.copy()
        sc.frame_set(f0); h0 = arm.matrix_world @ root.head
        offs = {}
        for f in range(f0, f1 + 1):
            sc.frame_set(f); h = arm.matrix_world @ root.head
            offs[f] = Vector((-h.x, -h.y, (h0.z - h.z) if name in a.lockz else 0))  # 골반을 매 프레임 원점 위에
        for f, d in offs.items():
            arm.location = base + d; arm.keyframe_insert('location', frame=f)
    for o in tops:
        o.parent = pivot

    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = a.ortho
    el = math.radians(a.elev); target = Vector((0, 0, a.target_z))
    cam.location = target + Vector((0, -20 * math.cos(el), 20 * math.sin(el)))
    cam.rotation_euler = (math.radians(90) - el, 0, 0)

    if preview:
        pivot.rotation_euler[2] = math.radians(a.face)
        sc.frame_set(f0); sc.render.filepath = os.path.abspath(preview)
        bpy.ops.render.render(write_still=True)
        print('PREVIEW', preview, flush=True)
        return None

    frames = list(range(f0, f1 + 1, a.step))
    total = len(DIRS) * len(frames)
    for di, d in enumerate(DIRS):
        pivot.rotation_euler[2] = math.radians(a.face - 45 * di)
        for fi, f in enumerate(frames):
            sc.frame_set(f)
            sc.render.filepath = os.path.join(os.path.abspath(a.out), f'{name}_{d}_{fi:02d}.png')
            bpy.ops.render.render(write_still=True)
            print(f'PROGRESS {name} {di * len(frames) + fi + 1}/{total}', flush=True)
    print('CLIP', name, len(frames), flush=True)
    return {'frames': len(frames), 'step': a.step, 'source_fps': sc.render.fps}


def main():
    a = parse()
    if a.list_actions:
        return list_actions(a.list_actions)
    if a.preview:
        return render_clip(a, *a.clips[0], preview=a.preview)
    os.makedirs(a.out, exist_ok=True)
    meta_path = os.path.join(a.out, 'meta.json')
    meta = json.load(open(meta_path, encoding='utf-8')) if os.path.exists(meta_path) else {}
    for name, fbx in a.clips:
        for d in DIRS:
            for old in glob.glob(os.path.join(a.out, f'{name}_{d}_[0-9][0-9].png')):
                os.remove(old)  # 같은 동작을 다시 구울 때 이전 프레임이 섞이지 않게
        meta[name] = render_clip(a, name, fbx)
        json.dump(meta, open(meta_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('DONE', meta)


main()
