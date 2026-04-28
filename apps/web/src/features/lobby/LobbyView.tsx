import { type PublicRoomResult } from "../../infra/http/sessionApi";

export type LobbySeatType = "human" | "ai";

type LobbyViewProps = {
  busy: boolean;
  locale: string;
  serverBaseInput: string;
  serverConnected: boolean;
  roomTitleInput: string;
  nicknameInput: string;
  hostSeatInput: string;
  seatTypes: LobbySeatType[];
  activeRoom: PublicRoomResult | null;
  activeRoomSeat: number | null;
  rooms: PublicRoomResult[];
  notice: string;
  error: string;
  onServerBaseInput: (value: string) => void;
  onConnectServer: () => void;
  onRoomTitleInput: (value: string) => void;
  onNicknameInput: (value: string) => void;
  onHostSeatInput: (value: string) => void;
  onSeatTypeChange: (index: number, value: LobbySeatType) => void;
  onCreateRoom: () => void;
  onQuickStartHumanVsAi: () => void;
  onRefreshRooms: () => void;
  onJoinRoom: (roomNo: number, seat: number) => void;
  onToggleReady: (ready: boolean) => void;
  onStartRoom: () => void;
  onLeaveRoom: () => void;
};

function isKoreanLocale(locale: string): boolean {
  return locale.toLowerCase().startsWith("ko");
}

export function LobbyView({
  busy,
  locale,
  serverBaseInput,
  serverConnected,
  roomTitleInput,
  nicknameInput,
  hostSeatInput,
  seatTypes,
  activeRoom,
  activeRoomSeat,
  rooms,
  notice,
  error,
  onServerBaseInput,
  onConnectServer,
  onRoomTitleInput,
  onNicknameInput,
  onHostSeatInput,
  onSeatTypeChange,
  onCreateRoom,
  onQuickStartHumanVsAi,
  onRefreshRooms,
  onJoinRoom,
  onToggleReady,
  onStartRoom,
  onLeaveRoom,
}: LobbyViewProps) {
  const ko = isKoreanLocale(locale);
  const activeSeat = activeRoom?.seats.find((seat) => seat.seat === activeRoomSeat) ?? null;
  const canStart =
    activeRoom?.status === "waiting" &&
    activeRoomSeat === activeRoom?.host_seat &&
    activeRoom.human_joined_count === activeRoom.human_total_count &&
    activeRoom.human_ready_count === activeRoom.human_total_count;

  return (
    <div className="lobby-shell">
      <section className="panel">
        <div className="panel-head">
          <h2>{ko ? "서버 연결" : "Server Connection"}</h2>
        </div>
        <div className="lobby-grid">
          <label>
            {ko ? "서버 주소" : "Server address"}
            <input
              value={serverBaseInput}
              onChange={(event) => onServerBaseInput(event.target.value)}
              placeholder={ko ? "예: http://127.0.0.1:9090" : "e.g. http://127.0.0.1:9090"}
            />
          </label>
          <div className="actions">
            <button type="button" disabled={busy} onClick={onConnectServer}>
              {serverConnected ? (ko ? "다시 확인" : "Reconnect") : ko ? "연결" : "Connect"}
            </button>
            <button type="button" disabled={busy} onClick={onRefreshRooms}>
              {ko ? "방 목록 새로고침" : "Refresh rooms"}
            </button>
          </div>
        </div>
        {notice ? <p className="notice ok">{notice}</p> : null}
        {error ? <p className="notice err">{error}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>{ko ? "방 만들기" : "Create Room"}</h2>
        </div>
        <div className="lobby-grid">
          <label>
            {ko ? "닉네임" : "Nickname"}
            <input value={nicknameInput} onChange={(event) => onNicknameInput(event.target.value)} />
          </label>
          <label>
            {ko ? "방 제목" : "Room title"}
            <input value={roomTitleInput} onChange={(event) => onRoomTitleInput(event.target.value)} />
          </label>
          <label>
            {ko ? "호스트 좌석" : "Host seat"}
            <select value={hostSeatInput} onChange={(event) => onHostSeatInput(event.target.value)}>
              {seatTypes.map((_, index) => (
                <option key={`host-seat-${index + 1}`} value={String(index + 1)}>
                  {ko ? `${index + 1}번 좌석` : `Seat ${index + 1}`}
                </option>
              ))}
            </select>
          </label>
          <div className="seat-grid">
            {seatTypes.map((seatType, index) => (
              <label key={`seat-type-${index + 1}`}>
                {ko ? `${index + 1}번 좌석` : `Seat ${index + 1}`}
                <select
                  value={seatType}
                  onChange={(event) => onSeatTypeChange(index, event.target.value === "human" ? "human" : "ai")}
                >
                  <option value="human">{ko ? "사람" : "Human"}</option>
                  <option value="ai">AI</option>
                </select>
              </label>
            ))}
          </div>
          <div className="actions">
            <button type="button" disabled={busy || !serverConnected} onClick={onCreateRoom}>
              {ko ? "방 만들기" : "Create room"}
            </button>
            <button type="button" disabled={busy} onClick={onQuickStartHumanVsAi}>
              {ko ? "사람 1 + AI 3 빠른 시작" : "Quick start: 1 human + 3 AI"}
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>{ko ? `공개 방 (${rooms.length})` : `Open Rooms (${rooms.length})`}</h2>
        </div>
        <div className="timeline">
          {rooms.map((room) => (
            <article key={`room-${room.room_no}`} className="timeline-item">
              <strong>
                #{room.room_no} · {room.room_title}
              </strong>
              <span>
                {ko ? `사람 ${room.human_joined_count}/${room.human_total_count} · 준비 ${room.human_ready_count}` : `Humans ${room.human_joined_count}/${room.human_total_count} · Ready ${room.human_ready_count}`}
              </span>
              <small>{room.status}</small>
              <div className="token-actions">
                {room.seats
                  .filter((seat) => seat.seat_type === "human" && seat.player_id == null)
                  .map((seat) => (
                    <button
                      key={`room-${room.room_no}-seat-${seat.seat}`}
                      type="button"
                      disabled={busy || !serverConnected}
                      onClick={() => onJoinRoom(room.room_no, seat.seat)}
                    >
                      {ko ? `${seat.seat}번 좌석 참가` : `Join seat ${seat.seat}`}
                    </button>
                  ))}
              </div>
            </article>
          ))}
          {rooms.length === 0 ? <p>{ko ? "열린 방이 없습니다." : "No rooms are open."}</p> : null}
        </div>
      </section>

      {activeRoom ? (
        <section className="panel">
          <div className="panel-head">
            <h2>
              {ko ? "현재 방" : "Current Room"} #{activeRoom.room_no} · {activeRoom.room_title}
            </h2>
          </div>
          <div className="timeline">
            {activeRoom.seats.map((seat) => {
              const isMine = activeRoomSeat === seat.seat;
              const seatStatus =
                seat.seat_type === "ai"
                  ? "AI"
                  : seat.player_id == null
                    ? ko ? "빈 좌석" : "Open"
                    : seat.ready
                      ? ko ? "준비 완료" : "Ready"
                      : ko ? "대기 중" : "Waiting";
              return (
                <article key={`active-room-seat-${seat.seat}`} className="timeline-item">
                  <strong>
                    {ko ? `${seat.seat}번 좌석` : `Seat ${seat.seat}`} · {seat.nickname ?? (seat.seat_type === "ai" ? "AI" : ko ? "미참가" : "Open")}
                  </strong>
                  <span>{seat.seat_type === "ai" ? "AI" : ko ? "사람" : "Human"}</span>
                  <small>{isMine ? (ko ? "내 좌석" : "My seat") : seatStatus}</small>
                </article>
              );
            })}
          </div>
          <div className="actions">
            {activeSeat && activeSeat.seat_type === "human" ? (
              <button
                type="button"
                disabled={busy || activeRoom.status !== "waiting"}
                onClick={() => onToggleReady(!(activeSeat.ready === true))}
              >
                {activeSeat.ready ? (ko ? "준비 해제" : "Unready") : ko ? "준비" : "Ready"}
              </button>
            ) : null}
            <button type="button" disabled={busy || !canStart} onClick={onStartRoom}>
              {ko ? "게임 시작" : "Start game"}
            </button>
            <button type="button" disabled={busy || activeRoom.status !== "waiting"} onClick={onLeaveRoom}>
              {ko ? "방 나가기" : "Leave room"}
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
