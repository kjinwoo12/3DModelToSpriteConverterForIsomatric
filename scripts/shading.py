# 스프라이트용 단순 셰이딩: 텍스처 색을 발광(평평한 애니풍) + 디퓨즈(약한 음영)로 섞고, 알파는 유지.
# 뒷면(얇은 옷 안쪽)은 어둡게 칠해 구멍처럼 보이지 않게 한다.
# render8.py가 import해서 쓴다. Blender 안에서만 동작.
import math
import bpy


def apply(emission=0.6, world=0.6, sun=2.0, flat_prefixes=(), backface_rgb=(0.05, 0.045, 0.06)):
    """flat_prefixes: 이름이 이걸로 시작하는 머티리얼은 뒷면을 어둡게 하지 않음(두께를 준 옷·신발 등)"""
    sc = bpy.context.scene
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        nt = m.node_tree
        b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not b or not out:
            continue
        e = nt.nodes.new('ShaderNodeEmission')
        d = nt.nodes.new('ShaderNodeBsdfDiffuse')
        add = nt.nodes.new('ShaderNodeAddShader')
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'
        if flat_prefixes and m.name.startswith(tuple(flat_prefixes)):
            mx.inputs['Factor'].default_value = 0.0
        else:
            nt.links.new(geo.outputs['Backfacing'], mx.inputs['Factor'])
            mx.inputs[7].default_value = (*backface_rgb, 1)
        bc = b.inputs['Base Color']
        if bc.links:
            nt.links.new(bc.links[0].from_socket, mx.inputs[6])
        else:
            mx.inputs[6].default_value = bc.default_value
        nt.links.new(mx.outputs[2], e.inputs[0]); nt.links.new(mx.outputs[2], d.inputs[0])
        e.inputs[1].default_value = emission
        nt.links.new(e.outputs[0], add.inputs[0]); nt.links.new(d.outputs[0], add.inputs[1])
        mix = nt.nodes.new('ShaderNodeMixShader'); tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        al = b.inputs['Alpha']
        if al.links:
            nt.links.new(al.links[0].from_socket, mix.inputs[0])
        else:
            mix.inputs[0].default_value = al.default_value
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(add.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
    sc.render.film_transparent = True
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new('sprite_world'); sc.world = w; w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[1].default_value = world
    s = bpy.data.objects.new('sprite_sun', bpy.data.lights.new('sprite_sun', 'SUN'))
    sc.collection.objects.link(s); s.data.energy = sun
    s.rotation_euler = (math.radians(50), 0, math.radians(-30))


def add_rim(energy=3.0, color=(0.55, 0.95, 1.0)):
    """뒤쪽 윗편에서 비추는 색 테두리 조명. energy 0이면 만들지 않음"""
    if energy <= 0:
        return None
    sc = bpy.context.scene
    rim = bpy.data.objects.new('sprite_rim', bpy.data.lights.new('sprite_rim', 'SUN'))
    sc.collection.objects.link(rim)
    rim.data.energy = energy; rim.data.color = color
    rim.rotation_euler = (math.radians(-60), 0, math.radians(20))
    return rim
