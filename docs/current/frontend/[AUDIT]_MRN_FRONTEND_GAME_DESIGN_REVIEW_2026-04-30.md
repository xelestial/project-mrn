# MRN 프론트엔드 게임 디자인 의견서

작성일: 2026-04-30 KST

## 결론

MRN 웹 프론트엔드는 현재 "게임판이 있는 운영 도구"에서 "상업형 보드게임 UI"로 넘어가려는 중간 단계다. 방향은 맞다. 보드 우선 구조, 플레이어 스탠디, 이벤트 오버레이, 프롬프트 카드, 날씨/턴/경제 피드백까지 게임다운 재료는 이미 들어와 있다.

다만 현 상태를 최신 모바일/PC 보드게임과 비교하면 아직 상업 출시급은 아니다. 가장 큰 문제는 미감 부족이 아니라 읽기성이다. 3초 안에 "누구 차례인가", "무슨 일이 일어났나", "나는 무엇을 해야 하나"가 한 번에 들어와야 하는데, 데스크톱에서는 프롬프트 오버레이가 보드를 크게 가리고, 모바일에서는 카드 선택지가 세로 글자로 무너진다. 즉, 현재의 핵심 과제는 더 화려하게 만드는 것이 아니라 게임 상태를 더 빠르게 이해시키는 것이다.

추천 방향은 `조선 누아르 장부 보드게임`이다. MONOPOLY GO식 보상 리듬, Catan Universe식 보드 명료성, MARVEL SNAP식 빠른 이벤트 판독성을 가져오되, MRN만의 인장, 장부, 암행, 거래, 밀약, 표식 모티프로 고유한 시각 언어를 만들어야 한다.

## 검토 범위와 증거

- 로컬 앱: `apps/web`, Vite dev server `http://127.0.0.1:9000`
- 주요 파일: `apps/web/src/App.tsx`, `apps/web/src/styles.css`, `apps/web/src/features/board/BoardPanel.tsx`, `apps/web/src/features/board/GameEventOverlay.tsx`, `apps/web/src/features/prompt/PromptOverlay.tsx`
- 캡처:
  - `/Users/sil/Workspace/project-mrn/.gstack/mrn-lobby-1440x900.png`
  - `/Users/sil/Workspace/project-mrn/.gstack/mrn-match-1440x900.png`
  - `/Users/sil/Workspace/project-mrn/.gstack/mrn-match-mobile-390x844.png`
- 로컬 성능 참고치:
  - Playwright navigation: DOMContentLoaded 63ms, load 64ms
  - gstack browse perf: total 214ms, load 214ms
  - 주의: 로컬 Vite/mock 런타임 기준이라 production bundle, 네트워크, 실제 스트림 비용을 대표하지는 않는다.

## 참고 게임

- [MONOPOLY GO! - Scopely](https://www.scopely.com/en/games/monopoly-go): 캐주얼 보드, 큰 보상 피드백, 단순한 액션 판독성.
- [MARVEL SNAP](https://marvelsnap.com/): 짧은 매치, 강한 카드/이벤트 연출, 빠른 정보 밀도.
- [MARVEL SNAP Game Overview](https://marvelsnap.com/game-overview/): 카드와 위치 중심 UI 문법.
- [CATAN Universe](https://www.catan.com/catan-universe): 전략 보드의 명료성, 테이블탑 감각, 플랫폼 대응.
- [Board Kings - Google Play](https://play.google.com/store/apps/details?hl=en_US&id=com.jellybtn.boardkings): 캐주얼 보드, 빌드/공격/방문 루프, 밝은 월드 아이덴티티.

## 한줄 평가

- 게임 디자인 표현: 3.5 / 5
- 폰트: 3.2 / 5
- 레이아웃: 3.0 / 5
- 색상: 3.4 / 5
- 이벤트 오버레이: 3.6 / 5
- 컬러 패턴: 3.0 / 5
- 파티클/모션: 2.8 / 5
- 아이콘/SVG: 2.9 / 5
- 모바일 대응: 2.0 / 5
- 상업 출시 준비도: 3.1 / 5

## 잘하고 있는 점

보드는 이미 단순한 디버그 테이블을 벗어났다. 쿼터뷰 링 보드, 타일 색상, 소유자 스탬프, 이동 경로, 스탠디 캐릭터가 있고, 플레이어 4명을 화면 모서리에 배치하는 시도도 현재 장르와 잘 맞는다.

이벤트 오버레이는 종류 체계가 좋다. dice, move, purchase, rent, fortune, lap, bankruptcy, trick, mark, economy처럼 게임 사건을 시각적으로 분해할 준비가 되어 있다. 특히 주사위 SVG는 방향이 좋고, 이벤트마다 색을 다르게 잡으려는 의도도 타당하다.

프롬프트 오버레이도 단순 모달보다 낫다. 남은 시간, 대상 플레이어, 손패, 선택지, 카드 맥락이 한 장면 안에 들어온다. 이는 웹 앱이 아니라 실제 턴제 게임처럼 느껴지게 만드는 중요한 기반이다.

색상 체계는 어두운 네이비, 금색 결정 포인트, cyan 자원색, 플레이어별 주황/하늘/보라/초록으로 기본 축이 있다. 현재 테마는 일관성이 아주 없는 상태는 아니며, 오히려 너무 많은 보정 레이어가 쌓여 핵심 대비가 흐려지는 쪽에 가깝다.

## 주요 문제

### 1. 데스크톱 레이아웃: 보드와 프롬프트가 서로 싸운다

1440x900 매치 캡처에서 프롬프트 오버레이가 중앙 보드 대부분을 가린다. 선택 행동이 중요하다는 신호는 분명하지만, 보드게임에서 선택의 의미는 보드 상태와 함께 읽혀야 한다. 현재는 "선택 패널을 보느라 보드를 잃는" 순간이 생긴다.

권장: 선택 오버레이는 전체 폭을 덮는 방식보다 하단 dock, 우측 inspector, 또는 축소/확대 가능한 stage card로 정리한다. 핵심 선택지는 크게 보여주되, 보드 중앙의 이동/소유/도착 정보는 계속 살아 있어야 한다.

### 2. 모바일 레이아웃: 현재는 플레이 불가에 가깝다

390x844 캡처에서 카드 선택지가 좁은 열로 압축되어 글자가 세로로 쪼개진다. 플레이어 카드, 보드, 날씨, 손패, 선택 모달이 모두 동시에 보이려다 정보가 붕괴한다. 최신 모바일 보드게임은 한 화면에 모든 것을 넣지 않는다. 지금 필요한 것만 stage로 끌어올리고 나머지는 접는다.

권장: 모바일은 별도 레이아웃이어야 한다. 상단: 현재 턴/날씨/자원. 중앙: 보드 또는 선택 stage 중 하나. 하단: 내 액션. 다른 플레이어 상태와 로그는 drawer로 숨긴다.

### 3. 아이콘 언어가 섞여 있다

현재 이벤트 표기는 SVG 주사위, 텍스트, 기호, emoji가 섞여 있다. 예를 들어 이벤트 오버레이는 `💸`, `💰`, `👀`, `🎉`, `💀`, `✦`, `이동`, `땅`, `꾀`, `지목`이 함께 쓰인다. 프로토타입으로는 빠르지만, 상업형 게임 UI에서는 세계관 밀도를 깨뜨린다.

권장: core event icon set 12-16개를 만든다. 주사위, 이동, 매입, 통행료 지불, 통행료 수령, 날씨, 잔꾀, 표식, 파산, 보상, 손패, 장부를 같은 선 굵기와 같은 재질의 SVG로 통일한다. 기존 `pawn-piece.svg`, `private-character-seal.svg`는 좋은 출발점이지만, 전체 UI의 문장으로 확장되어야 한다.

### 4. 색상은 많지만 의미 우선순위가 약하다

CSS에는 흰색, 금색, 옅은 파랑, 네이비 계열이 매우 자주 반복된다. 플레이어 색과 이벤트 색은 나쁘지 않지만, "현재 행동", "위험", "보상", "내 것", "상대 것", "시스템 상태"가 색만 보고 즉시 구분되지는 않는다.

권장: 색을 더 추가하지 말고 줄인다. 색 토큰을 의미별로 잠그는 것이 먼저다.

- 결정/선택: gold
- 내 턴/내 소유: player color + gold ring
- 보상/수익: green 또는 coin gold
- 손실/위험: red
- 정보/날씨/시스템: cyan
- 비활성/과거 로그: desaturated blue

### 5. 폰트는 안전하지만 개성이 약하다

`Noto Sans KR` 중심 선택은 한국어 가독성 면에서 안전하다. 문제는 모든 UI가 같은 목소리로 말한다는 점이다. 현재 게임은 장부, 암행, 거래, 잔꾀 같은 단어를 쓰는데, 타이틀/이벤트/보상 순간의 타이포그래피가 이 세계관을 충분히 밀어주지 않는다.

권장: 본문과 숫자는 Noto Sans KR을 유지한다. 대신 이벤트 제목, 큰 보상, 챕터/라운드, 카드 이름에는 한국어 표시성이 있는 별도 display face를 제한적으로 쓴다. 과하게 붓글씨로 가면 촌스러워질 수 있으니, "현대적으로 정리된 역사물 UI" 쪽이 좋다.

### 6. 파티클과 모션은 아직 CSS 장식 단계다

현재는 conic-gradient burst, pulse, shake, hop, trail, flash가 중심이다. 반응성은 있지만 최신 캐주얼/카드 게임의 "보상감"에는 못 미친다. MONOPOLY GO나 MARVEL SNAP은 사건이 일어날 때 화면이 그 사건의 무게를 즉시 보여준다.

권장: 전역 파티클을 남발하지 말고 사건별 micro VFX를 만든다.

- dice: 주사위 착지, 1회 충격파, 숫자 pop
- move: 경로 spark, 도착 tile pulse
- rent pay: coin drain, red debit slash
- rent receive: coin burst, ledger stamp
- mark/trick: seal flip, ink smear, card shimmer
- lap/reward: controlled confetti, coin arc

`prefers-reduced-motion` 대응은 반드시 유지한다.

## 디자인 샷건 옵션

### A. Commercial Board Table

MONOPOLY GO와 Board Kings에 가까운 방향이다. 밝은 보드, 큰 보상 숫자, 캐릭터 리액션, 명확한 액션 버튼을 앞세운다. 장점은 접근성과 모바일 친화성이다. 단점은 MRN의 조선/잔꾀/장부 느낌이 약해질 수 있다.

### B. Joseon Noir Ledger

현재 MRN에 가장 어울리는 방향이다. 어두운 남색, 금박, 인장 빨강, 장부 종이, 먹선, 도장, 비밀문서, 엽전/냥 모티프를 쓴다. 장점은 고유성이 강하다는 점이다. 단점은 과하면 어둡고 복잡해질 수 있으므로 정보 계층을 엄격하게 잡아야 한다.

### C. Strategic Tabletop

CATAN Universe에 가까운 방향이다. 보드를 가장 선명하게 두고, 연출은 절제하며, 현재 턴/자원/선택을 정확히 읽히게 한다. 장점은 전략 게임으로서 신뢰감이다. 단점은 캐주얼한 보상감과 캐릭터성이 약해질 수 있다.

추천 조합: B를 메인 아이덴티티로 삼고, A의 보상 리듬과 C의 보드 명료성을 섞는다.

## 우선순위 제안

### P0. 3초 판독성 회복

- 항상 보이는 현재 배우: 플레이어, 캐릭터, 턴 상태
- 항상 보이는 이유: 왜 이 프롬프트가 떴는지
- 항상 보이는 결과: 방금 굴림, 이동, 매입/통행료, 손익
- 보드 중앙을 가리는 오버레이 최소화
- 모바일 전용 action stage 설계

### P1. 아이콘과 이벤트 문법 통일

- emoji 제거
- core event SVG icon set 제작
- 이벤트별 색/모션/사운드 후보 정의
- overlay title, icon, amount, affected tile/player의 순서 고정

### P2. MRN만의 시그니처 룩 만들기

- 인장, 장부, 엽전, 밀서, 표식, 날씨, 암행 모티프를 UI 전반으로 확장
- generic sci-fi blue panel 느낌을 줄이고 역사물+보드게임의 재료감을 추가
- 카드, 타일, 버튼, 배지에 같은 세계관 질감을 적용

### P3. 성능과 반응형 기준선

- 1366x768, 1440x900, 390x844, 430x932를 필수 QA 뷰포트로 지정
- tile label 최소 가독 크기 보장
- backdrop-filter와 큰 box-shadow가 많은 화면에서 GPU 비용 측정
- production build 기준 Lighthouse/Playwright trace 별도 측정

## 출시 전 합격 기준

- 3초 테스트: 처음 보는 사람이 누구 차례인지, 무슨 일이 일어났는지, 무엇을 눌러야 하는지 말할 수 있다.
- 이벤트 테스트: dice, move, rent, fortune, mark가 텍스트를 읽기 전에 구분된다.
- 모바일 테스트: 카드명과 버튼 텍스트가 세로로 깨지지 않는다.
- 보드 테스트: 선택 프롬프트 중에도 도착 타일과 관련 플레이어가 보인다.
- 아이콘 테스트: core game surface에서 emoji가 사라지고 같은 스타일의 아이콘만 남는다.
- 색상 테스트: gold는 선택/결정, cyan은 정보/자원, red는 손실/위험처럼 의미가 흔들리지 않는다.

## 최종 의견

MRN은 이미 "예쁜 웹 대시보드"보다 더 어려운 길을 가고 있다. 보드게임, 카드 선택, 실시간 로그, 캐릭터, 경제 이벤트를 한 화면에서 다루려는 시도는 복잡하다. 그래서 지금 필요한 디자인 원칙은 장식 추가가 아니라 장면 연출의 절제다.

내 판단으로는 현재 방향을 버릴 필요는 없다. 다만 다음 패스는 "더 화려한 UI"가 아니라 "플레이어가 사건을 놓치지 않는 UI"여야 한다. 데스크톱은 보드와 선택의 공존, 모바일은 완전히 다른 action-first 구조, 비주얼은 조선 누아르 장부라는 고유한 말투. 이 세 가지를 잡으면 MRN은 흔한 다크 블루 게임판에서 벗어나 자기 얼굴을 가질 수 있다.
