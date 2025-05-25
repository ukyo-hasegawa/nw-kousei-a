import socket
import threading
import json
import time # タイムアウトや遅延のため

PORT = 8080
SERVER_SHUTDOWN_EVENT = threading.Event() # サーバーシャットダウン用

def log(*args):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]", *args)

class OthelloGame:
    def __init__(self, board_size=8):
        self.board_size = board_size
        self.board = [[None] * board_size for _ in range(board_size)]
        self.turn = "black"  # 最初の手番は黒
        self.case = "CONTINUE" # "CONTINUE", "PASS", "FINISH", "FORCED_TERMINATION"
        self.message = "" # FORCED_TERMINATION時のメッセージなど

    def initialize_board(self):
        center = self.board_size // 2
        self.board[center - 1][center - 1] = "white"
        self.board[center][center] = "white"
        self.board[center - 1][center] = "black"
        self.board[center][center - 1] = "black"
        self.turn = "black" # 初期化時は必ず黒番から
        self.case = "CONTINUE"
        self.message = ""

    def is_valid_move(self, row, col, color):
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False
        if self.board[row][col] is not None:
            return False
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                return True
        return False

    def _check_direction(self, r_start, c_start, dr, dc, color):
        opponent = "white" if color == "black" else "black"
        r, c = r_start + dr, c_start + dc
        if not (0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == opponent):
            return False
        r += dr; c += dc
        while 0 <= r < self.board_size and 0 <= c < self.board_size:
            if self.board[r][c] is None:
                return False
            if self.board[r][c] == color:
                return True
            r += dr; c += dc
        return False

    def place_and_flip(self, row, col, color):
        if not self.is_valid_move(row, col, color): # 事前チェックは行うべき
            log(f"Warning: place_and_flip called with invalid move ({row},{col}) for {color}")
            return False # 不正な手なら何もしない

        self.board[row][col] = color
        directions = [(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
        flipped_any = False
        for dr, dc in directions:
            if self._check_direction(row, col, dr, dc, color):
                self._flip_direction(row, col, dr, dc, color)
                flipped_any = True
        return flipped_any # 実際に反転が起きたか (is_valid_moveがTrueなら通常True)

    def _flip_direction(self, r_start, c_start, dr, dc, color):
        opponent = "white" if color == "black" else "black"
        r, c = r_start + dr, c_start + dc
        while 0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == opponent:
            self.board[r][c] = color
            r += dr; c += dc

    def any_valid_moves(self, color):
        for r in range(self.board_size):
            for c in range(self.board_size):
                if self.is_valid_move(r, c, color):
                    return True
        return False

    def is_full(self):
        return all(cell is not None for row in self.board for cell in row)
    
class GameSession:
    def __init__(self, clients, colors, initial_spectators):
        self.clients = clients  # [conn1, conn2] (プレイヤー)
        self.colors = colors    # ["black", "white"]
        self.game = OthelloGame()
        self.lock = threading.Lock()
        self.current_spectators = [] # このゲームセッションの観戦者ソケットリスト
        self.player_threads = []
        self.session_active = True

        log(f"Starting new game session between {self.clients[0].getpeername()} ({colors[0]}) and {self.clients[1].getpeername()} ({colors[1]})")
        self.game.initialize_board()

        # 初期観戦者を追加
        for spec_conn in initial_spectators:
            self.add_spectator(spec_conn, send_initial_state=False) # 初期盤面は最初のbroadcastで送る

        self.broadcast_state() # 初期盤面と手番を送信

        for idx, conn in enumerate(self.clients):
            thread = threading.Thread(target=self.handle_player, args=(conn, idx), daemon=True)
            self.player_threads.append(thread)
            thread.start()

    def add_spectator(self, spectator_conn, send_initial_state=True):
        with self.lock:
            if spectator_conn not in self.current_spectators and self.session_active:
                self.current_spectators.append(spectator_conn)
                log(f"Spectator {spectator_conn.getpeername()} added to game session.")
                if send_initial_state:
                    try:
                        current_state = {
                            "board": self.game.board,
                            "turn": self.game.turn,
                            "case": self.game.case, # 通常は "CONTINUE"
                            "message": "Spectating ongoing game.",
                            "type": "initial_spectate"
                        }
                        spectator_conn.sendall(json.dumps(current_state).encode())
                    except Exception as e:
                        log(f"Error sending initial state to new spectator {spectator_conn.getpeername()}: {e}")
                        self._remove_spectator_socket(spectator_conn) # 送信失敗したらリストから除く
            elif not self.session_active:
                log(f"Game session is not active. Cannot add spectator {spectator_conn.getpeername()}.")
                try: spectator_conn.close() # セッション非アクティブなら観戦不可
                except: pass


    def _remove_spectator_socket(self, spectator_conn):
        #ロックは呼び出し元で取得想定
        if spectator_conn in self.current_spectators:
            self.current_spectators.remove(spectator_conn)
            log(f"Spectator {spectator_conn.getpeername()} removed from session.")
        try:
            spectator_conn.close()
        except Exception:
            pass

    def broadcast_state(self):
        if not self.session_active:
            return

        with self.lock: # gameオブジェクトへのアクセスを保護
            data = {
                "board": self.game.board,
                "turn": self.game.turn,
                "case": self.game.case,
                "message": self.game.message
            }
        payload = json.dumps(data).encode()

        active_clients_after_broadcast = []
        for c in self.clients:
            try:
                c.sendall(payload)
                active_clients_after_broadcast.append(c)
            except Exception as e:
                log(f"Error sending state to player {c.getpeername()}: {e}. Player will be marked for removal.")
                # 実際の削除は handle_player の切断検知に任せるか、ここで能動的に行う
                # ここで削除すると、handle_player内での処理と競合する可能性
        # self.clients = active_clients_after_broadcast # ここでリストを更新すると問題が起きやすい

        current_spectators_copy = list(self.current_spectators) # イテレーション中の変更を避ける
        for s_conn in current_spectators_copy:
            try:
                s_conn.sendall(payload)
            except Exception as e:
                log(f"Error sending state to spectator {s_conn.getpeername()}: {e}. Removing spectator.")
                with self.lock:
                    self._remove_spectator_socket(s_conn)

        if self.game.case in ["FINISH", "FORCED_TERMINATION"]:
            log(f"Game ended. Case: {self.game.case}. Message: {self.game.message}")
            self.end_session()


    def handle_player(self, conn, player_idx):
        player_color = self.colors[player_idx]
        log(f"Handler started for player {player_color} ({conn.getpeername()})")

        try:
            while self.session_active:
                if SERVER_SHUTDOWN_EVENT.is_set(): break
                try:
                    raw = conn.recv(1024)
                    if not raw:
                        log(f"Player {player_color} ({conn.getpeername()}) disconnected (received empty).")
                        self.notify_disconnection(conn, player_color)
                        return # スレッド終了
                except socket.timeout: # タイムアウト設定している場合
                    continue
                except (socket.error, ConnectionResetError, BrokenPipeError) as e:
                    log(f"Socket error with player {player_color} ({conn.getpeername()}): {e}. Player disconnected.")
                    self.notify_disconnection(conn, player_color)
                    return # スレッド終了

                try:
                    move = json.loads(raw.decode())
                    # log(f"Received from {player_color}: {move}")
                except json.JSONDecodeError:
                    log(f"Invalid JSON from {player_color} ({conn.getpeername()}): {raw.decode()[:100]}")
                    # 不正なデータなので接続を切るか、エラーを返すか。ここでは無視して次の入力を待つこともできるが危険。
                    # self.notify_disconnection(conn, player_color, "Invalid data received")
                    continue # 今回は次の入力を待つ形にするが、通常は切断推奨

                # クライアントからの切断通知
                if move.get("action") == "disconnect":
                    log(f"Player {player_color} ({conn.getpeername()}) sent disconnect message.")
                    self.notify_disconnection(conn, player_color, "Player initiated disconnect")
                    return


                # ゲームロジックはロック内で処理
                with self.lock:
                    if not self.session_active: return # セッションが終了していたら処理しない

                    # 自分のターンか、正しい色が送られてきたか
                    if move.get("turn") != player_color:
                        log(f"Move from {player_color} but message turn is {move.get('turn')}. Ignoring.")
                        # エラーをクライアントに返すことも検討
                        # conn.sendall(json.dumps({"error": "Not your color in message"}).encode())
                        continue
                    if self.game.turn != player_color:
                        log(f"Not {player_color}'s turn (game turn is {self.game.turn}). Ignoring move.")
                        # conn.sendall(json.dumps({"error": "Not your turn"}).encode())
                        continue

                    x, y = move.get("x"), move.get("y")
                    if x is None or y is None:
                        log(f"Invalid move format from {player_color}: {move}")
                        continue

                    if self.game.is_valid_move(y, x, player_color):
                        self.game.place_and_flip(y, x, player_color)
                        next_player_color = "white" if player_color == "black" else "black"

                        if self.game.any_valid_moves(next_player_color):
                            self.game.turn = next_player_color
                            self.game.case = "CONTINUE"
                        elif self.game.any_valid_moves(player_color): # 相手に手がないが自分にはまだ手がある場合 (パス)
                            self.game.turn = player_color # 手番は変わらず、相手がパスしたことになる
                            self.game.case = "PASS"
                            self.game.message = f"{next_player_color.capitalize()} has no moves and passes."
                        else: # 両者ともに手がない、または盤面が埋まった
                            self.game.case = "FINISH"
                            self.game.message = "No valid moves for both players. Game over."
                        
                        if self.game.is_full() and self.game.case != "FINISH":
                             self.game.case = "FINISH"
                             self.game.message = "Board is full. Game over."

                    else: # 不正な手
                        log(f"Invalid move ({y},{x}) by {player_color}. Board not changed.")
                        # 不正な手を打ったことをクライアントに通知しても良い
                        error_data = {
                            "board": self.game.board, "turn": self.game.turn, "case": "ERROR",
                            "message": f"Invalid move at ({y},{x}). Try again."
                        }
                        try: conn.sendall(json.dumps(error_data).encode())
                        except: pass
                        continue # 盤面更新せずに次の入力を待つ

                    self.game.message = "" # 通常のCONTINUEならメッセージはクリア
                    if self.game.case == "PASS":
                        self.game.message = f"{('White' if self.game.turn == 'black' else 'Black')} has no valid moves. Pass."


                self.broadcast_state() # 状態変更後にブロードキャスト

                if self.game.case in ["FINISH", "FORCED_TERMINATION"]:
                    return # ゲーム終了なのでハンドラも終了

        except Exception as e:
            log(f"Unexpected error in player handler for {player_color} ({conn.getpeername()}): {e}")
            self.notify_disconnection(conn, player_color, f"Unexpected error: {e}")
        finally:
            log(f"Handler for player {player_color} ({conn.getpeername()}) ended.")
            # conn.close() は notify_disconnection や end_session で行われる


    def notify_disconnection(self, disconnected_conn, disconnected_player_color, reason="Player disconnected"):
        global active_game_session # グローバル変数を更新するため
        with self.lock:
            if not self.session_active: return #既に終了処理済みなら何もしない
            self.session_active = False # まずセッションを非アクティブに

            log(f"Player {disconnected_player_color} ({disconnected_conn.getpeername()}) disconnected. Reason: {reason}")

            if disconnected_conn in self.clients:
                self.clients.remove(disconnected_conn)
            try:
                disconnected_conn.close()
            except Exception as e:
                log(f"Error closing disconnected player socket: {e}")

            self.game.case = "FORCED_TERMINATION"
            self.game.message = f"Player {disconnected_player_color.capitalize()} disconnected. {reason}. Game over."

        self.broadcast_state() # 最終状態をブロードキャスト (これによりend_sessionも呼ばれる)
        
        # end_session内で他のクライアントもクローズされる
        if active_game_session == self: #自分がアクティブセッションならクリア
            active_game_session = None
            log("Active game session cleared due to player disconnection.")


    def end_session(self):
        global active_game_session
        with self.lock:
            if not self.session_active and self.game.case not in ["FINISH", "FORCED_TERMINATION"]:
                # broadcast_stateから呼ばれる場合、既にsession_active=Falseになっていることがある
                # game.caseが終了状態でなければ、それは不整合の可能性
                pass
            self.session_active = False
            log(f"Ending game session. Final case: {self.game.case}")

            for c in self.clients:
                try: c.close()
                except Exception: pass
            self.clients.clear()

            for s_conn in self.current_spectators:
                try: s_conn.close()
                except Exception: pass
            self.current_spectators.clear()

        if active_game_session == self:
            active_game_session = None
            log("Active game session cleared after ending.")


# ------------------- グローバル変数とメイン処理 -------------------
waiting_players = [] # プレイヤーモードで接続し、相手を待っているクライアントのリスト [(conn, addr)]
global_spectators = [] # アクティブなゲームがない場合に待機している観戦者のリスト [conn]
active_game_session = None
main_server_socket = None # メインのサーバーソケット


def handle_new_connection(conn, addr):
    global waiting_players, global_spectators, active_game_session
    log(f"Handling new connection from: {addr}")
    try:
        conn.settimeout(10.0) # 10秒以内にモード情報が送られてくることを期待
        initial_data_raw = conn.recv(1024)
        conn.settimeout(None)

        if not initial_data_raw:
            log(f"Connection from {addr} closed before sending mode.")
            conn.close()
            return

        initial_data = json.loads(initial_data_raw.decode())
        client_mode = initial_data.get("mode", "player") # デフォルトはプレイヤー
        log(f"Client {addr} mode: {client_mode}, data: {initial_data}")

        if client_mode == "spectator":
            if active_game_session and active_game_session.session_active:
                active_game_session.add_spectator(conn)
            else:
                global_spectators.append(conn)
                log(f"Spectator {addr} added to global list ({len(global_spectators)} total), waiting for a game.")
                try:
                    conn.sendall(json.dumps({
                        "status": "waiting_for_game",
                        "message": "No active game. Waiting for a game to start or for players to connect."
                    }).encode())
                except Exception as e:
                    log(f"Error sending waiting message to spectator {addr}: {e}")
                    if conn in global_spectators: global_spectators.remove(conn)
                    conn.close()
        else: # player mode
            # プレイヤーは色設定の確認までこのスレッドで行う
            player_conn = conn
            player_addr = addr
            
            # クライアントからの最初のメッセージが色設定完了通知である場合もある
            # (クライアントが接続直後に色を期待して即座に "color_set" を送るパターン)
            is_color_set_message = initial_data.get("status") == "color_set" or "Setting_OK" in initial_data

            with threading.Lock(): # waiting_playersリスト操作の保護
                waiting_players.append((player_conn, player_addr, is_color_set_message, initial_data if is_color_set_message else None))
                log(f"Player {player_addr} added to waiting list. Total waiting: {len(waiting_players)}")

                if len(waiting_players) >= 2:
                    player1_info = waiting_players.pop(0)
                    player2_info = waiting_players.pop(0)
                    
                    p1_conn, p1_addr, p1_is_color_set, p1_initial_data = player1_info
                    p2_conn, p2_addr, p2_is_color_set, p2_initial_data = player2_info

                    pair = [(p1_conn, p1_addr), (p2_conn, p2_addr)]
                    colors_to_assign = ["black", "white"]
                    assigned_players_conn = []
                    assignment_ok = True

                    # 色割り当てと確認
                    for i, (p_conn, p_addr) in enumerate(pair):
                        color = colors_to_assign[i]
                        try:
                            p_conn.sendall(json.dumps({"player_color": color}).encode())
                            log(f"Sent color {color} to player {p_addr}")

                            # クライアントからの "Setting_OK" または "color_set" を待つ
                            # 既に最初のメッセージで受信済みの場合はそれを使う
                            if (i == 0 and p1_is_color_set):
                                response = p1_initial_data
                                log(f"Player {p_addr} pre-sent color confirmation: {response}")
                            elif (i == 1 and p2_is_color_set):
                                response = p2_initial_data
                                log(f"Player {p_addr} pre-sent color confirmation: {response}")
                            else:
                                p_conn.settimeout(10.0)
                                response_raw = p_conn.recv(1024)
                                p_conn.settimeout(None)
                                if not response_raw: raise ConnectionAbortedError("Client disconnected before confirming color.")
                                response = json.loads(response_raw.decode())
                                log(f"Received color confirmation from {p_addr}: {response}")

                            confirmed_color = response.get("color", response.get("Setting_OK"))
                            if (response.get("status") == "color_set" or "Setting_OK" in response) and confirmed_color == color:
                                log(f"Player {p_addr} confirmed color {color}.")
                                assigned_players_conn.append(p_conn)
                            else:
                                raise ValueError(f"Color confirmation failed or wrong color. Expected {color}, got {confirmed_color}. Full response: {response}")
                        except Exception as e:
                            log(f"Error during color assignment for player {p_addr} ({color}): {e}")
                            assignment_ok = False
                            # 失敗したプレイヤーは閉じる
                            try: p_conn.close()
                            except: pass
                            # もう片方のプレイヤーを待機リストに戻す
                            other_player_idx = 1 - i
                            other_p_conn, other_p_addr = pair[other_player_idx]
                            if other_p_conn in assigned_players_conn : # もし片方成功していたら
                                assigned_players_conn.remove(other_p_conn)
                                waiting_players.insert(0, (other_p_conn, other_p_addr, False, None)) # 待機リストの先頭に戻す
                                log(f"Returned player {other_p_addr} to waiting list.")
                            break # forループを抜ける
                    
                    if assignment_ok and len(assigned_players_conn) == 2:
                        log("Two players successfully assigned colors. Starting new game session.")
                        if active_game_session:
                            log("Warning: An active game session already exists. Ending it before starting a new one.")
                            active_game_session.end_session() # 古いセッションを強制終了
                            time.sleep(0.1) # 念のため少し待つ

                        current_game_spectators_list = list(global_spectators) # コピー
                        global_spectators.clear()
                        
                        active_game_session = GameSession(assigned_players_conn, colors_to_assign, current_game_spectators_list)
                    else:
                        log("Failed to set up a pair for the game. One or more players failed color assignment.")
                        # 失敗しなかったプレイヤーがいれば、待機リストに戻されているはず
                        # 既に接続が閉じられたプレイヤーは assigned_players_conn にはいない
                        for p_rem in assigned_players_conn: # もし万が一残っていたら閉じる
                             try: p_rem.close()
                             except: pass


    except (socket.timeout, json.JSONDecodeError) as e:
        log(f"Error handling new connection from {addr} (timeout or JSON error): {e}")
        try: conn.close()
        except: pass
    except ConnectionAbortedError as e: # クライアントが途中で切断
        log(f"Connection from {addr} aborted: {e}")
        try: conn.close()
        except: pass
    except Exception as e:
        log(f"Unexpected error handling new connection from {addr}: {e}")
        import traceback
        traceback.print_exc()
        try: conn.close()
        except: pass


def server_main():
    global main_server_socket, active_game_session
    main_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        main_server_socket.bind(("0.0.0.0", PORT))
    except OSError as e:
        log(f"Error binding to port {PORT}: {e}. Server cannot start.")
        return
        
    main_server_socket.listen()
    # main_server_socket.settimeout(1.0) # acceptにタイムアウトを設定してCtrl+Cを検知しやすくする
    log(f"Server listening on port {PORT}")

    try:
        while not SERVER_SHUTDOWN_EVENT.is_set():
            try:
                # タイムアウト付きでacceptし、シャットダウンイベントをチェックできるようにする
                main_server_socket.settimeout(1.0)
                conn, addr = main_server_socket.accept()
                main_server_socket.settimeout(None) # 通常のブロッキングモードに戻す
                
                threading.Thread(target=handle_new_connection, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue # タイムアウトは正常、ループを続ける
            except OSError as e: # サーバーソケットがクローズされた場合など
                 if SERVER_SHUTDOWN_EVENT.is_set():
                     log("Server socket closed as part of shutdown.")
                     break
                 else:
                     log(f"Error accepting connection: {e}") # それ以外のOSError
                     break # ループを抜けて終了処理へ

    except KeyboardInterrupt:
        log("KeyboardInterrupt received. Shutting down server...")
    finally:
        SERVER_SHUTDOWN_EVENT.set()
        log("Cleaning up server resources...")
        if active_game_session:
            log("Ending active game session due to server shutdown...")
            active_game_session.end_session() # アクティブなセッションを終了

        # 残っている待機プレイヤーや観戦者の接続を閉じる
        for p_conn, _, _, _ in waiting_players:
            try: p_conn.close()
            except: pass
        waiting_players.clear()
        for s_conn in global_spectators:
            try: s_conn.close()
            except: pass
        global_spectators.clear()

        if main_server_socket:
            main_server_socket.close()
            log("Main server socket closed.")
        log("Server shutdown complete.")


if __name__ == "__main__":
    server_main()