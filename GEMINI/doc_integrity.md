# doc_integrity.py

- 역할: 최신 엔진 기준 문서화 파일.
- 핵심 변경: v0.7.5에서 승리토큰 최적화 프로파일, summary 문서무결성 출력, 무결성 테스트를 반영.
- 수정 규칙: 대응 소스 수정 시 반드시 본 문서를 같이 갱신하고 mtime이 소스보다 늦어야 한다.


## Timestamp tolerance
- The integrity check allows a tiny epsilon when comparing source/doc mtimes.
- This avoids false negatives caused by zip extraction or filesystem timestamp rounding while still requiring docs to track source changes.
