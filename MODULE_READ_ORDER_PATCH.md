## 패치: MODULE_READ_ORDER.md 추가 항목

다음을 "최우선 공통 문서" 섹션 맨 위에 추가:

```
## 최우선 공통 문서
- **공동 개발 원칙은 `COLLAB_SPEC_v0_3.md`를 읽는다.**
- **아키텍처 리팩토링 작업 전 반드시 `ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md`를 읽는다.**
- 구현 세부 예시는 `ARCHITECTURE_IMPL_GUIDE.md`를 참고한다.
- `CHANGE_WORKFLOW_GUIDE.md`가 정식 기준 문서일 때는 작업 시작 전에 먼저 읽는다.
- 메타데이터/로그/외부 보드 스펙을 건드릴 때는 `METADATA_REGISTRY.md`, `ACTION_LOG_SCHEMA.md`, `BOARD_LAYOUT_SCHEMA.md`를 먼저 확인한다.
```

그리고 하단에 아래 추가:

```
## 아키텍처 관련 문서
- `COLLAB_SPEC_v0_3.md` → Claude/GPT 공동 개발 원칙 명세
- `ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md` → 정책/생존/분석 리팩토링 합의안 (v1.0)
- `ARCHITECTURE_IMPL_GUIDE.md` → AGREED SPEC 구현 가이드 (registry/factory/context/evaluator 예시)
```
