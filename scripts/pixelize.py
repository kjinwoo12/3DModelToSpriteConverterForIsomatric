# render8.py가 찍은 프레임을 도트 스프라이트 시트로 만든다. numpy만 쓰므로 Blender 안에서도 돈다.
#
#   blender -b -P scripts/pixelize.py -- work/hero_frames work/hero_sheets --cell 96
#   python scripts/pixelize.py work/hero_frames out/hero --cell 96 --art-json --rename dash=rolling   (Pillow 필요)
#
# 출력: {동작}.png(줄 = 방향 S,SW,W,NW,N,NE,E,SE / 칸 = 프레임), sprites.json, preview.gif(선택), art.json(선택)
import argparse, glob, json, os, re, struct, sys, zlib

import numpy as np

try:
    import bpy  # Blender 안이면 PNG 읽기에 bpy 사용, 밖이면 Pillow
except ImportError:
    bpy = None

DIRS = ['S', 'SW', 'W', 'NW', 'N', 'NE', 'E', 'SE']
LOOP_DEFAULT = 'idle,run,air,climb,walk,sprint'
PREVIEW_BG = (30, 28, 44)


def parse(argv=None):
    if argv is None:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser(prog='pixelize.py', description='8방향 렌더 프레임 → 도트 시트')
    p.add_argument('src', help='render8.py 출력 폴더')
    p.add_argument('out', help='시트를 쓸 폴더')
    p.add_argument('--cell', type=int, default=96, help='칸 크기(px). 렌더 크기의 절반 권장 (기본 96)')
    p.add_argument('--alpha', type=int, default=110, help='이 값(0~255)보다 불투명한 픽셀만 남김 (기본 110)')
    p.add_argument('--color-step', type=int, default=8, help='색 단계 간격. 8 = 채널당 32단계, 1 = 줄이지 않음 (기본 8)')
    p.add_argument('--outline', default='12101a', help='1px 외곽선 색(hex). none이면 외곽선 없음 (기본 12101a)')
    p.add_argument('--only', default='', help='이 동작만 처리, 쉼표 구분')
    p.add_argument('--rename', action='append', default=[], metavar='OLD=NEW', help='시트 이름 바꾸기 (예: dash=rolling)')
    p.add_argument('--no-gif', action='store_true', help='preview.gif를 만들지 않음')
    p.add_argument('--gif-scale', type=int, default=2, help='preview.gif 확대 배율 (기본 2)')
    g = p.add_argument_group('art.json (엔진에서 읽을 애니메이션 메타데이터, 선택)')
    g.add_argument('--art-json', action='store_true', help='art.json도 만듦. 이미 있으면 이번에 만든 동작의 clips만 갱신하고 나머지 값은 유지')
    g.add_argument('--fps', type=int, default=10, help='재생 fps (기본 10. render8 --step 3 + 30fps 원본이면 10)')
    g.add_argument('--loop', default=LOOP_DEFAULT, help=f'반복 재생 동작, 쉼표 구분 (기본 {LOOP_DEFAULT})')
    g.add_argument('--ppu', type=float, default=40, help='pixelsPerUnit (기본 40)')
    g.add_argument('--pivot-y', type=float, default=0.25, help='발 위치(칸 아래에서 비율, 기본 0.25)')
    g.add_argument('--height', type=float, default=1.25, help='머리 위 UI 높이(m, 기본 1.25)')
    return p.parse_args(argv)


# ---- 파일 입출력 ---------------------------------------------------------------

def load_rgba(path):
    """PNG → (h, w, 4) uint8, 위에서 아래 순서"""
    if bpy is None:
        from PIL import Image
        return np.asarray(Image.open(path).convert('RGBA'))
    im = bpy.data.images.load(os.path.abspath(path), check_existing=False)
    try:
        w, h = im.size
        px = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(im)
    return np.round(px.reshape(h, w, 4)[::-1] * 255).astype(np.uint8)


def _chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))


def save_png(path, rgba):
    h, w = rgba.shape[:2]
    raw = np.concatenate([np.zeros((h, 1), np.uint8), rgba.reshape(h, w * 4)], 1).tobytes()  # 줄마다 필터 0
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


def _lzw(data):
    """GIF용 LZW. data = 8비트 색 번호 bytes"""
    out = bytearray(); acc = nbits = 0; width = 9

    def put(code):
        nonlocal acc, nbits
        acc |= code << nbits; nbits += width
        while nbits >= 8:
            out.append(acc & 255); acc >>= 8; nbits -= 8

    base = {bytes([i]): i for i in range(256)}
    table = dict(base); nxt = 258
    put(256)  # clear
    w = data[:1]
    for i in range(1, len(data)):
        c = data[i:i + 1]; wc = w + c
        if wc in table:
            w = wc; continue
        put(table[w])
        if nxt < 4096:
            table[wc] = nxt; nxt += 1
            if nxt > (1 << width) and width < 12:
                width += 1
        else:  # 표가 차면 비우고 다시
            put(256); table = dict(base); nxt = 258; width = 9
        w = c
    put(table[w]); put(257)  # end
    if nbits:
        out.append(acc & 255)
    return bytes(out)


def save_gif(path, frames, ms):
    """RGB 프레임들 → 무한 반복 GIF. 팔레트는 많이 쓰인 256색, 나머지 색은 가장 가까운 색으로"""
    key = lambda px: (px[..., 0].astype(np.int64) << 16) | (px[..., 1].astype(np.int64) << 8) | px[..., 2]
    uniq, cnt = np.unique(np.concatenate([key(f).ravel() for f in frames]), return_counts=True)
    pal = uniq[np.argsort(-cnt, kind='stable')[:256]]
    rgb = lambda k: np.stack([(k >> 16) & 255, (k >> 8) & 255, k & 255], -1)
    prgb, urgb = rgb(pal), rgb(uniq)
    near = np.empty(len(uniq), np.uint8)
    for s in range(0, len(uniq), 2048):
        near[s:s + 2048] = ((urgb[s:s + 2048, None] - prgb[None]) ** 2).sum(2).argmin(1)
    table = np.zeros((256, 3), np.uint8); table[:len(pal)] = prgb
    h, w = frames[0].shape[:2]
    with open(path, 'wb') as f:
        f.write(b'GIF89a' + struct.pack('<HHBBB', w, h, 0xF7, 0, 0) + table.tobytes())
        f.write(b'\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00')
        for fr in frames:
            data = _lzw(near[np.searchsorted(uniq, key(fr))].tobytes())
            f.write(b'\x21\xF9\x04\x00' + struct.pack('<H', max(2, round(ms / 10))) + b'\x00\x00')
            f.write(b'\x2C' + struct.pack('<HHHHB', 0, 0, w, h, 0) + b'\x08')
            for s in range(0, len(data), 255):
                f.write(bytes([len(data[s:s + 255])]) + data[s:s + 255])
            f.write(b'\x00')
        f.write(b'\x3B')


# ---- 픽셀화 ----------------------------------------------------------------------

def _box_weights(src, dst):
    """면적 평균 가중치 행렬 (dst, src)"""
    s = src / dst; W = np.zeros((dst, src))
    for i in range(dst):
        lo, hi = i * s, (i + 1) * s
        for j in range(int(lo), min(src, int(np.ceil(hi)))):
            W[i, j] = min(hi, j + 1) - max(lo, j)
    return W / s


_weights = {}


def shrink(px, cell):
    """면적 평균 축소. 알파를 곱한 뒤 평균해야 투명한 가장자리 색이 번지지 않음"""
    h, w = px.shape[:2]
    Wy = _weights.setdefault((h, cell), _box_weights(h, cell))
    Wx = _weights.setdefault((w, cell), _box_weights(w, cell))
    f = px.astype(np.float64); a = f[..., 3:4] / 255
    r = np.concatenate([f[..., :3] * a, f[..., 3:4]], 2)
    r = np.einsum('ij,jkc->ikc', Wy, r); r = np.einsum('kl,ilc->ikc', Wx, r)
    al = r[..., 3:4] / 255
    rgb = np.where(al > 0, r[..., :3] / np.maximum(al, 1e-9), 0)
    return np.clip(np.round(np.concatenate([rgb, r[..., 3:4]], 2)), 0, 255).astype(np.uint8)


def pixel(px, a):
    px = shrink(px, a.cell)
    solid = px[..., 3] > a.alpha
    rgb = px[..., :3] // a.color_step * a.color_step
    o = np.zeros((a.cell, a.cell, 4), np.uint8)
    o[solid, :3] = rgb[solid]; o[solid, 3] = 255
    if a.outline.lower() != 'none':
        pad = np.pad(solid, 1)
        ring = (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]) & ~solid
        o[ring] = (*bytes.fromhex(a.outline), 255)
    return o


def frames_of(src, anim, d):
    pat = re.compile(re.escape(f'{anim}_{d}_') + r'(\d+)\.png$')
    fs = [(int(m.group(1)), f) for f in glob.glob(os.path.join(src, f'{anim}_{d}_*.png'))
          if (m := pat.search(os.path.basename(f)))]
    return [f for _, f in sorted(fs)]


def main(argv=None):
    a = parse(argv)
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
    for ai, an in enumerate(anims):
        rows = [[pixel(load_rgba(f), a) for f in frames_of(a.src, an, d)] for d in DIRS]
        n = len(rows[0])
        if any(len(r) != n for r in rows):
            raise SystemExit(f'{an}: 방향마다 프레임 수가 다릅니다 {[len(r) for r in rows]}')
        sheet = rename.get(an, an)
        save_png(os.path.join(a.out, f'{sheet}.png'), np.concatenate([np.concatenate(r, 1) for r in rows], 0))
        meta[sheet] = {'frames': n, 'cell': a.cell, 'rows': DIRS}; done.append(sheet)
        print(f'{sheet}.png  {n}프레임 x {len(DIRS)}방향')
        print(f'PROGRESS pixelize {ai + 1}/{len(anims)}', flush=True)
        if not a.no_gif:
            for i in range(n):
                strip = np.concatenate([r[i] for r in rows], 1)
                bg = np.empty(strip.shape[:2] + (3,), np.uint8); bg[:] = PREVIEW_BG
                m = strip[..., 3] > 0; bg[m] = strip[..., :3][m]
                preview.append(bg)
    json.dump(meta, open(meta_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    if preview:
        s = max(1, a.gif_scale)
        save_gif(os.path.join(a.out, 'preview.gif'), [im.repeat(s, 0).repeat(s, 1) for im in preview], 1000 / a.fps)

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
    print('DONE', ', '.join(done), flush=True)


if __name__ == '__main__':
    main()
