# render8.py가 찍은 프레임을 도트 스프라이트 시트로 만든다. 일반 Python(Pillow, numpy) 스크립트.
#
#   python scripts/pixelize.py work/hero_frames work/hero_sheets --cell 96
#   python scripts/pixelize.py work/hero_frames out/hero --cell 96 --art-json --rename dash=rolling
#
# 출력: {동작}.png(줄 = 방향 S,SW,W,NW,N,NE,E,SE / 칸 = 프레임), sprites.json, preview.gif(선택), art.json(선택)
import argparse, glob, json, os, re

import numpy as np
from PIL import Image, ImageDraw

DIRS = ['S', 'SW', 'W', 'NW', 'N', 'NE', 'E', 'SE']
LOOP_DEFAULT = 'idle,run,air,climb,walk,sprint'


def parse():
    p = argparse.ArgumentParser(description='8방향 렌더 프레임 → 도트 시트')
    p.add_argument('src', help='render8.py 출력 폴더')
    p.add_argument('out', help='시트를 쓸 폴더')
    p.add_argument('--cell', type=int, default=96, help='칸 크기(px). 렌더 크기의 절반 권장 (기본 96)')
    p.add_argument('--alpha', type=int, default=110, help='이 값(0~255)보다 불투명한 픽셀만 남김 (기본 110)')
    p.add_argument('--color-step', type=int, default=8, help='색 단계 간격. 8 = 채널당 32단계, 1 = 줄이지 않음 (기본 8)')
    p.add_argument('--outline', default='12101a', help='1px 외곽선 색(hex). none이면 외곽선 없음 (기본 12101a)')
    p.add_argument('--only', default='', help='이 동작만 처리, 쉼표 구분')
    p.add_argument('--rename', action='append', default=[], metavar='OLD=NEW', help='시트 이름 바꾸기 (예: dash=rolling)')
    p.add_argument('--no-gif', action='store_true', help='preview.gif를 만들지 않음')
    g = p.add_argument_group('art.json (엔진에서 읽을 애니메이션 메타데이터, 선택)')
    g.add_argument('--art-json', action='store_true', help='art.json도 만듦. 이미 있으면 이번에 만든 동작의 clips만 갱신하고 나머지 값은 유지')
    g.add_argument('--fps', type=int, default=10, help='재생 fps (기본 10. render8 --step 3 + 30fps 원본이면 10)')
    g.add_argument('--loop', default=LOOP_DEFAULT, help=f'반복 재생 동작, 쉼표 구분 (기본 {LOOP_DEFAULT})')
    g.add_argument('--ppu', type=float, default=40, help='pixelsPerUnit (기본 40)')
    g.add_argument('--pivot-y', type=float, default=0.25, help='발 위치(칸 아래에서 비율, 기본 0.25)')
    g.add_argument('--height', type=float, default=1.25, help='머리 위 UI 높이(m, 기본 1.25)')
    return p.parse_args()


def pixel(im, a):
    im = im.resize((a.cell, a.cell), Image.BOX)
    px = np.asarray(im).copy()
    solid = px[..., 3] > a.alpha
    rgb = px[..., :3] // a.color_step * a.color_step
    o = np.zeros((a.cell, a.cell, 4), np.uint8)
    o[solid, :3] = rgb[solid]; o[solid, 3] = 255
    if a.outline.lower() != 'none':
        pad = np.pad(solid, 1)
        ring = (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~solid
        o[ring] = (*bytes.fromhex(a.outline), 255)
    return Image.fromarray(o)


def frames_of(src, anim, d):
    pat = re.compile(re.escape(f'{anim}_{d}_') + r'(\d+)\.png$')
    fs = [(int(m.group(1)), f) for f in glob.glob(os.path.join(src, f'{anim}_{d}_*.png'))
          if (m := pat.search(os.path.basename(f)))]
    return [f for _, f in sorted(fs)]


def main():
    a = parse()
    os.makedirs(a.out, exist_ok=True)
    rename = dict(r.split('=', 1) for r in a.rename)
    only = {s for s in a.only.split(',') if s}
    anims = sorted({re.sub(r'_S_\d+\.png$', '', os.path.basename(f)) for f in glob.glob(os.path.join(a.src, '*_S_*.png'))
                    if re.search(r'_S_\d+\.png$', f)})
    if only:
        anims = [x for x in anims if x in only]
    if not anims:
        raise SystemExit(f'{a.src}에 {{동작}}_S_00.png 형식 프레임이 없습니다')
    meta_path = os.path.join(a.out, 'sprites.json')
    meta = json.load(open(meta_path, encoding='utf-8')) if os.path.exists(meta_path) else {}
    preview = []; done = []
    for an in anims:
        rows = [[pixel(Image.open(f).convert('RGBA'), a) for f in frames_of(a.src, an, d)] for d in DIRS]
        n = len(rows[0])
        if any(len(r) != n for r in rows):
            raise SystemExit(f'{an}: 방향마다 프레임 수가 다릅니다 {[len(r) for r in rows]}')
        sheet = rename.get(an, an)
        sh = Image.new('RGBA', (a.cell * n, a.cell * len(DIRS)))
        for y, r in enumerate(rows):
            for x, f in enumerate(r):
                sh.paste(f, (x * a.cell, y * a.cell))
        sh.save(os.path.join(a.out, f'{sheet}.png'))
        meta[sheet] = {'frames': n, 'cell': a.cell, 'rows': DIRS}; done.append(sheet)
        print(f'{sheet}.png  {n}프레임 x {len(DIRS)}방향')
        for i in range(n):
            bg = Image.new('RGBA', (a.cell * len(DIRS), a.cell + 14), (30, 28, 44, 255))
            for di in range(len(DIRS)):
                bg.alpha_composite(rows[di][i], (di * a.cell, 14))
            ImageDraw.Draw(bg).text((3, 1), sheet, fill=(230, 230, 240, 255))
            preview.append(bg)
    json.dump(meta, open(meta_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    if not a.no_gif and preview:
        scale = max(1, 288 // a.cell)
        fr = [im.resize((im.width * scale, im.height * scale), Image.NEAREST).convert('RGB') for im in preview]
        fr[0].save(os.path.join(a.out, 'preview.gif'), save_all=True, append_images=fr[1:], duration=round(1000 / a.fps), loop=0)

    if a.art_json:
        art_path = os.path.join(a.out, 'art.json')
        art = json.load(open(art_path, encoding='utf-8')) if os.path.exists(art_path) else {
            'frameWidth': a.cell, 'frameHeight': a.cell, 'pixelsPerUnit': a.ppu,
            'pivotX': 0.5, 'pivotY': a.pivot_y, 'height': a.height,
            'directions': DIRS, 'layout': 'rows', 'clips': {}}
        loops = {s for s in a.loop.split(',') if s}
        for sheet in done:  # 이번에 만든 시트만 넣고, 손으로 고친 다른 동작 값은 그대로
            art['clips'][sheet] = {'sheet': sheet, 'fps': a.fps, 'loop': sheet in loops}
        json.dump(art, open(art_path, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        print('art.json clips:', ', '.join(art['clips']))


if __name__ == '__main__':
    main()
