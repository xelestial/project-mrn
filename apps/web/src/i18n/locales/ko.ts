export const koLocale = {
  app: {
    title: "MRN Online Viewer (React/FastAPI)",
    subtitle: "세션 생성, 참가, 시작, 실시간 스트림 관찰을 한 화면에서 진행할 수 있습니다.",
    routeLobby: "로비",
    routeMatch: "매치",
    connectionExpand: "연결 상태 펼치기",
    connectionCollapse: "연결 상태 접기",
    densityStandard: "표준 밀도",
    densityCompact: "컴팩트 밀도",
    rawShow: "디버그 로그",
    rawHide: "디버그 로그 닫기",
    rawMessages: "디버그 로그",
    localeKo: "한국어",
    localeEn: "English",
    waitingTitle: (playerId: number) => `플레이어 P${playerId}의 선택을 기다리는 중입니다.`,
    waitingDescription: "내 턴이 아니어도 다른 플레이어의 진행 상황은 극장과 보드에서 계속 확인할 수 있습니다.",
    myTurnWaitingTitle: "내 턴 진행 준비 중",
    myTurnWaitingDescription: (beatLabel: string, beatDetail: string) =>
      koLocale.app.inlineSummary(["선택 요청을 불러오는 중", beatLabel, beatDetail]),
    passivePromptTitle: "다른 플레이어 선택 진행 중",
    passivePromptSummary: (playerId: number, promptLabel: string, secondsLeft: number | null) =>
      `P${playerId} / ${promptLabel} / 남은 시간 ${secondsLeft ?? "-"}초`,
    spectatorTitle: (playerId: number) => `P${playerId}의 진행 중`,
    spectatorDescription: "다른 플레이어가 행동하는 동안 공개된 진행 흐름을 계속 보여줍니다.",
    spectatorHeadline: "관전자 패널",
    inlineSummary: (parts: string[]) => {
      const visible = parts.map((part) => part.trim()).filter((part) => part && part !== "-");
      return visible.length > 0 ? visible.join(" / ") : "-";
    },
    spectatorEconomySummary: (parts: string[]) => koLocale.app.inlineSummary(parts),
    spectatorEffectSummary: (parts: string[]) => koLocale.app.inlineSummary(parts),
    spectatorSpotlightSummary: (parts: string[]) => koLocale.app.inlineSummary(parts),
    spectatorNeutralSummary: (parts: string[]) => koLocale.app.inlineSummary(parts),
    spectatorHeadlineSummary: (headline: string, summary: string) => koLocale.app.inlineSummary([headline, summary]),
    spectatorFields: {
      weather: "현재 날씨",
      character: "현재 인물",
      beat: "현재 단계",
      action: "공개 행동",
      prompt: "현재 선택",
      worker: "참가자 상태",
      move: "최근 이동",
      landing: "도착 처리",
      economy: "경제 처리",
      effect: "효과 처리",
      progress: "턴 진행 흐름",
    },
    topSummaryEmpty: "세션을 선택하세요",
    topSummary: (sessionId: string, runtimeStatus: string) => `세션 ${sessionId} / 상태 ${runtimeStatus}`,
    turnBanner: (actorText: string) => `${actorText}의 턴입니다`,
    reopenPrompt: (promptLabel: string, secondsLeft: number | null) =>
      `선택창 다시 열기: ${promptLabel} / 남은 ${secondsLeft ?? "-"}초`,
    errors: {
      refreshSessions: "세션 목록을 불러오지 못했습니다.",
      sendPrompt: "선택 요청을 전송하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      invalidPromptPlayer: "선택 요청에 player_id가 없습니다.",
      promptRejected: (reason?: string) => (reason ? `선택이 거절되었습니다. ${reason}` : "선택이 거절되었습니다."),
      promptStale: (reason?: string) =>
        reason ? `선택 요청이 이미 만료되었거나 처리되었습니다. ${reason}` : "선택 요청이 이미 만료되었거나 처리되었습니다.",
      promptTimedOut: "선택 시간이 만료되었습니다. 엔진이 기본 처리로 진행합니다.",
      promptConnectionLost: "연결이 잠시 끊겼습니다. 다시 연결되는지 계속 확인해 주세요.",
      createSession: "세션을 만들지 못했습니다.",
      startAiSession: "AI 세션을 시작하지 못했습니다.",
      quickStart: "빠른 시작을 실행하지 못했습니다.",
      startByHostTokenMissing: "세션 ID와 호스트 토큰을 입력해 주세요.",
      startSession: "세션을 시작하지 못했습니다.",
      joinSeatMissing: "세션 ID, 좌석, 참가 토큰을 입력해 주세요.",
      joinSeatFailed: "좌석 참가에 실패했습니다.",
      joinSeatNotWaiting: "세션이 waiting 상태가 아니므로 참가할 수 없습니다.",
      joinSeatNotFound: (seat: number) => `${seat}번 좌석 정보를 찾을 수 없습니다.`,
      joinSeatNotHuman: (seat: number) => `${seat}번 좌석은 사람이 참가하는 좌석이 아닙니다.`,
    },
    notices: {
      createSession: (sessionId: string, hostToken: string, joinTokens: Record<string, string>) =>
        `세션 생성 완료: ${sessionId} / host_token=${hostToken} / join_tokens=${JSON.stringify(joinTokens)}`,
      startAiSession: (sessionId: string) => `AI 세션 시작: ${sessionId}`,
      quickStart: (sessionId: string, playerId: number) => `빠른 시작 완료: ${sessionId} (P${playerId})`,
      startSession: (sessionId: string) => `세션 시작됨: ${sessionId}`,
      joinSeat: (playerId: number) => `P${playerId} 좌석 참가 완료`,
      useSession: (sessionId: string) => `세션 선택: ${sessionId}`,
    },
  },
  lobby: {
    controlsTitle: "로비 제어",
    createSessionTitle: "세션 생성",
    createSessionDescription: "새 세션을 만들고 사람/AI 좌석 구성을 지정합니다.",
    hostJoinTitle: "호스트 / 참가",
    hostJoinDescription: "기존 세션을 시작하거나 사람 좌석에 참가합니다.",
    streamTitle: "스트림 연결",
    sessionListTitle: (count: number) => `세션 목록 (${count})`,
    expand: "펼치기",
    collapse: "접기",
    fields: {
      seed: "시드",
      seatCount: "좌석 수 (1-4)",
      aiProfile: "AI 프로필",
      sessionId: "세션 ID",
      hostToken: "호스트 토큰",
      joinSeat: "참가 좌석",
      joinToken: "참가 토큰",
      displayName: "표시 이름",
      sessionToken: "세션 토큰 (선택)",
    },
    buttons: {
      quickStartHumanVsAi: "사람 1 + AI 3 빠른 시작",
      createCustomSession: "커스텀 세션 생성",
      createAndStartAi: "생성 + AI 세션 시작",
      startSession: "세션 시작",
      joinAndConnect: "참가 및 연결",
      connect: "연결",
      refreshSessions: "세션 새로고침",
      useSession: "이 세션 사용",
      useSeatToken: (seat: string) => `${seat}번 좌석 토큰 사용`,
    },
    placeholders: {
      sessionId: "sess_xxx",
      hostToken: "host_xxx",
      joinToken: "seat_join_token",
      sessionToken: "session_p1_xxx (관전자면 비워둠)",
    },
    labels: {
      latestCreateTokens: "최근 생성된 참가 토큰",
    },
    values: {
      human: "human",
      ai: "ai",
      seat: (seat: string) => `Seat ${seat}`,
    },
  },
  connection: {
    title: "연결 상태",
    fields: {
      connection: "연결",
      lastSequence: "마지막 시퀀스",
      runtime: "런타임",
      watchdog: "Watchdog",
      lastActivityMs: "마지막 활동(ms)",
    },
    runtimeStatus: {
      running: "실행 중",
      finished: "종료됨",
      failed: "실패",
      recovery_required: "복구 필요",
    },
    watchdogStatus: {
      ok: "정상",
      stalled_warning: "경고",
    },
  },
  board: {
    title: "보드",
    loading: "보드 정보를 기다리는 중입니다.",
    manifestBoard: "설정 정보(parameter manifest)로 초기화된 보드입니다.",
    roundTurnMarker: (round: number, turn: number, markerOwner: number | null, endTimeRemaining: number | null) =>
      `${round}라운드 / ${turn}턴 / 징표 소유자 P${markerOwner ?? "-"} / 종료 시간 ${endTimeRemaining?.toFixed(2) ?? "-"}`,
    lastMove: (playerId: number | null, fromTileIndex: number | null, toTileIndex: number | null) =>
      `최근 이동: P${playerId ?? "?"} ${fromTileIndex === null ? "?" : fromTileIndex + 1} -> ${toTileIndex === null ? "?" : toTileIndex + 1}`,
    zoneLabel: (zoneColor: string) => (zoneColor ? `구역 ${zoneColor}` : "구역 -"),
    costLabel: (cost: number | null, rent: number | null) => {
      const purchase = cost === null ? "-" : `${cost}냥`;
      const rentText = rent === null ? "-" : `${rent}냥`;
      return `구매가 ${purchase} / 통행료 ${rentText}`;
    },
    ownerNone: "소유자 -",
    owner: (playerId: number) => `소유자 P${playerId}`,
    moveStartTag: "출발",
    moveEndTag: "도착",
    activeTurnTag: (playerId: number) => `현재 턴 P${playerId}`,
    zoneColorCss: {
      "": "#475569",
      black: "#475569",
      red: "#ef4444",
      yellow: "#eab308",
      blue: "#3b82f6",
      green: "#22c55e",
      white: "#e2e8f0",
      검은색: "#475569",
      빨간색: "#ef4444",
      노란색: "#eab308",
      파란색: "#3b82f6",
      초록색: "#22c55e",
      하얀색: "#e2e8f0",
    },
    tileKind: {
      S: "운수",
      F1: "종료 - 1",
      F2: "종료 - 2",
      T2: "토지",
      T3: "고급 토지",
    },
  },
  players: {
    title: "플레이어",
    waiting: "플레이어 정보를 기다리는 중입니다.",
    stats: {
      position: (value: number) => `위치 ${value}`,
      cash: (value: number) => `현금 ${value}`,
      shards: (value: number) => `조각 ${value}`,
      tiles: (value: number) => `토지 ${value}`,
      hidden: (value: number) => `히든 ${value}`,
    },
  },
  timeline: {
    title: (count: number) => `최근 이벤트 (${count})`,
  },
  situation: {
    title: "현재 상황",
    cards: {
      actor: "행동자",
      roundTurn: "라운드 / 턴",
      event: "이벤트",
      weather: "날씨",
      weatherEffect: "날씨 효과",
    },
    roundTurn: (round: string, turn: string) => `${round}라운드 / ${turn}턴`,
    empty: "-",
    alertsTitle: "중요 경고",
  },
  promptType: {
    generic: "선택 요청",
    labels: {
      movement: "이동값 결정",
      runaway_step_choice: "탈출 노비 이동 선택",
      lap_reward: "랩 보상 선택",
      draft_card: "드래프트 인물 선택",
      final_character: "최종 캐릭터 선택",
      final_character_choice: "최종 캐릭터 선택",
      trick_to_use: "잔꾀 사용",
      purchase_tile: "토지 구매",
      hidden_trick_card: "히든 잔꾀 지정",
      mark_target: "지목 대상 선택",
      coin_placement: "승점 배치",
      geo_bonus: "지리 보너스 선택",
      doctrine_relief: "교리 연구관 효과",
      active_flip: "액티브 카드 뒤집기",
      specific_trick_reward: "특정 잔꾀 보상",
      burden_exchange: "짐 카드 교환",
      trick_tile_target: "잔꾀 대상 토지 선택",
    },
  },
  promptHelper: {
    default: "선택지를 고르면 즉시 엔진으로 전달됩니다. 남은 시간이 지나면 기본 응답으로 처리됩니다.",
    byType: {
      movement: "주사위를 굴리거나 주사위 카드를 사용해 이번 턴의 이동값을 결정하세요.",
      runaway_step_choice: "탈출 노비 효과로 선택 가능한 이동 경로 중 하나를 고르세요.",
      lap_reward: "10포인트 예산 안에서 현금/조각/승점 조합을 선택하세요.",
      draft_card: "드래프트 단계에서 이번 라운드 후보 인물을 가져가세요.",
      final_character: "최종으로 사용할 인물을 고르세요.",
      final_character_choice: "최종으로 사용할 인물을 고르세요.",
      trick_to_use: "지금 타이밍에 사용할 잔꾀를 선택하거나 사용하지 않음을 고르세요.",
      purchase_tile: "도착한 칸의 토지를 구매할지 결정하세요.",
      hidden_trick_card: "이번 라운드에 히든으로 지정할 잔꾀를 선택하세요.",
      mark_target: "지목 효과를 적용할 대상(인물/플레이어)을 선택하세요.",
      coin_placement: "승점을 어디에 놓을지 선택하세요.",
      geo_bonus: "지리 보너스 효과를 선택하세요.",
      doctrine_relief: "교리 연구관 효과의 적용 대상을 선택하세요.",
      active_flip: "현재 뒤집을 수 있는 카드 중 하나를 선택하거나 뒤집기 종료를 누르세요.",
      specific_trick_reward: "보상으로 받을 잔꾀를 선택하세요.",
      burden_exchange: "보급 단계가 열려 짐 카드를 정리할 수 있습니다. 이번에 비용을 내고 제거할지 결정하세요.",
      trick_tile_target: "카드 효과를 적용할 토지를 직접 고르세요.",
    },
  },
  eventLabel: {
    events: {
      session_started: "세션 시작됨",
      parameter_manifest: "설정 정보 동기화",
      round_start: "라운드 시작",
      weather_reveal: "날씨 공개",
      draft_pick: "드래프트 선택",
      final_character_choice: "최종 캐릭터 선택",
      turn_start: "턴 시작",
      dice_roll: "이동값 결정",
      player_move: "말 이동",
      trick_used: "잔꾀 사용",
      fortune_drawn: "운수 공개",
      fortune_resolved: "운수 처리",
      tile_purchased: "토지 구매",
      rent_paid: "렌트 지불",
      landing_resolved: "도착 칸 처리",
      marker_transferred: "징표 이동",
      marker_flip: "카드 뒤집기",
      lap_reward_chosen: "랩 보상 선택",
      decision_requested: "선택 요청 등록",
      decision_resolved: "선택 처리 완료",
      decision_timeout_fallback: "시간 초과 기본 처리",
      mark_queued: "지목 예약",
      mark_target_none: "지목 대상 없음",
      mark_target_missing: "지목 대상 불일치",
      mark_blocked: "지목 차단",
      active_flip_resolved: "카드 뒤집기 처리",
      bankruptcy: "파산",
      game_end: "게임 종료",
      game_finished: "게임 종료",
    },
    nonEvents: {
      prompt: "선택 요청",
      decision_ack: "선택 응답",
      system: "시스템",
      notice: "공지",
      error: "오류",
    },
    genericEvent: "이벤트",
    genericMessage: "메시지",
  },
  stream: {
    genericEvent: "이벤트",
    weatherEffectFallback: {
      "사냥의 계절": "무뢰 속성 인물의 지목 성공 시 추가로 4냥을 받습니다.",
      "풍년든 가을": "출발점을 돌 때 미리내 조각을 1개 더 받습니다.",
      "말이 살찌는 계절": "주사위를 1개 더 굴립니다.",
      "외세의 침략": "모든 참가자가 2냥을 은행에 지불합니다.",
      "솔선 수범": "징표를 가진 참가자는 3냥을 은행에 지불합니다.",
      "기우제": "징표를 가진 참가자는 조각 1개를 받고 종료 시간을 1칸 앞당깁니다.",
      "구휼의 상징": "징표를 가진 참가자는 4냥을 은행에서 받습니다.",
      "성물의 날": "조각을 받을 때 1개 더 받습니다.",
      "모든 것을 자원으로": "모든 짐 카드를 제거하고 제거 비용의 2배를 은행에서 받습니다.",
      "긴급 피난": "모든 짐 제거 비용이 2배가 됩니다.",
      "대규모 민란": "주인 없는 토지는 이번 턴 분쟁 지역으로 취급됩니다.",
      "운수 좋은 날": "운수 칸에 도착하면 2장을 공개합니다.",
      "검은 달": "검은색 토지의 통행료가 2배가 됩니다.",
      "휴가철": "빨간색 토지의 통행료가 2배가 됩니다.",
      "어린이 보호구역": "노란색 토지의 통행료가 2배가 됩니다.",
      "바다다!": "파란색 토지의 통행료가 2배가 됩니다.",
      "멋진 설경": "하얀색 토지의 통행료가 2배가 됩니다.",
      "곡식가득한 평야": "초록색 토지의 통행료가 2배가 됩니다.",
      "밤인데 낮처럼 밝아요": "종료를 3칸 앞당깁니다.",
      "길고 긴 겨울": "종료를 1칸 앞당깁니다.",
      "추운 겨울날": "출발점 통과 보상 없음 + 2냥 은행 지불",
      "사랑과 우정": "같은 칸 조우 시 참가자 1명당 4냥을 얻습니다.",
      "잔꾀 부리기": "잔꾀를 1장 받고 기존 잔꾀를 버리고 새로 받을 수 있습니다.",
      "아주 큰 화목 난로": "이번 라운드의 짐 피해가 줄어듭니다.",
      "배신의 징표": "현재 효과 없음",
      "맑고 포근한 하루": "주사위 카드를 1장 선택해 가집니다.",
    } as const,
    genericEffect: (name: string) => `${name} 효과`,
    moveSummary: (fromDisplay: string, toDisplay: string, pathLength?: number) =>
      typeof pathLength === "number" && pathLength > 0 ? `${fromDisplay} -> ${toDisplay} (경로 ${pathLength}칸)` : `${fromDisplay} -> ${toDisplay}`,
    landingResultAt: (summary: string, tileDisplay: string) => `${summary} / ${tileDisplay}번 칸`,
    diceCard: (cards: string) => `주사위 카드 ${cards}`,
    diceRoll: (dice: string) => `주사위 ${dice}`,
    diceTotalSummary: (cardText: string, diceText: string, total: string | number) => {
      if (cardText && diceText) {
        return `${cardText} + ${diceText} = ${total}`;
      }
      if (cardText) {
        return `${cardText} = ${total}`;
      }
      if (diceText) {
        return `${diceText} = ${total}`;
      }
      return String(total);
    },
    landing: {
      purchaseSkip: "구매 없이 턴 종료",
      purchase: "토지 구매",
      rent: "렌트 지불",
      markResolved: "지목 처리",
      default: "도착 칸 처리",
    },
    heartbeat: {
      detail: (interval: number, dropCount: number) => `간격 ${interval}ms / 누락 ${dropCount}`,
      interval: (interval: string) => `간격 ${interval}`,
    },
    playerLabel: (playerId: number | string) => `P${playerId}`,
    readyStateLabel: (readyState: string) => {
      if (readyState === "ready") {
        return "상태 준비됨";
      }
      if (readyState === "not_ready") {
        return "상태 준비 안 됨";
      }
      return `상태 ${readyState}`;
    },
    workerModeSummary: (policyMode?: string, workerAdapter?: string, policyClass?: string, decisionStyle?: string) => {
      const parts: string[] = [];
      if (policyMode && policyMode !== "-") {
        parts.push(`모드 ${policyMode}`);
      }
      if (workerAdapter && workerAdapter !== "-") {
        parts.push(`어댑터 ${workerAdapter}`);
      }
      if (policyClass && policyClass !== "-") {
        parts.push(`클래스 ${policyClass}`);
      }
      if (decisionStyle && decisionStyle !== "-") {
        parts.push(`스타일 ${decisionStyle}`);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    actorDetail: (actor: string, detail: string) => `${actor} / ${detail}`,
    effectsList: (parts: string[]) => {
      const visible = parts.filter((part) => part && part.trim() && part.trim() !== "-");
      return visible.length > 0 ? visible.join(", ") : "-";
    },
    promptDetail: (actor: string, promptLabel: string) => `${actor} / ${promptLabel}`,
    decisionRequestedDetail: (
      actor: string,
      promptLabel: string,
      tileDisplay?: string,
      choiceCount?: number | null,
      workerSummary?: string
    ) => {
      const parts = [actor, promptLabel];
      if (tileDisplay && tileDisplay !== "-") {
        parts.push(`${tileDisplay}번 칸`);
      }
      if (typeof choiceCount === "number" && choiceCount > 0) {
        parts.push(`선택지 ${choiceCount}개`);
      }
      if (workerSummary && workerSummary !== "-") {
        parts.push(workerSummary);
      }
      return parts.join(" / ");
    },
    decisionAckDetail: (status: string, reason: string) => (reason && reason !== "-" ? `${status} (${reason})` : status),
    decisionResolvedDetail: (resolution: string, choice: string, workerSummary?: string) => {
      const head = choice && choice !== "-" ? `${resolution} (${choice})` : resolution;
      return workerSummary && workerSummary !== "-" ? `${head} / ${workerSummary}` : head;
    },
    decisionTimeoutFallbackDetail: (
      summary: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts = ["시간 초과 기본 처리"];
      if (summary && summary !== "-") {
        parts.push(summary);
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`실패 ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`폴백 ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `시도 ${attemptCount}/${attemptLimit}` : `시도 ${attemptCount}회`);
      }
      const modeSummary = koLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.join(" / ");
    },
    workerStatusDetail: (
      workerLabel: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      readyState?: string,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts: string[] = [];
      if (workerLabel && workerLabel !== "-") {
        parts.push(workerLabel);
      }
      if (readyState && readyState !== "-") {
        parts.push(koLocale.stream.readyStateLabel(readyState));
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`실패 ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`폴백 ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `시도 ${attemptCount}/${attemptLimit}` : `시도 ${attemptCount}회`);
      }
      const modeSummary = koLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    weatherDetail: (weather: string, effect: string) => (effect && effect !== "-" ? `${weather} / ${effect}` : weather),
    errorDetail: (code: string, message: string) => (code && code !== "-" ? `${code}: ${message}` : message),
    stalledWarning: (text: string) => `런타임 경고: ${text}`,
    tilePurchased: (tileDisplay: string, cost: unknown) => `${tileDisplay}번 칸 구매 / 비용 ${cost}`,
    markerTransferred: (from: unknown, to: unknown, flipped?: unknown) =>
      typeof flipped === "number" ? `[징표] P${from} -> P${to} (플립 P${flipped})` : `[징표] P${from} -> P${to}`,
    markQueued: (source: unknown, target: unknown, targetCharacter: string, effectType: string) => {
      const effect =
        effectType === "bandit_tax"
          ? "산적"
          : effectType === "hunter_pull"
            ? "추노꾼"
            : effectType === "baksu_transfer"
              ? "박수"
              : effectType === "manshin_remove_burdens"
                ? "만신"
                : "지목";
      return `[${effect}] P${source} -> P${target} / ${targetCharacter}`;
    },
    markTargetNone: (source: unknown, actorName: string) => `${actorName || `P${source}`} / 지목 가능한 대상이 없어 기본 처리`,
    markTargetMissing: (source: unknown, targetCharacter: string) =>
      `P${source} / 지목 대상 ${targetCharacter || "-"}을(를) 현재 차례 순서에서 찾지 못함`,
    markBlocked: (source: unknown, target: unknown, targetCharacter: string) =>
      `P${source} / P${target}${targetCharacter ? ` (${targetCharacter})` : ""} 지목이 공개 상태라 차단됨`,
    markerFlipDetail: (from: string, to: string) => `${from} -> ${to}`,
    rentPaid: (payer: unknown, owner: unknown, amount: unknown, tileDisplay: string) =>
      `P${payer} -> P${owner} / ${amount}냥 / ${tileDisplay}번 칸`,
    fortuneDrawn: (cardName: string) => `운수 공개 / ${cardName}`,
    fortuneResolved: (summary: string) => `운수 처리 / ${summary}`,
    lapRewardChosen: (actor: string, reward: string) => `${actor} / ${reward}`,
    lapRewardBundle: (parts: string[]) => koLocale.app.inlineSummary(parts),
    bankruptcy: (pid: unknown) => `P${pid} 파산`,
    winner: (winner: number) => `승자 P${winner}`,
    gameEndDefault: "게임 종료",
    lapReward: {
      cash: (cash: number) => `현금 +${cash}`,
      shards: (shards: number) => `조각 +${shards}`,
      coins: (coins: number) => `승점 +${coins}`,
    },
    manifestSync: "설정 정보 동기화",
    manifestSyncHash: (hash: string) => `설정 동기화 ${hash}`,
    markResolved: (source: number, target: number) => `[지목] P${source} -> P${target}`,
    markerFlip: "카드 뒤집기",
    fValueChange: {
      detail: (before: number, delta: number, after: number) => `종료 시간 ${before} + (${delta}) = ${after}`,
      label: "종료 시간 변경",
    },
    runtimeError: "런타임 오류",
    promptWaiting: (promptLabel: string) => `${promptLabel} 대기`,
  },
  theater: {
    coreActionTitle: "최근 공개 행동",
    coreActionDescription: "이동, 구매, 렌트, 운수, 날씨, 카드 효과처럼 모든 플레이어가 아는 진행 흐름을 모아 보여줍니다.",
    payoffSceneTitle: "같은 턴 결과 장면",
    turnFlowTitle: "같은 턴 흐름",
    turnFlowEmpty: "아직 같은 턴 안에서 이어진 공개 행동이 없습니다.",
    roundTurnBadge: (round: number | null, turn: number | null) =>
      round !== null && turn !== null ? `${round}라운드 / ${turn}턴` : "라운드 / 턴 정보 없음",
    latestPublicAction: "가장 최근 공개 행동",
    noDetail: "추가 정보 없음",
    actionKind: {
      move: "이동",
      economy: "경제",
      effect: "효과",
      decision: "선택",
      system: "진행",
    },
    actionKeywords: {
      move: ["말 이동", "이동", "주사위"],
      economy: ["토지 구매", "렌트", "현금", "조각", "승점"],
      effect: ["운수", "날씨", "잔꾀", "카드 뒤집기", "지목"],
      decision: ["선택", "지목 대상"],
    } as const,
    toneBadge: {
      move: "이동",
      economy: "경제",
      critical: "중요",
      system: "진행",
    },
    panelLead: {
      move: "말의 이동과 목적지 요약을 먼저 보여줍니다.",
      economy: "구매, 렌트, 보상, 비용 변화를 요약합니다.",
      effect: "날씨, 운수, 잔꾀, 카드 효과를 보여줍니다.",
      decision: "선택 요청과 응답 흐름을 표시합니다.",
      system: "연결, 복구, 경고, 오류를 표시합니다.",
    },
    detailHeading: {
      move: "이동 상세",
      economy: "경제 상세",
      effect: "효과 상세",
      decision: "선택 상세",
      system: "시스템 상세",
    },
    payoffBeat: {
      tile_purchased: "구매 결과",
      rent_paid: "렌트 결과",
      fortune_drawn: "운수 공개",
      fortune_resolved: "운수 효과",
      lap_reward_chosen: "보상 결과",
    },
    payoffBeatIndex: (index: number, total: number, label: string) => `${index}/${total} ${label}`,
    incidentTitle: "턴 극장",
    incidentDescription: "턴 진행, 선택 요청, 시스템 기록을 분리해서 현재 게임의 흐름을 따라갑니다.",
    laneBadge: {
      core: "핵심",
      prompt: "선택",
      system: "시스템",
    },
    laneTitle: {
      core: "턴 진행",
      prompt: "선택 요청",
      system: "시스템 기록",
    },
    laneDescription: {
      core: "이동, 구매, 렌트, 운수, 효과 같은 공개 진행을 보여줍니다.",
      prompt: "선택 요청, 응답, 시간 초과 기본 처리를 모아둡니다.",
      system: "연결 상태, 복구, 경고, 오류를 표시합니다.",
    },
    laneEmpty: {
      core: "아직 공개 행동이 없습니다.",
      prompt: "아직 선택 요청 기록이 없습니다.",
      system: "아직 시스템 기록이 없습니다.",
    },
    expand: "펼치기",
    collapse: "접기",
  },
  turnStage: {
    title: "턴 극장 상단",
    description: "날씨, 인물, 이동, 도착 처리, 카드 효과를 이번 턴 기준으로 묶어 보여줍니다.",
    myTurn: "내 턴",
    observing: "관전 중",
    actorHeadline: (actor: string) => `${actor}의 진행`,
    actorWaiting: "행동자 정보 대기 중",
    weatherTitle: "현재 라운드 날씨",
    weatherBadge: "날씨",
    characterTitle: "선택 인물",
    characterBadge: "인물",
    movementTitle: "이동 처리",
    movementBadge: "주사위 / 이동",
    landingTitle: "도착 칸 처리",
    landingBadge: "구매 / 렌트",
    cardEffectTitle: "카드 효과",
    cardEffectBadge: "잔꾀 / 운수",
    currentBeatTitle: "현재 단계",
    currentBeatBadge: "단계",
    sceneSequenceTitle: "이번 턴 장면",
    sceneSequenceBadge: "장면",
    resultSequenceTitle: "이번 턴 결과",
    resultSequenceBadge: "결과",
    progressTitle: "턴 흐름",
    progressBadge: "흐름",
    workerTitle: "참가자 상태",
    workerBadge: "worker",
    actorStatusTitle: "현재 행동자 상태",
    actorStatusBadge: "자원",
    fields: {
      dice: "주사위",
      move: "이동",
      landing: "도착",
      purchase: "구매",
      rent: "렌트",
      trick: "잔꾀",
      fortune: "운수",
      decision: "선택",
      beat: "현재 행동",
      cash: "현금",
      shards: "조각",
      handCoins: "손 승점",
      placedCoins: "배치 승점",
      totalScore: "총점",
      ownedTiles: "소유 토지",
    },
    promptIdle: "선택 요청 없음",
    progressEmpty: "아직 이번 턴의 진행 기록이 없습니다.",
    workerStatusLabel: (status: string) => {
      if (status === "pending") {
        return "외부 worker 대기 중";
      }
      if (status === "resolved_by_worker") {
        return "외부 worker 처리 완료";
      }
      if (status === "worker_failed") {
        return "외부 worker 실패";
      }
      if (status === "resolved_by_local_fallback") {
        return "로컬 폴백 처리";
      }
      return status || "-";
    },
    workerStatusSummary: (
      status: string,
      workerId?: string,
      failureCode?: string,
      fallbackMode?: string,
      attemptCount?: number | null,
      attemptLimit?: number | null,
      readyState?: string,
      policyMode?: string,
      workerAdapter?: string,
      policyClass?: string,
      decisionStyle?: string
    ) => {
      const parts: string[] = [];
      const label = status && status !== "-" ? koLocale.turnStage.workerStatusLabel(status) : "";
      if (label) {
        parts.push(label);
      }
      if (readyState && readyState !== "-") {
        parts.push(koLocale.stream.readyStateLabel(readyState));
      }
      if (workerId && workerId !== "-") {
        parts.push(`worker ${workerId}`);
      }
      if (failureCode && failureCode !== "-") {
        parts.push(`실패 ${failureCode}`);
      }
      if (fallbackMode && fallbackMode !== "-") {
        parts.push(`폴백 ${fallbackMode}`);
      }
      if (typeof attemptCount === "number" && attemptCount > 0) {
        parts.push(typeof attemptLimit === "number" && attemptLimit > 0 ? `시도 ${attemptCount}/${attemptLimit}` : `시도 ${attemptCount}회`);
      }
      const modeSummary = koLocale.stream.workerModeSummary(policyMode, workerAdapter, policyClass, decisionStyle);
      if (modeSummary !== "-") {
        parts.push(modeSummary);
      }
      return parts.length > 0 ? parts.join(" / ") : "-";
    },
    weatherSummaryLine: (weatherName: string, weatherEffect: string) =>
      weatherEffect && weatherEffect !== "-" ? `${weatherName} / ${weatherEffect}` : weatherName,
    roundTurnLabel: (round: number | null, turn: number | null) => `R${round ?? "-"} / T${turn ?? "-"}`,
    turnStartDetail: (actor: string) => `${actor} / 턴 시작`,
    sequenceIndex: (index: number, total: number) => `${index}/${total}`,
    sequenceBeat: {
      weather: "이번 턴 날씨 효과 반영",
      purchase: "도착 직후 구매 판단",
      rent: "상대 소유 칸 렌트 정산",
      fortuneDraw: "운수 카드 공개",
      fortuneResolved: "운수 효과 반영",
      lapReward: "완주 보상 처리",
      mark: "지목 대상 효과 처리",
      flip: "현재 액티브 카드 뒤집기",
    },
  },
  prompt: {
    noChoiceDescription: "선택지가 아직 없습니다.",
    hiddenCardName: "히든 카드",
    hiddenCardDescription: (name: string) => `${name} 효과`,
    hiddenState: {
      hidden: "히든 잔꾀",
      public: "공개 잔꾀",
      usable: "사용 가능",
      unavailable: "지금 사용 불가",
    },
    collapsedChip: (label: string, secondsLeft: number | null) => `선택 요청: ${label} / 남은 시간 ${secondsLeft ?? "-"}초`,
    headTitle: (label: string) => `선택 요청: ${label}`,
    collapse: "접기",
    expand: "펼치기",
    secondaryChoiceBadge: "보조 선택",
    requestMetaPills: (playerId: number, timeoutMs: number, secondsLeft: number | null) => [
      `행동자 P${playerId}`,
      `제한 ${Math.ceil(timeoutMs / 1000)}초`,
      `남은 시간 ${secondsLeft ?? "-"}초`,
    ],
    requestCompactMetaPills: (playerId: number, secondsLeft: number | null) => [`P${playerId}`, `남은 ${secondsLeft ?? "-"}초`],
    requestMeta: (requestId: string, playerId: number, timeoutMs: number, secondsLeft: number | null) =>
      `요청 ID ${requestId} / 행동자 P${playerId} / 제한 시간 ${Math.ceil(timeoutMs / 1000)}초 / 남은 시간 ${secondsLeft ?? "-"}초`,
    context: {
      currentPosition: "현재 위치",
      usableCards: "사용 가능 카드",
      selectedCards: "선택 카드",
      currentWeather: "현재 날씨",
      actorCharacter: "행동 인물",
      selectableTargets: "선택 가능 대상",
      targetRule: "지목 규칙",
      trigger: "발동 원인",
      burdenCard: "대상 짐",
      burdenCost: "제거 비용",
      currentF: "현재 F",
      supplyThreshold: "보급 기준",
      purchaseCost: "구매 비용",
      currentCash: "보유 현금",
      zone: "구역",
      currentShards: "현재 조각",
      currentCoins: "현재 승점",
      currentPlacedCoins: "배치 승점",
      currentTotalScore: "총 승점",
      ownedTiles: "보유 토지",
      rewardBudget: "보상 예산",
      rewardPools: "남은 보상 풀",
      draftPhase: "드래프트 단계",
      targetTiles: "대상 토지",
      noneSelected: "없음",
      burdenExchangeTrigger: (threshold: number | null, currentF: number | null) => {
        if (threshold !== null && currentF !== null) {
          return `보급 단계 (F ${currentF} / 기준 ${threshold})`;
        }
        if (threshold !== null) {
          return `보급 단계 (기준 F ${threshold})`;
        }
        return "보급 단계";
      },
      markTargetRule: (targetCount: number | null) =>
        targetCount === 0
          ? "이번 라운드 뒤 순번의 비공개 인물이 없어 지목할 대상이 없습니다."
          : "이번 라운드 뒤 순번의 아직 공개되지 않은 인물만 지목할 수 있습니다.",
    },
    movement: {
      rollMode: "주사위 굴리기",
      cardMode: "주사위 카드 사용",
      cardGuide: (limit: number) => `사용할 주사위 카드를 선택하세요. 최대 ${limit}장까지 사용할 수 있습니다.`,
      rollButton: "주사위 굴리기",
      rollWithCardsButton: (cards: number[]) => `주사위 굴리기(주사위 카드 ${cards.join(", ")} 사용)`,
      selectCardsFirst: "주사위 카드를 먼저 선택하세요.",
    },
    trick: {
      usePrompt: "[사용할 잔꾀를 선택하세요]",
      hiddenPrompt: "[이번 라운드에 히든으로 지정할 잔꾀를 선택하세요]",
      handSummary: (count: number, hiddenCount?: number) =>
        `손패 전체 ${count}장${typeof hiddenCount === "number" ? ` / 히든 ${hiddenCount}장` : ""}`,
      skipTitle: "[이번에는 사용 안 함]",
      skipDescription: "[이번에는 잔꾀를 사용하지 않습니다.]",
    },
    character: {
      draftPrompt: "[드래프트 후보 중 1장을 가져가세요]",
      finalPrompt: "[최종으로 사용할 인물을 고르세요]",
      ability: (name: string) => `[${name} 능력]`,
      draftPhaseLabel: (phase: number | null) => (phase !== null ? `${phase}차 드래프트` : "드래프트"),
      finalPhaseLabel: "최종 확정",
    },
    mark: {
      noneTitle: "[지목 안 함]",
      noneDescription: "[이번에는 지목 효과를 사용하지 않습니다.]",
      title: (target: string) => `[${target}]`,
      description: (targetCharacter: string, targetPlayerId: number) => `[대상 인물 / 플레이어: ${targetCharacter} / P${targetPlayerId}]`,
      fallbackDescription: "[지목 대상을 선택하세요]",
    },
    choice: {
      noChoices: "선택 가능한 항목이 없습니다.",
      cashTitle: "현금 선택",
      shardTitle: "조각 선택",
      coinTitle: "승점 선택",
      cashReward: (amount: number) => `현금 +${amount}`,
      shardReward: (amount: number) => `조각 +${amount}`,
      coinReward: (amount: number) => `승점 +${amount}`,
      mixedReward: (cash: number, shards: number, coins: number, spent: number | null, budget: number | null) => {
        const parts = [];
        if (cash > 0) parts.push(`현금 +${cash}`);
        if (shards > 0) parts.push(`조각 +${shards}`);
        if (coins > 0) parts.push(`승점 +${coins}`);
        if (spent !== null && budget !== null) parts.push(`예산 ${spent}/${budget}`);
        return parts.join(" / ");
      },
      buyTileTitle: "토지 구매",
      buyTile: (pos: number | null, cost: number | null) =>
        pos !== null && cost !== null ? `${pos + 1}번 칸 / 비용 ${cost}` : "도착한 칸의 토지를 구매합니다.",
      skipPurchaseTitle: "구매 없이 턴 종료",
      skipPurchase: "구매하지 않고 현재 턴을 종료합니다.",
      endFlip: "뒤집기 종료",
      endFlipDescription: "더 이상 카드를 뒤집지 않고 종료합니다.",
      flipChange: (current: string, next: string) => `${current} -> ${next}`,
      flipDescription: "선택한 카드를 반대 면으로 뒤집습니다.",
      exchangeBurden: "짐 카드 교환",
      exchangeBurdenDescription: (cardName: string | null, cost: number | null, trigger: string) =>
        `${trigger}${cardName ? ` / ${cardName}` : ""}${cost !== null ? ` / 비용 ${cost}` : ""}`,
      keepBurdenTitle: "이번에는 유지",
      keepBurdenDescription: (cardName: string | null, trigger: string) =>
        `${trigger}에는${cardName ? ` ${cardName}` : " 이 짐 카드"}를 유지합니다.`,
      skip: "건너뜀",
    },
    busy: "처리 중... 엔진 응답을 기다리는 중",
  },
} as const;
