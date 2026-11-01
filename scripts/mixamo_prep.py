# 3D 모델을 Mixamo 오토리거에 올릴 수 있는 FBX로 만든다. Blender 안에서 실행.
#
#   blender -b -P scripts/mixamo_prep.py -- --in models/hero/hero.glb --out models/hero/hero_for_mixamo.fbx
#
# 하는 일
#  - 뼈대 제거(현재 자세를 메시에 굳히고 버텍스 그룹·셰이프 키 삭제): Mixamo가 새로 리깅한다
#  - 언릿/발광 머티리얼(VRM 등)을 Principled + 텍스처로 바꿈: FBX에 텍스처가 실려 Mixamo 미리보기에 색이 보인다
#  - 텍스처를 PNG로 풀어 FBX에 내장
#  - 선택: 한 겹짜리 옷 메시에 두께(Mixamo·게임 엔진은 뒷면을 그리지 않음)
#
# 모델별 개조(색 바꾸기, 옷 추가 등)는 먼저 따로 해서 .blend/.glb로 저장한 뒤 이 스크립트에 넣는다.
import argparse, os, sys

import bpy
import bmesh  # bpy 다음에 import


def parse():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='mixamo_prep.py', description='모델 → Mixamo 업로드용 FBX(뼈대 없음, 텍스처 내장)')
    p.add_argument('--in', dest='src', required=True, help='.glb/.gltf/.fbx/.obj/.blend (VRM은 확장자를 .glb로 바꿔서)')
    p.add_argument('--out', required=True, help='출력 FBX 경로')
    p.add_argument('--solidify', action='append', default=[], metavar='PREFIX=THICKNESS',
                   help='이름이 PREFIX로 시작하는 메시에 두께(m) 부여, 구멍 난(한 겹) 메시만 (예: Coat_=0.008)')
    p.add_argument('--drop', action='append', default=[], metavar='PREFIX', help='이름이 PREFIX로 시작하는 오브젝트 삭제 (여러 번)')
    p.add_argument('--turn', type=float, default=0, help='Z축으로 돌릴 각도(도). 정면이 -Y(Blender 앞)를 보게. VRM/VRoid는 180')
    return p.parse_args(argv)


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.blend':
        bpy.ops.wm.open_mainfile(filepath=path)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f'지원하지 않는 형식: {ext}')


def open_edges(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    n = sum(1 for e in bm.edges if not e.is_manifold); bm.free(); return n


def solidify(rules):
    for o in [o for o in bpy.data.objects if o.type == 'MESH']:
        th = next((t for pre, t in rules if o.name.startswith(pre)), None)
        if th is None or not open_edges(o):
            continue
        bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(o.data); bm.free()
        m = o.modifiers.new('thick', 'SOLIDIFY'); m.thickness = th; m.offset = -1; m.use_rim = True; m.use_even_offset = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_move_to_index(modifier='thick', index=0)
        bpy.ops.object.modifier_apply(modifier='thick')
        print('THICK', o.name, th)


def to_principled(tex_dir):
    os.makedirs(tex_dir, exist_ok=True)
    for im in bpy.data.images:
        if im.size[0] == 0:
            continue
        p = os.path.join(tex_dir, bpy.path.clean_name(im.name) + '.png')
        im.file_format = 'PNG'; im.save(filepath=p)
        if im.packed_file:
            im.unpack(method='REMOVE')
        im.filepath = p
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        tex = next((n for n in nt.nodes if n.type == 'TEX_IMAGE'), None)
        if tex is None or any(n.type == 'BSDF_PRINCIPLED' for n in nt.nodes):
            continue
        img = tex.image; nt.nodes.clear()
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = img
        b = nt.nodes.new('ShaderNodeBsdfPrincipled'); o = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(t.outputs['Color'], b.inputs['Base Color']); nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
        nt.links.new(b.outputs[0], o.inputs[0])
        print('MAT', m.name, '→ Principled')


def strip_rig():
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    for o in meshes:
        bpy.context.view_layer.objects.active = o
        if o.data.shape_keys:
            o.shape_key_clear()
        for m in list(o.modifiers):
            if m.type == 'ARMATURE':
                bpy.ops.object.modifier_apply(modifier=m.name)
        mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
        o.vertex_groups.clear()
    for o in [o for o in bpy.data.objects if o.type != 'MESH']:
        bpy.data.objects.remove(o)
    return meshes


def main():
    a = parse()
    load(os.path.abspath(a.src))
    for pre in a.drop:
        for o in [o for o in bpy.data.objects if o.name.startswith(pre)]:
            bpy.data.objects.remove(o)
    solidify([(r.split('=')[0], float(r.split('=')[1])) for r in a.solidify])
    out = os.path.abspath(a.out); os.makedirs(os.path.dirname(out), exist_ok=True)
    to_principled(os.path.join(os.path.dirname(out), 'textures'))
    meshes = strip_rig()
    if a.turn:
        import math
        from mathutils import Matrix
        R = Matrix.Rotation(math.radians(a.turn), 4, 'Z')
        for o in meshes:
            o.data.transform(R @ o.matrix_world); o.matrix_world = Matrix.Identity(4)
    bpy.ops.export_scene.fbx(filepath=out, path_mode='COPY', embed_textures=True, object_types={'MESH'})
    print('EXPORTED', out, [o.name for o in meshes])


main()
