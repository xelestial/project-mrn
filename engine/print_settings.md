# print_settings.py

## 역할
현재 기본 설정과 문서 무결성 상태를 사람이 빠르게 확인할 수 있게 출력한다.

## 최신 변경
- 종료 규칙 출력에 `monopolies_to_trigger_end`를 유지하고, `tiles_to_trigger_end`, `higher_tiles_to_trigger_end`는 `None`으로 유지한다.
- 현재 기본 종료 규칙은 7타일, 3구역 독점, 9타일, 생존자 수 기준을 함께 보여준다.

## 수정 시 주의
- 기본 설정 키가 늘어나면 이 출력과 `test_config_settings.py`를 함께 갱신한다.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.
