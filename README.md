# 3D Model → Isometric 8-Direction Sprite Converter

3D 캐릭터 모델과 Mixamo 동작으로 쿼터뷰(아이소메트릭) 8방향 도트 스프라이트 시트를 만드는 Blender 애드온 겸 명령줄 도구입니다.
Blender 3D 뷰 사이드바(N)의 **Sprite8** 탭에서 버튼으로 실행하거나, 같은 스크립트를 `blender -b -P`로 돌릴 수 있습니다.

```
모델(.glb/.fbx/.obj/.blend) ──mixamo_prep.py──▶ 업로드용 FBX ──Mixamo──▶ 동작별 FBX(스킨 포함)
   ──render8.py──▶ 8방향 PNG 프레임 ──pixelize.py──▶ 도트 시트 + sprites.json (+ preview.gif, art.json)
```

| 파일 | 실행 | 하는 일 |
|---|---|---|
| `scripts/__init__.py`, `blender_manifest.toml` | 애드온 | Sprite8 패널. 아래 스크립트를 백그라운드 Blender로 돌림 |
| `scripts/mixamo_prep.py` | Blender | 뼈대 제거, 텍스처 내장, (선택) 얇은 옷에 두께 → Mixamo 업로드용 FBX |
| `scripts/render8.py` | Blender | 동작 FBX를 정사영 고각 30°, 45° 간격 8방향으로 렌더. 제자리 고정 |
| `scripts/shading.py` | (render8이 import) | 평평한 애니풍 셰이딩, 뒷면 어둡게, 테두리 조명 |
| `scripts/pixelize.py` | Blender 또는 Python | 축소, 알파 컷, 색 단계, 1px 외곽선 → 시트, `sprites.json`, `preview.gif`, `art.json` |

## 설치

- **Blender 4.2 이상**(5.2에서 확인). 애드온만 쓰면 다른 설치는 필요 없습니다(Blender 내장 numpy만 사용).
- **Mixamo 계정**(Adobe, 무료). 이미 리깅·애니메이션이 들어간 FBX가 있으면 필요 없습니다.

### 애드온 설치

1. zip 만들기(저장소 루트에서):
   ```bash
   blender --command extension build --source-dir scripts --output-dir dist
   ```
   `dist/iso_sprite_converter-1.0.0.zip`이 생깁니다.
2. Blender에서 **Edit > Preferences > Get Extensions > 오른쪽 위 ⌄ > Install from Disk**로 zip을 고릅니다. zip을 Blender 창에 끌어다 놓아도 됩니다.
3. 3D 뷰에서 `N`을 눌러 사이드바를 열고 **Sprite8** 탭을 엽니다.

설정값은 씬에 저장되므로 캐릭터마다 .blend를 하나 두면 다음에 그대로 다시 굽습니다.

### 명령줄로만 쓸 때

예시는 `blender`가 PATH에 있다고 가정합니다. 아니면 전체 경로로 씁니다(예: `"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"`).
pixelize만 일반 Python으로 돌리려면 `pip install -r requirements.txt`(numpy, Pillow)가 필요합니다.

명령은 저장소 루트에서 실행한다고 가정합니다. 아래 예시는 원본을 `models/{캐릭터}/`, 중간 결과를 `work/`에 둡니다(`work/`, `*.fbx`, `*.vrm`은 `.gitignore`에 들어 있음). 경로는 자유롭게 바꿔도 됩니다.

## 애드온 사용법

패널은 단계 순서대로 세 칸입니다. 각 단계는 백그라운드 Blender에서 돌기 때문에 지금 연 씬은 바뀌지 않고, 렌더 중에도 Blender를 쓸 수 있습니다. 진행률과 **취소** 버튼은 패널 맨 위에 나옵니다. 실패하면 마지막 오류 줄이 패널에 뜨고, 전체 로그는 **Window > Toggle System Console**에서 봅니다.

**1. Mixamo 업로드용 FBX** (이미 리깅된 FBX가 있으면 건너뜀)
- **모델**과 **출력 FBX**를 고르고 **Mixamo용 FBX 만들기**. 지금 Blender에서 고친 모델을 쓰려면 저장한 뒤 **지금 연 .blend 사용**을 켭니다.
- **Z 회전**, **두께**(`Coat_=0.008`), **삭제**(`Icosphere`)는 아래 명령줄 옵션과 같습니다. 여러 개는 쉼표로 구분합니다.

**2. 8방향 렌더**
- 동작 목록 채우기: **동작 폴더**를 고르면 그 폴더의 FBX가 하나씩 들어갑니다(동작 이름 = 파일 이름). 동작이 여러 개 든 FBX(KayKit 같은 에셋 팩)는 **여러 동작 FBX**에 고르고 **FBX 액션 읽기**를 누르면 액션마다 한 줄씩 들어갑니다(기본 꺼짐).
- 목록에서 구울 동작을 체크하고, 이름 칸을 더블클릭해 게임에서 쓸 이름(`idle`, `run` 등)으로 바꿉니다. 목록 아래 ▸를 열면 이름으로 검색할 수 있습니다.
- **프레임 폴더**를 정하고, 먼저 **미리보기 한 장**으로 선택한 동작의 S방향 첫 프레임을 찍어 봅니다. 결과는 이미지 에디터의 `Sprite8 Preview`에 뜹니다. 고각·화면 폭·겨눔 높이를 여기서 맞춥니다.
- 무기나 소품을 빼려면 **숨길 오브젝트**에 이름 앞부분을 씁니다(예: `1H_,2H_,Knife`).
- **8방향 렌더**로 체크한 동작을 전부 찍습니다. 나머지 옵션은 **세부 옵션**에 있고, 뜻은 아래 4단계 표와 같습니다.

**3. 도트 시트**
- **시트 폴더**를 정하고 **도트 시트 만들기**. 끝나면 첫 시트가 이미지 에디터에 뜨고, 움직임은 시트 폴더의 `preview.gif`로 봅니다.
- **렌더 + 시트**는 2단계 렌더가 끝나면 이어서 시트까지 만듭니다.
- 게임 엔진용 메타데이터가 필요하면 **art.json**을 켭니다(아래 6단계 참고).

## 명령줄 사용법: 캐릭터 `hero` 만들기

### 1. 모델 준비

정면이 보이는 T포즈나 A포즈 모델이 필요합니다. glTF(.glb), FBX, OBJ, .blend를 받습니다. VRoid(.vrm)는 확장자만 `.glb`로 바꾸면 그대로 읽힙니다.

색 바꾸기나 옷 추가 같은 개조는 Blender에서 먼저 하고 `.blend`나 `.glb`로 저장해 둡니다. 라이선스를 확인하고 CC0나 상업 이용 가능한 모델만 씁니다.

### 2. Mixamo 업로드용 FBX 만들기

```bash
blender -b -P scripts/mixamo_prep.py -- --in models/hero/hero.glb --out models/hero/hero_for_mixamo.fbx
```

- 옷이 한 겹이라 뒤에서 보면 구멍이 나면 두께를 줍니다: `--solidify Coat_=0.008` (이름이 `Coat_`로 시작하는 메시에 8mm, 여러 번 사용 가능)
- 렌더에 필요 없는 오브젝트 삭제: `--drop Icosphere`
- 모델이 뒤를 보고 있으면(VRoid/VRM) `--turn 180`. 정면이 Blender 앞쪽(-Y)을 봐야 Mixamo에서 정면으로 보입니다.
- 텍스처는 출력 폴더의 `textures/`에도 PNG로 풀립니다.

### 3. Mixamo에서 리깅하고 동작 받기

1. https://www.mixamo.com 에서 **Upload Character**로 `hero_for_mixamo.fbx`를 올립니다.
2. 턱, 손목, 팔꿈치, 무릎, 사타구니에 마커를 찍습니다. 소매가 넓으면 손목 마커는 실제 손목에 찍습니다. Skeleton LOD는 **Standard**(손가락 포함).
3. 동작을 고르고 **Download**: Format **FBX Binary**, Skin **With Skin**, Frames per Second **30**. **In Place**가 있으면 체크합니다(없어도 render8이 제자리로 고정).
4. 파일 이름을 게임에서 쓸 동작 이름으로 바꿔 `models/hero/anims/`에 모읍니다. 예: `idle.fbx`, `run.fbx`, `attack.fbx`

> Mixamo FBX는 Adobe 약관상 재배포할 수 없습니다. 공개 저장소에 커밋하지 말고 로컬에만 두세요. 구운 시트는 게임에 써도 됩니다.

### 4. 8방향 렌더

```bash
blender -b -P scripts/render8.py -- --out work/hero_frames --clips-dir models/hero/anims --res 192 --step 3
```

- `--step 3`: 30fps 원본에서 3프레임마다 한 장(= 10fps)
- `--res 192`: 렌더 크기. 다음 단계 칸 크기(96)의 2배로 찍어야 축소가 깔끔합니다.
- 한 동작만 다시: `--clip attack=models/hero/anims/attack.fbx` (같은 동작의 이전 프레임은 지우고 새로 씀)
- 동작이 여러 개 든 FBX: `--clip "idle=Rogue.fbx#Idle" --clip "run=Rogue.fbx#Running_A"`. 들어 있는 동작 이름은 `--list-actions Rogue.fbx`로 봅니다.
- 값 맞추기용 한 장: `--preview work/test.png` (첫 동작의 첫 프레임, S방향)
- 결과: `work/hero_frames/{동작}_{방향}_{번호}.png`, `meta.json`

자주 맞추는 값:

| 증상 | 옵션 |
|---|---|
| 카메라 각도를 게임에 맞추기 | `--elev` (고각, 기본 30° ≈ 2:1 아이소메트릭) |
| 캐릭터가 칸에 비해 너무 크거나 작음 | `--ortho` (화면 폭 m, 기본 3.2. 크면 작게 찍힘) |
| 머리나 발이 잘림 | `--target-z` (카메라 겨눔 높이, 기본 0.75) |
| S줄에 뒷모습이 찍힘 | `--face 180` |
| 오르기처럼 위로 올라가는 동작이 칸을 벗어남 | `--lockz climb,wallrun` (높이 이동도 없앰) |
| 음영이 너무 진하거나 약함 | `--emission` (기본 0.6, 높을수록 평평) |
| 테두리 조명 끄기·바꾸기 | `--rim 0`, `--rim-color 1,0.6,0.6` |
| 두께를 준 옷의 뒷면이 검게 나옴 | `--flat-prefix Coat_` |
| 제자리 고정 기준 뼈 바꾸기/끄기 | `--root-bone 이름`, `--keep-root-motion` |
| 무기·소품이 같이 찍힘 | `--hide 1H_ --hide Knife` (이름 앞부분, 여러 번) |
| 느림 | `--samples 4`, `--gpu` |

전체 옵션: `blender -b -P scripts/render8.py -- --help`

### 5. 도트 시트로 변환

```bash
blender -b -P scripts/pixelize.py -- work/hero_frames work/hero_sheets --cell 96
```

Pillow와 numpy가 있으면 `python scripts/pixelize.py work/hero_frames work/hero_sheets --cell 96`도 같습니다.

`work/hero_sheets/preview.gif`로 8방향을 한 번에 확인하고, 마음에 안 들면 4단계 옵션을 바꿔 다시 찍습니다.

- `--cell 96`: 칸 크기(px). 주인공 96, 작은 적 64 정도
- `--outline none`: 외곽선 없음 / `--outline 2a1a1a`: 외곽선 색
- `--color-step 1`: 색 단계를 줄이지 않음(기본 8 = 채널당 32단계)
- `--alpha 110`: 반투명 가장자리를 얼마나 잘라낼지
- `--rename dash=rolling`: 시트 이름을 게임 동작 이름에 맞춤
- `--only idle,run`: 일부 동작만 다시 만듦
- `--gif-scale 3`: preview.gif 확대 배율(기본 2)

### 6. 엔진에 넣기 (선택: art.json)

게임 에셋 폴더로 바로 출력하고 애니메이션 메타데이터 `art.json`도 만들 수 있습니다.

```bash
blender -b -P scripts/pixelize.py -- work/hero_frames path/to/game/Characters/hero --cell 96 --art-json --fps 10 --no-gif
```

- 없으면 기본값으로 새로 만듭니다(`--ppu 40 --pivot-y 0.25 --height 1.25`, 반복 재생 동작은 `--loop idle,run,...`).
- 이미 있으면 이번에 만든 동작의 `clips`만 넣거나 갱신하고, 손으로 맞춘 다른 값은 그대로 둡니다.
- `pivotY`는 칸 아래에서 발끝까지의 비율입니다. 기본 렌더 값이면 96px 칸에서 24px(0.25)입니다.

art.json 형식:

```json
{
  "frameWidth": 96, "frameHeight": 96, "pixelsPerUnit": 40,
  "pivotX": 0.5, "pivotY": 0.25, "height": 1.25,
  "directions": ["S","SW","W","NW","N","NE","E","SE"], "layout": "rows",
  "clips": { "idle": { "sheet": "idle", "fps": 10, "loop": true } }
}
```

Unity라면 PNG를 Filter Mode **Point**, Compression **None**, Pixels Per Unit = `pixelsPerUnit`으로 가져와 `frameWidth × frameHeight` 격자로 자르면 됩니다.

## 시트 형식

- 줄(위 → 아래) = 방향 `S, SW, W, NW, N, NE, E, SE`. S는 카메라 쪽(화면 아래), 시계 방향
- 칸(왼 → 오) = 프레임, 칸 크기는 `--cell`
- `sprites.json`: 시트마다 `{frames, cell, rows}`

## 문제 해결

- **`bpy`가 없다고 나옴**: 일반 `python`이 아니라 `blender -b -P ...`로 실행해야 합니다.
- **캐릭터가 투명하거나 흰색**: Mixamo 다운로드 때 Skin이 With Skin이었는지 확인. 텍스처가 FBX에 내장돼 있어야 합니다(mixamo_prep이 해 줌). 외부 텍스처를 쓰는 FBX는 render8이 FBX 폴더 아래에서 같은 파일 이름을 찾아 연결합니다.
- **애드온 패널이 안 보임**: Preferences > Add-ons에서 `Isometric 8-Direction Sprite Converter`가 켜져 있는지 확인합니다.
- **`방향마다 프레임 수가 다릅니다`**: 렌더가 중간에 끊긴 것. 그 동작만 `--clip`으로 다시 찍습니다.

## 라이선스

[MIT](LICENSE). 자유롭게 사용·수정·배포할 수 있습니다. 단, 이 도구로 처리하는 모델·동작(Mixamo 등)의 라이선스는 각 원본을 따릅니다.
