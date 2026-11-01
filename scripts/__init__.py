# Blender 애드온: 3D 뷰 N패널(Sprite8 탭)에서 mixamo_prep → render8 → pixelize를 실행한다.
# 각 단계는 같은 폴더의 스크립트를 백그라운드 Blender로 돌린다. 지금 열린 씬은 건드리지 않고, 렌더 중에도 UI가 멈추지 않는다.
import os, queue, subprocess, sys, tempfile, threading

import bpy
from bpy.props import (BoolProperty, CollectionProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       PointerProperty, StringProperty)

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW_IMAGE = 'Sprite8 Preview'


def ap(path):
    return os.path.normpath(bpy.path.abspath(path)) if path else ''


def split_list(s):
    return [x.strip() for x in s.replace(';', ',').split(',') if x.strip()]


def clip_name(s):
    return s.strip().lower().replace(' ', '_')


def to_hex(c):
    return ''.join(f'{round(max(0, min(1, v)) * 255):02x}' for v in c)


# ---- 백그라운드 작업 ----------------------------------------------------------

class Job:
    current = None

    def __init__(self, title, script, args, on_done=None):
        self.title, self.on_done = title, on_done
        self.lines, self.progress, self.status, self.error = [], 0.0, '시작 중', ''
        self.q = queue.Queue()
        cmd = [bpy.app.binary_path, '-b', '--factory-startup', '-P', os.path.join(HERE, script), '--', *args]
        print('Sprite8:', subprocess.list2cmdline(cmd))
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, creationflags=flags)
        threading.Thread(target=self._read, daemon=True).start()
        Job.current = self
        bpy.app.timers.register(self._tick, first_interval=0.2)

    def _read(self):
        for raw in self.proc.stdout:
            self.q.put(raw.decode('utf-8', 'replace').rstrip())
        self.q.put(None)

    @property
    def running(self):
        return self.proc.poll() is None or not self.q.empty()

    def _tick(self):
        ended = False
        while True:
            try:
                line = self.q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                ended = True; break
            self.lines.append(line)
            if line.startswith('PROGRESS '):
                _, what, frac = line.split(' ', 2)
                n, t = map(int, frac.split('/'))
                self.progress = n / max(1, t); self.status = f'{what} {n}/{t}'
            elif line.startswith(('CLIP ', 'PREVIEW', 'EXPORTED', 'ACTION ')) or line.endswith('방향'):
                self.status = line[:80]
            elif 'Error' in line or 'error:' in line or line.startswith('SystemExit'):
                self.error = line
        redraw()
        if not ended:
            return 0.2
        self.proc.wait()
        if self.proc.returncode == 0:
            self.status, self.progress, self.error = '완료', 1.0, ''
            if self.on_done:
                self.on_done(self)
        else:
            tail = [l for l in self.lines if l.strip()][-6:]
            self.error = self.error or (tail[-1] if tail else f'종료 코드 {self.proc.returncode}')
            self.status = '실패'
            print('Sprite8 실패:\n' + '\n'.join(tail))
        redraw()
        return None

    def cancel(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        self.status = '취소됨'


def redraw():
    wm = bpy.context.window_manager
    for w in wm.windows:
        for area in w.screen.areas:
            if area.type in ('VIEW_3D', 'IMAGE_EDITOR'):
                area.tag_redraw()


def busy(op):
    if Job.current and Job.current.running:
        op.report({'WARNING'}, '이미 작업이 돌고 있습니다')
        return True
    return False


# ---- 설정 --------------------------------------------------------------------

class ClipItem(bpy.types.PropertyGroup):
    enabled: BoolProperty(name='렌더', default=True)
    name: StringProperty(name='동작 이름', description='시트·프레임 파일 이름. 게임에서 쓸 동작 이름')
    file: StringProperty(name='FBX', subtype='FILE_PATH', description='스킨이 포함된 동작 FBX')
    action: StringProperty(name='액션', description='FBX에 동작이 여러 개 들어 있으면 고를 액션 이름. 비우면 FBX 기본 동작')


def scan_clips(s, _context=None):
    d = ap(s.clips_dir)
    if not os.path.isdir(d):
        return
    have = {(ap(c.file), c.action) for c in s.clips}
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if f.lower().endswith('.fbx') and (p, '') not in have:
            c = s.clips.add(); c.name = clip_name(os.path.splitext(f)[0]); c.file = p


class Settings(bpy.types.PropertyGroup):
    # 1. Mixamo 준비
    prep_use_current: BoolProperty(name='지금 연 .blend 사용', description='저장된 현재 파일을 입력으로 씀(먼저 저장할 것)')
    prep_src: StringProperty(name='모델', subtype='FILE_PATH', description='.glb/.gltf/.fbx/.obj/.blend (VRM은 확장자를 .glb로)')
    prep_out: StringProperty(name='출력 FBX', subtype='FILE_PATH', description='Mixamo에 올릴 FBX 경로')
    prep_solidify: StringProperty(name='두께', description='이름접두어=두께(m), 쉼표 구분. 예: Coat_=0.008')
    prep_drop: StringProperty(name='삭제', description='이름이 이걸로 시작하는 오브젝트 삭제, 쉼표 구분')
    prep_turn: FloatProperty(name='Z 회전', default=0, description='정면이 -Y를 보게 돌릴 각도(도). VRM/VRoid는 180')

    # 2. 8방향 렌더
    clips_dir: StringProperty(name='동작 폴더', subtype='DIR_PATH', update=scan_clips,
                              description='이 폴더의 FBX를 동작 목록에 추가(동작 이름 = 파일 이름)')
    actions_fbx: StringProperty(name='여러 동작 FBX', subtype='FILE_PATH',
                                description='동작이 여러 개 든 FBX. "액션 읽기"로 목록에 추가')
    clips: CollectionProperty(type=ClipItem)
    clips_index: IntProperty()
    frames_dir: StringProperty(name='프레임 폴더', subtype='DIR_PATH', description='8방향 PNG 프레임을 쓸 폴더')
    res: IntProperty(name='렌더 크기', default=192, min=16, max=2048, description='px, 정사각. 칸 크기의 2배 권장')
    step: IntProperty(name='프레임 간격', default=1, min=1, description='몇 프레임마다 찍을지. 30fps 원본을 10fps로 = 3')
    elev: FloatProperty(name='고각', default=30, min=0, max=90, description='카메라 고각(도). 30 ≈ 2:1 아이소메트릭')
    face: FloatProperty(name='정면 보정', default=0, description='모델이 S(카메라 쪽)를 보도록 돌릴 각도(도). Mixamo는 0')
    ortho: FloatProperty(name='화면 폭', default=3.2, min=0.01, description='정사영 화면 폭(m). 클수록 캐릭터가 작게 찍힘')
    target_z: FloatProperty(name='겨눔 높이', default=0.75, description='카메라가 겨누는 높이(m). 키의 절반쯤')
    samples: IntProperty(name='샘플', default=8, min=1, description='Cycles 샘플 수')
    rim: FloatProperty(name='테두리 조명', default=3, min=0, description='0이면 끔')
    rim_color: FloatVectorProperty(name='테두리 색', subtype='COLOR', size=3, min=0, max=1, default=(0.55, 0.95, 1.0))
    emission: FloatProperty(name='평평함', default=0.6, min=0, description='발광 비율. 높을수록 음영이 약함')
    flat_prefix: StringProperty(name='뒷면 유지', description='뒷면을 어둡게 하지 않을 머티리얼 접두어, 쉼표 구분')
    hide: StringProperty(name='숨길 오브젝트', description='이름이 이걸로 시작하는 오브젝트를 렌더에서 숨김, 쉼표 구분(무기 등)')
    lockz: StringProperty(name='높이 고정 동작', description='높이 이동도 없앨 동작 이름, 쉼표 구분 (예: climb,wallrun)')
    root_bone: StringProperty(name='기준 뼈', description='제자리 고정 기준 뼈. 비우면 이름이 Hips로 끝나는 뼈')
    keep_root_motion: BoolProperty(name='제자리 고정 안 함')
    gpu: BoolProperty(name='GPU 렌더')
    show_render_more: BoolProperty(name='세부 옵션')

    # 3. 도트 시트
    sheets_dir: StringProperty(name='시트 폴더', subtype='DIR_PATH', description='시트 PNG·sprites.json을 쓸 폴더')
    cell: IntProperty(name='칸 크기', default=96, min=8, max=1024, description='px. 렌더 크기의 절반 권장')
    alpha: IntProperty(name='알파 컷', default=110, min=0, max=255, description='이 값보다 불투명한 픽셀만 남김')
    color_step: IntProperty(name='색 단계', default=8, min=1, max=128, description='8 = 채널당 32단계, 1 = 줄이지 않음')
    use_outline: BoolProperty(name='외곽선', default=True)
    outline_color: FloatVectorProperty(name='외곽선 색', subtype='COLOR_GAMMA', size=3, min=0, max=1,
                                       default=(0x12 / 255, 0x10 / 255, 0x1a / 255))
    only: StringProperty(name='이 동작만', description='쉼표 구분. 비우면 프레임 폴더의 동작 전부')
    rename: StringProperty(name='이름 바꾸기', description='프레임이름=시트이름, 쉼표 구분. 예: dash=rolling')
    gif: BoolProperty(name='preview.gif', default=True)
    gif_scale: IntProperty(name='GIF 배율', default=2, min=1, max=8)
    art_json: BoolProperty(name='art.json', description='엔진에서 읽을 애니메이션 메타데이터. 이미 있으면 이번 동작만 갱신')
    fps: IntProperty(name='fps', default=10, min=1)
    loop: StringProperty(name='반복 동작', default='idle,run,air,climb,walk,sprint')
    ppu: FloatProperty(name='Pixels/Unit', default=40, min=0.01)
    pivot_y: FloatProperty(name='발 위치', default=0.25, min=0, max=1, description='칸 아래에서 발끝까지 비율')
    height: FloatProperty(name='UI 높이', default=1.25, description='머리 위 UI 높이(m)')

    def render_args(self):
        a = ['--res', self.res, '--step', self.step, '--elev', self.elev, '--face', self.face, '--ortho', self.ortho,
             '--target-z', self.target_z, '--samples', self.samples, '--rim', self.rim,
             '--rim-color', ','.join(f'{v:.4f}' for v in self.rim_color), '--emission', self.emission]
        for p in split_list(self.flat_prefix):
            a += ['--flat-prefix', p]
        for p in split_list(self.hide):
            a += ['--hide', p]
        if self.lockz.strip():
            a += ['--lockz', ','.join(split_list(self.lockz))]
        if self.root_bone.strip():
            a += ['--root-bone', self.root_bone.strip()]
        if self.keep_root_motion:
            a.append('--keep-root-motion')
        if self.gpu:
            a.append('--gpu')
        return [str(x) for x in a]

    def clip_args(self, only_active=False):
        items = [self.clips[self.clips_index]] if only_active and self.clips else [c for c in self.clips if c.enabled]
        a = []
        for c in items:
            if c.name.strip() and c.file:
                a += ['--clip', f'{clip_name(c.name)}={ap(c.file)}' + (f'#{c.action}' if c.action.strip() else '')]
        return a

    def pixelize_args(self):
        a = [ap(self.frames_dir), ap(self.sheets_dir), '--cell', self.cell, '--alpha', self.alpha,
             '--color-step', self.color_step, '--outline', to_hex(self.outline_color) if self.use_outline else 'none',
             '--fps', self.fps, '--gif-scale', self.gif_scale]
        if self.only.strip():
            a += ['--only', ','.join(split_list(self.only))]
        for r in split_list(self.rename):
            a += ['--rename', r]
        if not self.gif:
            a.append('--no-gif')
        if self.art_json:
            a += ['--art-json', '--loop', ','.join(split_list(self.loop)), '--ppu', self.ppu,
                  '--pivot-y', self.pivot_y, '--height', self.height]
        return [str(x) for x in a]


# ---- 연산자 -------------------------------------------------------------------

class SPRITE8_OT_prep(bpy.types.Operator):
    bl_idname = 'sprite8.prep'
    bl_label = 'Mixamo용 FBX 만들기'
    bl_description = '뼈대 제거·텍스처 내장·(선택) 두께 → Mixamo 업로드용 FBX'

    def execute(self, context):
        s = context.scene.sprite8
        if busy(self):
            return {'CANCELLED'}
        if s.prep_use_current:
            if not bpy.data.filepath:
                self.report({'ERROR'}, '현재 파일을 먼저 저장하세요'); return {'CANCELLED'}
            if bpy.data.is_dirty:
                self.report({'WARNING'}, '저장 안 된 변경은 반영되지 않습니다(마지막 저장본 사용)')
            src = bpy.data.filepath
        else:
            src = ap(s.prep_src)
        if not os.path.isfile(src) or not s.prep_out:
            self.report({'ERROR'}, '모델과 출력 FBX 경로를 정하세요'); return {'CANCELLED'}
        out = ap(s.prep_out)
        if not out.lower().endswith('.fbx'):
            out += '.fbx'
        args = ['--in', src, '--out', out, '--turn', str(s.prep_turn)]
        for r in split_list(s.prep_solidify):
            args += ['--solidify', r]
        for r in split_list(s.prep_drop):
            args += ['--drop', r]
        Job('Mixamo 준비', 'mixamo_prep.py', args)
        return {'FINISHED'}


class SPRITE8_OT_scan(bpy.types.Operator):
    bl_idname = 'sprite8.scan'
    bl_label = '폴더 다시 읽기'
    bl_description = '동작 폴더의 FBX 중 목록에 없는 것을 추가'

    def execute(self, context):
        scan_clips(context.scene.sprite8)
        return {'FINISHED'}


class SPRITE8_OT_read_actions(bpy.types.Operator):
    bl_idname = 'sprite8.read_actions'
    bl_label = 'FBX 액션 읽기'
    bl_description = 'FBX 안의 동작(액션)을 읽어 목록에 추가. 추가된 줄은 기본으로 꺼져 있음'

    def execute(self, context):
        s = context.scene.sprite8
        f = ap(s.actions_fbx)
        if busy(self):
            return {'CANCELLED'}
        if not os.path.isfile(f):
            self.report({'ERROR'}, 'FBX 파일을 고르세요'); return {'CANCELLED'}
        scene_name = context.scene.name

        def done(job):
            sc = bpy.data.scenes.get(scene_name)
            if not sc:
                return
            st = sc.sprite8; have = {(ap(c.file), c.action) for c in st.clips}; n = 0
            for line in job.lines:
                if line.startswith('ACTION '):
                    name = line[7:].split('\t')[0]
                    if (f, name) in have:
                        continue
                    c = st.clips.add(); c.name = clip_name(name); c.file = f; c.action = name; c.enabled = False; n += 1
            job.status = f'액션 {n}개 추가(체크해서 고르세요)'

        Job('액션 읽기', 'render8.py', ['--list-actions', f], done)
        return {'FINISHED'}


class SPRITE8_OT_clip_add(bpy.types.Operator):
    bl_idname = 'sprite8.clip_add'
    bl_label = '동작 추가'

    def execute(self, context):
        s = context.scene.sprite8
        c = s.clips.add(); c.name = f'clip{len(s.clips)}'; s.clips_index = len(s.clips) - 1
        return {'FINISHED'}


class SPRITE8_OT_clip_remove(bpy.types.Operator):
    bl_idname = 'sprite8.clip_remove'
    bl_label = '동작 빼기'

    def execute(self, context):
        s = context.scene.sprite8
        if s.clips:
            s.clips.remove(s.clips_index); s.clips_index = max(0, min(s.clips_index, len(s.clips) - 1))
        return {'FINISHED'}


class SPRITE8_OT_clip_toggle(bpy.types.Operator):
    bl_idname = 'sprite8.clip_toggle'
    bl_label = '전체 선택/해제'

    def execute(self, context):
        s = context.scene.sprite8
        on = not all(c.enabled for c in s.clips)
        for c in s.clips:
            c.enabled = on
        return {'FINISHED'}


def show_image(path):
    img = bpy.data.images.get(PREVIEW_IMAGE)
    if img:
        img.filepath = path; img.reload()
    else:
        img = bpy.data.images.load(path); img.name = PREVIEW_IMAGE
    shown = False
    for w in bpy.context.window_manager.windows:
        for area in w.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = img; shown = True
    return shown


class SPRITE8_OT_preview(bpy.types.Operator):
    bl_idname = 'sprite8.preview'
    bl_label = '미리보기 한 장'
    bl_description = '선택한 동작의 첫 프레임을 S방향으로 한 장만 찍음. 각도·크기 맞출 때 사용(이미지 에디터에 표시)'

    def execute(self, context):
        s = context.scene.sprite8
        if busy(self):
            return {'CANCELLED'}
        clip = s.clip_args(only_active=True)
        if not clip:
            self.report({'ERROR'}, '동작을 하나 고르세요'); return {'CANCELLED'}
        path = os.path.join(tempfile.gettempdir(), 'sprite8_preview.png')
        def done(job):
            if not show_image(path):
                job.status = f'이미지 에디터에서 "{PREVIEW_IMAGE}"를 여세요'

        Job('미리보기', 'render8.py', ['--preview', path, *clip, *s.render_args()], done)
        return {'FINISHED'}


def start_render(s, then=None):
    """문제가 있으면 이유를 돌려줌"""
    clips = s.clip_args()
    if not clips:
        return '렌더할 동작을 체크하세요'
    if not s.frames_dir:
        return '프레임 폴더를 정하세요'
    Job('8방향 렌더', 'render8.py', ['--out', ap(s.frames_dir), *clips, *s.render_args()], then)


def start_pixelize(s):
    if not os.path.isdir(ap(s.frames_dir)) or not s.sheets_dir:
        return '프레임 폴더와 시트 폴더를 정하세요'
    sheets = ap(s.sheets_dir)

    def done(job):
        names = next((l[5:].split(', ') for l in job.lines if l.startswith('DONE ')), [])
        job.status = '완료: ' + ', '.join(names)
        if names:  # Blender는 GIF를 못 읽으므로 첫 시트를 보여 줌. 움직임은 preview.gif로 확인
            show_image(os.path.join(sheets, names[0] + '.png'))

    Job('도트 시트', 'pixelize.py', s.pixelize_args(), done)


def run(op, err):
    if err:
        op.report({'ERROR'}, err); return {'CANCELLED'}
    return {'FINISHED'}


class SPRITE8_OT_render(bpy.types.Operator):
    bl_idname = 'sprite8.render'
    bl_label = '8방향 렌더'
    bl_description = '체크한 동작을 8방향 PNG 프레임으로 렌더. 같은 동작의 이전 프레임은 지우고 새로 씀'

    def execute(self, context):
        if busy(self):
            return {'CANCELLED'}
        return run(self, start_render(context.scene.sprite8))


class SPRITE8_OT_pixelize(bpy.types.Operator):
    bl_idname = 'sprite8.pixelize'
    bl_label = '도트 시트 만들기'
    bl_description = '프레임 폴더의 PNG를 축소·색 단계·외곽선 처리해 시트, sprites.json, preview.gif로'

    def execute(self, context):
        if busy(self):
            return {'CANCELLED'}
        return run(self, start_pixelize(context.scene.sprite8))


class SPRITE8_OT_render_and_pixelize(bpy.types.Operator):
    bl_idname = 'sprite8.render_and_pixelize'
    bl_label = '렌더 + 시트'
    bl_description = '8방향 렌더가 끝나면 바로 도트 시트까지 만듦'

    def execute(self, context):
        s = context.scene.sprite8
        if busy(self):
            return {'CANCELLED'}
        if not s.sheets_dir:
            self.report({'ERROR'}, '시트 폴더를 정하세요'); return {'CANCELLED'}
        scene_name = context.scene.name

        def then(job):
            err = start_pixelize(bpy.data.scenes[scene_name].sprite8)
            if err:
                job.error = err

        return run(self, start_render(s, then))


class SPRITE8_OT_cancel(bpy.types.Operator):
    bl_idname = 'sprite8.cancel'
    bl_label = '취소'

    def execute(self, context):
        if Job.current:
            Job.current.cancel()
        return {'FINISHED'}


class SPRITE8_OT_open(bpy.types.Operator):
    bl_idname = 'sprite8.open'
    bl_label = '폴더 열기'
    path: StringProperty()

    def execute(self, context):
        p = ap(self.path)
        if os.path.isfile(p):
            p = os.path.dirname(p)
        if not os.path.isdir(p):
            self.report({'ERROR'}, '폴더가 아직 없습니다'); return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=p)
        return {'FINISHED'}


# ---- UI --------------------------------------------------------------------------

class SPRITE8_UL_clips(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, 'enabled', text='')
        row.prop(item, 'name', text='', emboss=False)
        row.label(text=item.action or os.path.basename(item.file) or '(파일 없음)')


class Panel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Sprite8'


class SPRITE8_PT_main(Panel, bpy.types.Panel):
    bl_label = '8방향 스프라이트'

    def draw(self, context):
        job = Job.current
        col = self.layout.column()
        if not job:
            col.label(text='1 → 2 → 3 순서로 실행', icon='INFO')
            return
        if job.running:
            col.progress(factor=job.progress, type='BAR', text=f'{job.title}: {job.status}')
            col.operator('sprite8.cancel', icon='CANCEL')
        else:
            col.label(text=f'{job.title}: {job.status}', icon='ERROR' if job.error else 'CHECKMARK')
        if job.error:
            col.label(text=job.error[:120], icon='ERROR')
            col.label(text='자세한 로그: 창 > 시스템 콘솔 토글')


class SPRITE8_PT_prep(Panel, bpy.types.Panel):
    bl_label = '1. Mixamo 업로드용 FBX'
    bl_parent_id = 'SPRITE8_PT_main'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.sprite8; col = self.layout.column()
        col.prop(s, 'prep_use_current')
        if not s.prep_use_current:
            col.prop(s, 'prep_src')
        col.prop(s, 'prep_out')
        col.prop(s, 'prep_turn')
        col.prop(s, 'prep_solidify')
        col.prop(s, 'prep_drop')
        row = col.row(align=True)
        row.operator('sprite8.prep', icon='EXPORT')
        row.operator('sprite8.open', text='', icon='FILE_FOLDER').path = s.prep_out
        col.label(text='다음: mixamo.com에서 리깅 후', icon='INFO')
        col.label(text='동작을 With Skin FBX로 받기')


class SPRITE8_PT_render(Panel, bpy.types.Panel):
    bl_label = '2. 8방향 렌더'
    bl_parent_id = 'SPRITE8_PT_main'

    def draw(self, context):
        s = context.scene.sprite8; col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, 'clips_dir')
        row.operator('sprite8.scan', text='', icon='FILE_REFRESH')
        col.prop(s, 'actions_fbx')
        col.operator('sprite8.read_actions', icon='ACTION')
        row = col.row()
        row.template_list('SPRITE8_UL_clips', '', s, 'clips', s, 'clips_index', rows=4)
        side = row.column(align=True)
        side.operator('sprite8.clip_add', text='', icon='ADD')
        side.operator('sprite8.clip_remove', text='', icon='REMOVE')
        side.separator()
        side.operator('sprite8.clip_toggle', text='', icon='CHECKBOX_HLT')
        if s.clips and 0 <= s.clips_index < len(s.clips):
            c = s.clips[s.clips_index]; box = col.box().column()
            box.prop(c, 'file'); box.prop(c, 'action')
        col.separator()
        col.prop(s, 'frames_dir')
        col.prop(s, 'res'); col.prop(s, 'step')
        col.prop(s, 'elev'); col.prop(s, 'ortho'); col.prop(s, 'target_z'); col.prop(s, 'face')
        col.prop(s, 'hide')
        col.prop(s, 'show_render_more', icon='TRIA_DOWN' if s.show_render_more else 'TRIA_RIGHT', emboss=False)
        if s.show_render_more:
            box = col.box().column()
            for k in ('emission', 'rim', 'rim_color', 'flat_prefix', 'lockz', 'root_bone', 'keep_root_motion',
                      'samples', 'gpu'):
                box.prop(s, k)
        row = col.row(align=True)
        row.operator('sprite8.preview', icon='IMAGE_DATA')
        row.operator('sprite8.render', icon='RENDER_ANIMATION')
        row.operator('sprite8.open', text='', icon='FILE_FOLDER').path = s.frames_dir


class SPRITE8_PT_sheet(Panel, bpy.types.Panel):
    bl_label = '3. 도트 시트'
    bl_parent_id = 'SPRITE8_PT_main'

    def draw(self, context):
        s = context.scene.sprite8; col = self.layout.column()
        col.prop(s, 'sheets_dir')
        col.prop(s, 'cell'); col.prop(s, 'alpha'); col.prop(s, 'color_step')
        row = col.row(align=True)
        row.prop(s, 'use_outline')
        sub = row.row(); sub.enabled = s.use_outline; sub.prop(s, 'outline_color', text='')
        col.prop(s, 'only'); col.prop(s, 'rename')
        row = col.row(align=True)
        row.prop(s, 'gif'); sub = row.row(); sub.enabled = s.gif; sub.prop(s, 'gif_scale')
        col.prop(s, 'fps')
        col.prop(s, 'art_json')
        if s.art_json:
            box = col.box().column()
            for k in ('loop', 'ppu', 'pivot_y', 'height'):
                box.prop(s, k)
        row = col.row(align=True)
        row.operator('sprite8.pixelize', icon='TEXTURE')
        row.operator('sprite8.open', text='', icon='FILE_FOLDER').path = s.sheets_dir
        col.operator('sprite8.render_and_pixelize', icon='PLAY')


classes = (ClipItem, Settings, SPRITE8_OT_prep, SPRITE8_OT_scan, SPRITE8_OT_read_actions, SPRITE8_OT_clip_add,
           SPRITE8_OT_clip_remove, SPRITE8_OT_clip_toggle, SPRITE8_OT_preview, SPRITE8_OT_render, SPRITE8_OT_pixelize,
           SPRITE8_OT_render_and_pixelize, SPRITE8_OT_cancel, SPRITE8_OT_open, SPRITE8_UL_clips,
           SPRITE8_PT_main, SPRITE8_PT_prep, SPRITE8_PT_render, SPRITE8_PT_sheet)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.sprite8 = PointerProperty(type=Settings)


def unregister():
    if Job.current:
        Job.current.cancel()
    del bpy.types.Scene.sprite8
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
