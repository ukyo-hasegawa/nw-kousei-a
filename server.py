import socket
import threading
import json

PORT = 8080

def log(*args):
    print(*args)

class OthelloGame:
    def __init__(self, board_size=8):
        self.board_size = board_size
        # None で空き、"black" と "white" で石の状態を表現
        self.board = [[None] * board_size for _ in range(board_size)]
        self.turn = "black"
        self.case = "CONTINUE"  # プレイヤー間のやり取りを示す: "CONTINUE", "PASS", "FINISH"

    def initialize_board(self):
        # 初期盤面を中央に配置
        center = self.board_size // 2
        self.board[center - 1][center - 1] = "white"
        self.board[center][center]     = "white"
        self.board[center - 1][center] = "black"
        self.board[center][center - 1] = "black"

    def is_valid_move(self, row, col, color):
        # すでに駒がある場合は False
        if self.board[row][col] is not None:
            return False
        # 8方向を探索して挟めるか確認
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                return True
        return False

    def _check_direction(self, r, c, dr, dc, color):
        # 指定方向に相手色の石を挟んで自色に届くか
        opponent = "white" if color == "black" else "black"
        r += dr; c += dc
        # 盤外は False
        if not (0 <= r < self.board_size and 0 <= c < self.board_size):
            return False
        # 最初に隣接するのが相手色でなければ False
        if self.board[r][c] != opponent:
            return False
        # さらに進んで自色に到達すれば True
        while 0 <= r < self.board_size and 0 <= c < self.board_size:
            if self.board[r][c] is None:
                return False
            if self.board[r][c] == color:
                return True
            r += dr; c += dc
        return False

    def place_and_flip(self, row, col, color):
        # 駒を置いて、挟める方向の石をひっくり返す
        self.board[row][col] = color
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                self._flip_direction(row, col, dr, dc, color)

    def _flip_direction(self, r, c, dr, dc, color):
        # 指定方向に沿って相手色を自色にひっくり返す
        opponent = "white" if color == "black" else "black"
        r += dr; c += dc
        while self.board[r][c] == opponent:
            self.board[r][c] = color
            r += dr; c += dc

    def any_valid(self, color):
        # 次のプレイヤーに合法手が存在するか
        for r in range(self.board_size):
            for c in range(self.board_size):
                if self.is_valid_move(r, c, color):
                    return True
        return False

    def full(self):
        # 盤面がすべて埋まっているか
        return all(cell is not None for row in self.board for cell in row)

class GameSession:
    def __init__(self, clients, colors):
        self.clients = clients           # [conn1, conn2]
        self.colors = colors             # ["black", "white"]
        self.game = OthelloGame()
        self.lock = threading.Lock()
        self.start_session()

    def start_session(self):
        log("Starting new game session between", self.colors)
        # 初期盤面を設定して両クライアントに送信
        self.game.initialize_board()
        self.broadcast_state()
        # 各クライアントのハンドラーをデーモンスレッドで開始
        for idx, conn in enumerate(self.clients):
            threading.Thread(target=self.handle_client, args=(conn, idx), daemon=True).start()

    def broadcast_state(self):
        # 現在の盤面・ターン・ケースを全クライアントへ送信
        data = {
            "board": self.game.board,
            "turn": self.game.turn,
            "case": self.game.case
        }
        payload = json.dumps(data).encode()
        for c in self.clients:
            try:
                c.sendall(payload)
            except Exception as e:
                log("Error sending state:", e)

    def handle_client(self, conn, idx):
        # クライアントからの入力を受信し、ゲームを進行
        color = self.colors[idx]
        while True:
            try:
                raw = conn.recv(1024)
                if not raw:
                    log(f"Client {color} disconnected")
                    break
                move = json.loads(raw.decode())
                x, y, turn = move["x"], move["y"], move["turn"]
                with self.lock:
                    # ターンチェックと合法手チェック
                    if turn == self.game.turn and self.game.is_valid_move(y, x, turn):
                        self.game.place_and_flip(y, x, turn)
                        next_color = "white" if turn == "black" else "black"
                        # 次の手があるか、盤面満杯かでケースを設定
                        if self.game.any_valid(next_color):
                            self.game.case = "CONTINUE"
                            self.game.turn = next_color
                        elif self.game.full():
                            self.game.case = "FINISH"
                        else:
                            self.game.case = "PASS"
                            self.game.turn = next_color
                    # 更新をブロードキャスト
                    self.broadcast_state()
            except Exception as e:
                log("Error in session handle:", e)
                break
        conn.close()

# メインサーバー処理
if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen()

    waiting = []
    colors = ["black", "white"]
    log(f"Server listening on port {PORT}")

    # クライアント接続待機
    while True:
        conn, addr = server.accept()
        log("Client connected:", addr)
        waiting.append(conn)
        # 2 人揃ったらゲーム開始
        if len(waiting) >= 2:
            pair = waiting[:2]
            waiting = waiting[2:]
            # 色割り当てと確認
            for c, col in zip(pair, colors):
                c.sendall(json.dumps({"player_color": col}).encode())
                c.recv(1024)  # Setting_OK の確認
            GameSession(pair, colors)
