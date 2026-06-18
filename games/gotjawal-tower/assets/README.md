# 곤충 카드 사진 (실제 사진) 넣는 곳

여기에 아래 **파일 이름 그대로** 곤충 사진(jpg)을 넣으면, 게임의 동물 카드·슬롯에
그 사진이 바로 뜹니다. (정사각형에 가까울수록 예쁘게 보여요. 가로 400px 이상 권장)

| 파일 이름 | 곤충 |
|---|---|
| `muljanggun.jpg` | 물장군 |
| `wang_mantis.jpg` | 왕사마귀 |
| `dungbeetle.jpg` | 애기뿔소똥구리 |
| `jeju_beetle.jpg` | 제주홍단딱정벌레 |
| `aegi_mantis.jpg` | 애기사마귀 |
| `jangsu.jpg` | 장수풍뎅이 |
| `sasum.jpg` | 사슴벌레 |
| `mudang.jpg` | 무당벌레 |
| `samagwi.jpg` | 사마귀 |
| `jamjari.jpg` | 잠자리 |
| `meddugi.jpg` | 메뚜기 |
| `yeochi.jpg` | 여치 |
| `gwitturami.jpg` | 귀뚜라미 |
| `maemi.jpg` | 매미 |
| `banditbul.jpg` | 반딧불이 |
| `horangnabi.jpg` | 호랑나비 |
| `baechunabi.jpg` | 배추흰나비 |
| `kkulbeol.jpg` | 꿀벌 |
| `wangjamjari.jpg` | 왕잠자리 |
| `pungdeng.jpg` | 풍뎅이 |

## 동작 방식 (우선순위)
1. **이 폴더의 사진 파일** (있으면 최우선)
2. 없으면 → **자동 일러스트**로 대체 (게임은 항상 정상 동작)

> - 사진은 `.jpg`로, 위 파일명과 **정확히 똑같이** 저장해 주세요. (확장자가 png면 `gotjawal-tower.html`의
>   `INSECTS.forEach(it=>{ it.img=['assets/'+it.key+'.jpg']; });` 부분을 `.png`로 바꾸거나, 곤충별로 `img:[...]`를 직접 지정)
> - 공개 사진 URL을 쓰고 싶으면 해당 곤충의 `img` 배열에 URL을 추가하면 됩니다. 예: `it.img=['assets/maemi.jpg','https://.../maemi.jpg']`
> - 저작권을 꼭 확인하세요. 직접 찍은 사진이나 CC/공공누리 등 사용 가능한 사진을 권장합니다.
