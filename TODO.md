# TODO — Phase 0 MVP에서 제외한 항목 (기획서 4.1 Out)

MVP에서는 아래 항목을 **구현하지 않는다**. 착수 단계는 기획서 5장 로드맵 기준.

## Phase 1 — 범용 분석 완성
- [ ] 장비별 오실로스코프 CSV 자동 인식 어댑터 (실제 사용 장비부터) — 현재는 범용 표 리더 + 사람이 확인하는 UI
- [ ] ngspice raw 바이너리 파서 (현재는 `wrdata` 텍스트/CSV만)
- [ ] 스윕 세트 업로드 → Shmoo(setup/hold 실제 마진) · Fmax · Vmin
- [ ] 엣지 지터, 글리치 검출, 노이즈 마진(NMH/NML)
- [ ] 대용량 파형 다운샘플링(min-max / LTTB) + WebGL, Parquet 저장
- [ ] 지표 정의 YAML화
- [ ] PDF 리포트
- [ ] "직전 매핑 불러오기" 버튼

## Phase 2 — 공유 웹
- [ ] 로그인 · 그룹(동아리/연구실) 권한
- [ ] 측정 이력 DB (프로젝트 → 칩 → 측정 세션), 재분석
- [ ] FastAPI(`api/`) + React(`web/`) 이전 — `core/`는 그대로 재사용
- [ ] 칩 간 비교(통계)

## Phase 3~4 — 칩 전용 플러그인
- [ ] TCAM 플러그인(`core/plugins/tcam/`: analyzer + tcam.yaml) — 핀맵 확인 후
- [ ] SRAM · DRAM 플러그인
