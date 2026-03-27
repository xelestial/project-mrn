# main.py

간단한 단일 정책 배치 실행 엔트리 문서.

## 이번 갱신
- `config` 기본 인자를 `None`으로 바꿔 mutable default 패턴을 제거했다.
- 결과가 0게임이어도 안전하게 요약을 만든다.
- 버전 메타데이터를 최신 값과 동기화했다.


The main module keeps a tiny interactive harness for one-off local runs and printing basic winners. Distribution cleanup does not change runtime behavior here.
