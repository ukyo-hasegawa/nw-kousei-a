import socket
import threading
import json

PORT = 8080

def log(*args):
    print(*args)

class OthelloGame:
    def __init__(self, board_size=8):
        self.board_size = board_size
        self.board = [[None] * board_size for _ in range(board_size)]
        self.turn = "black"
        self.case = "CONTINUE"

    def initialize_board(self):
        c = self.board_size // 2
        self.board[c - 1][c - 1] = "white"
        self.board[c][c] = "white"
        self.board[c - 1][c] = "black"
        self.board[c][c - 1] = "black"

    def is_valid_move(self, row, col, color):
        if self.board[row][col] is not None:
            return False
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                return True
        return False

    def _check_direction(self, r, c, dr, dc, color):
        opponent = "white" if color == "black" else "black"
        r += dr; c += dc
        if not (0 <= r < self.board_size and 0 <= c < self.board_size):
            return False
        if self.board[r][c] != opponent:
            return False
        while 0 <= r < self.board_size and 0 <= c < self.board_size:
            if self.board[r][c] is None:
                return False
            if self.board[r][c] == color:
                return True
            r += dr; c += dc
        return False

    def place_and_flip(self, row, col, color):
        self.board[row][col] = color
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                self._flip_direction(row, col, dr, dc, color)

    def _flip_direction(self, r, c, dr, dc, color):
        opponent = "white" if color == "black" else "black"
        r += dr; c += dc
        while self.board[r][c] == opponent:
            self.board[r][c] = color
            r += dr; c += dc

    def any_valid(self, color):
        for r in range(self.board_size):
            for c in range(self.board_size):
                if self.is_valid_move(r, c, color):
                    return True
        return False

    def full(self):
        return all(cell is not None for row in self.board for cell in row)

class GameSession:
    def __init__(self, players, colors):
        self.players = players
        self.colors = colors
        self.watchers = []
        self.game = OthelloGame()
        self.lock = threading.Lock()
        self.start_session()

    def start_session(self):
        log("Starting new game session between", self.colors)
        self.game.initialize_board()
        self.broadcast_state()
        for idx, conn in enumerate(self.players):
            threading.Thread(target=self.handle_client, args=(conn, idx), daemon=True).start()

    def add_watcher(self, conn):
        self.watchers.append(conn)
        log("New watcher joined")
        try:
            state = json.dumps({
                "board": self.game.board,
                "turn": self.game.turn,
                "case": self.game.case
            }).encode()
            conn.sendall(state)
        except Exception as e:
            log("Failed to send state to watcher:", e)

    def broadcast_state(self):
        data = {
            "board": self.game.board,
            "turn": self.game.turn,
            "case": self.game.case
        }
        payload = json.dumps(data).encode()
        for c in self.players + self.watchers:
            try:
                c.sendall(payload)
            except Exception as e:
                log("Error sending state:", e)

    def handle_client(self, conn, idx):
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
                    if turn == self.game.turn and self.game.is_valid_move(y, x, turn):
                        self.game.place_and_flip(y, x, turn)
                        next_color = "white" if turn == "black" else "black"
                        if self.game.any_valid(next_color):
                            self.game.case = "CONTINUE"
                            self.game.turn = next_color
                        elif self.game.full():
                            self.game.case = "FINISH"
                        else:
                            self.game.case = "PASS"
                    self.broadcast_state()
            except Exception as e:
                log("Error in session handle:", e)
                break
        conn.close()

if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen()

    waiting_players = []
    current_session = None
    log(f"Server listening on port {PORT}")

    while True:
        conn, addr = server.accept()
        log("Client connected:", addr)
        
        try:
            msg = conn.recv(1024)
            client_info = json.loads(msg.decode())
            client_type = client_info.get("client_type", "player")
            log("client type:", client_type)
        except Exception as e:
            log("Failed to receive client_type:", e)
            conn.close()
            continue

        if client_type == "watcher":
            if current_session:
                current_session.add_watcher(conn)
            else:
                log("No session available yet.")
                conn.sendall(json.dumps({"error": "No active game"}).encode())
                conn.close()
        else:
            waiting_players.append(conn)
            if len(waiting_players) >= 2:
                pair = waiting_players[:2]
                waiting_players = waiting_players[2:]
                for c, col in zip(pair, ["black", "white"]):
                    c.sendall(json.dumps({"player_color": col}).encode())
                    c.recv(1024)  # Wait for Setting_OK
                current_session = GameSession(pair, ["black", "white"])
