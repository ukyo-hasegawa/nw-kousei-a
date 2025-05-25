import socket
import tkinter as tk
import json
import threading
import argparse  # 追加: コマンドライン引数を扱う
import time  # リトライ時の待機のため追加
import signal # Ctrl+Cによる終了処理のため追加 (念のため確認)
import sys    # sys.exitのため追加 (念のため確認)

PORT = 8080
SERVER_IP = "192.168.1.15" #端末のローカルIPアドレス
MAX_CONNECT_RETRIES = 3
CONNECT_RETRY_DELAY = 5 # seconds
CONNECT_TIMEOUT = 10 # seconds

class Client:
    def __init__(self, host, port=PORT):  # hostは必須引数に変更
        self.server = (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        connected = False
        for attempt in range(MAX_CONNECT_RETRIES):
            try:
                print(f"サーバーへの接続試行中 ({attempt + 1}/{MAX_CONNECT_RETRIES})... {self.server}")
                self.socket.settimeout(CONNECT_TIMEOUT) # 接続タイムアウト設定
                self.socket.connect(self.server)
                self.socket.settimeout(None) # 通常のブロッキングモードに戻す
                print(f"サーバーに接続しました: {self.server}")
                connected = True
                break
            except socket.timeout:
                print(f"接続試行 ({attempt + 1}) がタイムアウトしました。")
            except (socket.error, ConnectionRefusedError) as e: # ConnectionRefusedError も捕捉
                print(f"接続試行 ({attempt + 1}) に失敗しました: {e}")
            
            if attempt < MAX_CONNECT_RETRIES - 1:
                print(f"{CONNECT_RETRY_DELAY}秒後に再試行します...")
                # ソケットを再作成する必要がある場合がある
                self.socket.close() # 古いソケットを閉じる
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # 新しいソケットを作成
                time.sleep(CONNECT_RETRY_DELAY)
        
        if not connected:
            print("サーバーへの接続に最終的に失敗しました。")
            # GUIに通知するために例外を発生させる
            raise ConnectionError("サーバーへの接続に失敗しました。リトライ上限に達しました。")

    def send(self, message): #データの送信のみを行う
        print(f"Send: {message}")
        self.socket.sendall(message.encode("utf-8"))
        return

    def close(self):
        print("Close")
        self.socket.close()

class ClientGUI:
    def __init__(self, root, host, port, mode="player"):  # host, port, mode を受け取る
        self.root = root
        self.root.title("Othello Client")
        self.player_color = None
        self.turn = "black"
        self.board_size = 8
        self.cell_size = 50
        self.is_spectator = (mode == "spectator") # 観戦モードかどうかのフラグ

        self.canvas = tk.Canvas(self.root, width=self.board_size * self.cell_size, height=self.board_size * self.cell_size)
        self.canvas.grid(row=0, column=0)
        
        initial_info_text = "観戦モードで接続中..." if self.is_spectator else "マッチング中..."
        self.info_label = tk.Label(self.root, text=initial_info_text)
        self.info_label.grid(row=1, column=0)
        
        if not self.is_spectator: # プレイヤーモードの場合のみクリックイベントをバインド
            self.canvas.bind("<Button-1>", self.handle_click)

        self.host = host
        self.port = port

        threading.Thread(target=self.connect_and_setup_game, daemon=True).start()

    def connect_and_setup_game(self):
            try:
        #step1:サーバーに接続し接続できたことを出力
                self.client = Client(self.host, self.port) # サーバー接続

        # ★★★ サーバーに自分のモードを通知 ★★★
                if self.is_spectator:
                    self.client.send(json.dumps({"mode": "spectator"}))
                    self.info_label.config(text="観戦モード - サーバーに接続しました")
                else: # プレイヤーモード
                    self.client.send(json.dumps({"mode": "player"}))
                    # Player color はまだサーバーから受信していないので、ここでは設定しない
                    self.info_label.config(text="プレイヤーモード - サーバーに接続、マッチング待機中...")

            except ConnectionError as e:
                error_message = f"サーバー接続エラー: {e}\nリトライ上限に達しました。"
                self.info_label.config(text=error_message, wraplength=self.board_size * self.cell_size) # メッセージが長い場合に折り返す
                print(f"ClientGUI: {error_message}")
                self.exit_button = tk.Button(self.root, text="終了", command=self.on_close)
                self.exit_button.grid(row=2, column=0, pady=10)
                return # スレッド終了

            # プレイヤーモードの場合、サーバーからの色割り当てを待つ (set_player_colorではなく、receive_updates_loopで処理する方が望ましい)
            if not self.is_spectator:
                # ここで set_player_color を直接呼び出すのはタイミングが早すぎる可能性があります。
        #        代わりに、サーバーが色情報を送ってくるのを receive_updates_loop で待つように変更することを推奨します。
                # 今回は、set_player_color のエラーハンドリングを強化して問題の切り分けをします。
                if not self.set_player_color(): # 色設定が失敗したら終了
                    # set_player_color内でエラーメッセージが表示される想定
                    if "サーバー接続または色割り当てに失敗しました。" not in self.info_label.cget("text") and \
                    "色情報の受信がタイムアウトしました。" not in self.info_label.cget("text") and \
                    "サーバーからの色情報が不正です。" not in self.info_label.cget("text") and \
                    "サーバーから色情報を受信できませんでした(空応答)。" not in self.info_label.cget("text"): # エラーメッセージ重複を避ける
                        self.info_label.config(text="サーバーからの色割り当てに失敗しました。")
                    # エラーが起きたら終了ボタンを出すなど、ユーザーに知らせる
                    if not hasattr(self, 'exit_button') or not self.exit_button.winfo_exists():
                        self.exit_button = tk.Button(self.root, text="終了", command=self.on_close)
                        self.exit_button.grid(row=2, column=0, pady=10)
                    return # スレッド終了
        # 色設定成功後
                self.info_label.config(text=f"あなたの色: {self.player_color} - 対戦相手を待っています...")
            else: # 観戦モード
                self.player_color = "spectator" #便宜的
                self.info_label.config(text="観戦モード - ゲーム開始待機中...")


    # サーバーから初期盤面データを受信するまで、マッチング中のラベルを表示
    # (この部分は、色情報や初期盤面情報がサーバーから送られてくるタイミングに合わせて調整が必要)

    #step3:サーバーから初期盤面データを受信し、初期盤面を描画する。
            self.create_sidebar() # 先にサイドバーは作成しておく
    # self.receive_initialboard_data() # 初期盤面は色情報と一緒に来るか、その後に来るべき
    # self.update_turn_display()
    # self.update_score()
    # if not self.is_spectator:
    #    self.highlight_valid_moves()

    # マッチング中のラベルを非表示、自分の色を表示
            if not self.is_spectator and self.player_color:
                self.info_label.config(text=f"Your color: {self.player_color} ")
            elif self.is_spectator:
                self.info_label.config(text="観戦モード")

    #step4: 石を置いて、サーバーに送信する(GUIをクリックしたときに、サーバーに送信する)、その結果となる盤面データを受信し、盤面を更新する。→受信したデータを元に盤面を更新し描画する。
            threading.Thread(target=self.receive_updates_loop, daemon=True).start()

    def initialize_board(self):
        self.board = [[None for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.board[3][3] = "white"
        self.board[3][4] = "black"
        self.board[4][3] = "black"
        self.board[4][4] = "white"

    def handle_click(self, event):
        if self.is_spectator: # 観戦モードではクリック操作を無効化
            print("Spectator mode: Cannot make moves.")
            return

        print("Handle click")
        col = event.x // self.cell_size
        row = event.y // self.cell_size

        if not (0 <= col < self.board_size and 0 <= row < self.board_size):
            return
        
        if self.turn != self.player_color:
            print("Not your turn!!!!")
            return

        if self.board[row][col] is None:
            # クリックされた手が有効かどうかのチェックはサーバー側で行う想定
            # is_valid_moveはクライアント側の表示用なので、送信自体は行う
            move = {"x": col, "y": row, "turn": self.player_color}
            self.client.send(json.dumps(move))

    def set_player_color(self):
        if self.is_spectator: # 観戦モードでは色設定は不要
            return True

        print("Receive player color")
        try:
            self.client.socket.settimeout(20.0) # ★タイムアウトを少し長めに設定★
            response_bytes = self.client.socket.recv(1024)
            self.client.socket.settimeout(None) # 通常のブロッキングモードに戻す

            if not response_bytes: # ★サーバーから空のデータが来た場合★
                print("Received empty response from server when expecting player color.")
                self.info_label.config(text="サーバーから色情報を受信できませんでした(空応答)。")
                return False

            response = response_bytes.decode("utf-8")
            data = json.loads(response)
            print(f"Received player color data: {data}")

            if "player_color" in data:
                self.player_color = data["player_color"]
                # self.info_label.config(text=f"Your color: {self.player_color}") # ここでの更新はconnect_and_setup_gameに任せる
                print(f"Player color set to: {self.player_color}")
                # 色設定が完了したことをサーバーに通知
                self.client.send(json.dumps({"status": "color_set", "color": self.player_color}))
                return True
            elif "error" in data: # サーバーがエラーを返してきた場合
                print(f"Server error during color assignment: {data['error']}")
                self.info_label.config(text=f"色割り当てエラー: {data['error']}")
                return False
            else:
                print("No player color in received data.")
                self.info_label.config(text="色情報が正しく受信できませんでした。")
                return False
        except socket.timeout:
            print("Timeout waiting for player color.")
            self.info_label.config(text="色情報の受信がタイムアウトしました。")
            if hasattr(self.client, 'socket') and self.client.socket: # 念のため
                self.client.socket.settimeout(None)
            return False
        except json.JSONDecodeError:
            # response 変数が未定義の可能性があるので、response_bytes を表示
            decoded_response_for_log = "N/A"
            try:
                decoded_response_for_log = response_bytes.decode('utf-8', errors='ignore')
            except NameError: # response_bytesが定義されていない場合(recv前にエラーなど)
                pass
            print(f"Failed to decode player color data from server. Received(raw): '{decoded_response_for_log}'")
            self.info_label.config(text="サーバーからの色情報が不正です。")
            return False
        except Exception as e:
            print(f"Error receiving player color: {e}")
            self.info_label.config(text=f"色情報受信エラー: {e}")
            return False
        return False # 通常はここまで来ない


    def receive_initialboard_data(self):
        print("receive_initialboard_data")
        try:
            # 観戦モードの場合、サーバーは初期盤面を送ってくるタイミングがプレイヤーと異なる可能性がある
            # ここでは共通の受信処理とする
            response = self.client.socket.recv(1024).decode("utf-8")
            if not response:
                print("No data received from server for initial board")
                # エラー処理またはリトライ処理を検討
                return
            data = json.loads(response)
            # print(f"Received initial board data: {data}")
            
            # サーバーからのデータ形式に 'board' と 'turn' が含まれていることを期待
            if "board" in data and "turn" in data:
                self.board = data["board"]
                self.turn = data["turn"] # サーバーから初期手番ももらう
                self.update_board(data) # 初期盤面を描画
                # self.update_turn_display() # update_board内やconnect_and_setup_gameで呼ばれる
                # self.update_score()      # 同上
            else:
                print("Initial board data is missing 'board' or 'turn' field.")
                # エラーメッセージをGUIに表示することも検討
                self.info_label.config(text="初期盤面データの形式が不正です。")


        except socket.timeout:
            print("Timeout receiving initial board data.")
            self.info_label.config(text="初期盤面データの受信がタイムアウトしました。")
        except json.JSONDecodeError:
            print("Failed to decode initial board data.")
            self.info_label.config(text="初期盤面データの形式が不正です。")
        except Exception as e:
            print(f"Error receiving initial board: {e}")
            self.info_label.config(text=f"初期盤面受信エラー: {e}")
    
    def receive_updates_loop(self):
        while True:
            try:
                response = self.client.socket.recv(1024).decode("utf-8")

                if not response:
                    print("サーバーとの接続が切断されました。")
                    if self.is_spectator:
                        self.info_label.config(text="サーバーとの接続が切れました。観戦を終了します。")
                    else:
                        self.info_label.config(text="サーバーとの接続が切れました。ゲームを終了します。")
                    # end_game は盤面状態に依存するため、ここではGUIメッセージ更新とループ脱出のみ
                    self.root.after(0, self.disable_game_interaction) # クリック等を無効化
                    break

                data = json.loads(response)
                print(f"Received update: {data}") # デバッグ用に受信データを表示

                # サーバーからのメッセージタイプを判定
                message_type = data.get("case", data.get("type")) # "case" or "type" or other key

                if message_type == "FORCED_TERMINATION":
                    print("Opponent disconnected or server forced termination.")
                    self.info_label.config(text="対戦相手の接続が切れたか、サーバーにより終了されました。")
                    self.root.after(0, self.end_game_message, "対戦相手の切断") # end_gameより汎用的なメッセージ表示
                    break # ループを抜ける

                elif message_type == "PASS":
                    self.info_label.config(text=f"{data.get('passed_player', 'プレイヤー')}がパスしました。")
                    self.root.after(0, self.update_board_from_server, data)
                
                elif message_type == "FINISH":
                    self.info_label.config(text="ゲーム終了！")
                    self.root.after(0, self.update_board_from_server, data) # 最終盤面を更新
                    self.root.after(0, self.end_game) # end_gameを呼び出し勝敗表示
                    break # ゲーム終了なのでループを抜ける

                elif message_type == "CONTINUE" or "board" in data: # "CONTINUE" または盤面情報があれば更新
                    self.root.after(0, self.update_board_from_server, data)
                
                elif message_type == "ERROR": # サーバーからのエラーメッセージ
                    error_msg = data.get("message", "不明なエラー")
                    print(f"Server error: {error_msg}")
                    self.info_label.config(text=f"サーバーエラー: {error_msg}")
                    # エラーによってはゲーム続行不可能かもしれない
                    # self.root.after(0, self.disable_game_interaction)


            except json.JSONDecodeError as e:
                print(f"不正なJSONデータを受信しました: {response[:100]}... エラー: {e}") # 受信データの一部も表示
                self.info_label.config(text="サーバーからのデータ形式が不正です。")
                # ここでループを続けるか抜けるかはポリシーによる
                # break
            except socket.error as e: # socket.timeoutも含む可能性がある
                print(f"ソケットエラーが発生しました (受信ループ中): {e}")
                self.info_label.config(text="サーバーとの通信エラーが発生しました。")
                self.root.after(0, self.disable_game_interaction)
                break
            except Exception as e:
                print(f"予期せぬエラーが発生しました (受信ループ中): {e}")
                self.info_label.config(text="予期せぬエラーが発生しました。")
                self.root.after(0, self.disable_game_interaction)
                break
        print("Exited receive_updates_loop.")


    def update_board_from_server(self, server_response):
        print("Received board update from server")
        #print(f"Received data: {server_response}") # receive_updates_loopで表示済み
        if not server_response:
            print("No data received from server for board update")
            return
        if "error" in server_response:
            print("Error from server:", server_response["error"])
            self.info_label.config(text=f"サーバーエラー: {server_response['error']}")
            return
        
        self.board = server_response["board"]
        self.turn = server_response["turn"]
        print(f"Turn: {self.turn}")
        
        self.canvas.delete("piece", "highlight") # 石とハイライトを一度に消す
        self.draw_board_line() # 盤面の線は毎回描画
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])
        
        self.update_turn_display()
        self.update_score()
        if not self.is_spectator: # プレイヤーモードの場合のみ有効手を表示
            self.highlight_valid_moves()
        
        # パスの場合のinfo_label更新はreceive_updates_loopで行う
        # ゲーム終了の場合のinfo_label更新も同様

    def is_valid_move(self, row, col, color):
        if self.board[row][col] is not None:
            return False
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        valid = False
        for direction in directions:
            if self.check_direction(row, col, direction, color):
                valid = True
        return valid
    
    def check_direction(self, row, col, direction, color):
        opponent_color = "white" if color == "black" else "black"
        d_row, d_col = direction
        r, c = row + d_row, col + d_col
        
        if not (0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == opponent_color):
            return False
        
        r += d_row
        c += d_col
        while 0 <= r < self.board_size and 0 <= c < self.board_size:
            if self.board[r][c] is None:
                return False
            if self.board[r][c] == color:
                return True
            r += d_row
            c += d_col
        return False
              

    def first_draw_board(self): # このメソッドは update_board に統合しても良いかもしれない
        print("first_draw_board (called by update_board usually)")
        self.canvas.delete("all")
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])

    def update_board(self, data): # receive_initialboard_data から呼ばれる想定
        print("Update board (initial)")
        self.board = data["board"]
        self.turn = data.get("turn", self.turn) # 初期手番もここで更新
        self.canvas.delete("all") # "piece"だけでなく"all"でクリア
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])
        # self.update_turn_display() # 呼び出し元で行う
        # self.update_score()        # 呼び出し元で行う


    def place_piece(self, row, col, color):
        x0 = col * self.cell_size + self.cell_size // 4
        y0 = row * self.cell_size + self.cell_size // 4
        x1 = (col + 1) * self.cell_size - self.cell_size // 4
        y1 = (row + 1) * self.cell_size - self.cell_size // 4
        self.canvas.create_oval(x0, y0, x1, y1, fill=color, tags="piece") # "piece"タグを追加
    
    def draw_board_line(self):
        self.canvas.create_rectangle(
            0, 0,
            self.board_size * self.cell_size,
            self.board_size * self.cell_size,
            fill="green",
            outline="green" # 枠線も緑で問題ない
        )
        for i in range(self.board_size + 1):
            self.canvas.create_line(0, i * self.cell_size, self.board_size * self.cell_size, i * self.cell_size, fill="black")
            self.canvas.create_line(i * self.cell_size, 0, i * self.cell_size, self.board_size * self.cell_size, fill="black")

    def on_close(self, signal_received=None, frame=None):
        if signal_received:
            print(f"シグナル {signal_received} を受信しました。終了処理を行います...")
        else:
            print("終了処理が呼び出されました...")
        
        # サーバーに終了を通知 (オプショナルだが推奨)
        if hasattr(self, 'client') and self.client and hasattr(self.client, 'socket') and self.client.socket.fileno() != -1:
            try:
                # プレイヤーか観戦者かでメッセージを変えても良い
                exit_message = {"action": "disconnect", "mode": "spectator" if self.is_spectator else "player"}
                self.client.send(json.dumps(exit_message))
                print("サーバーに終了通知を送信しました。")
            except Exception as e:
                print(f"サーバーへの終了通知送信中にエラー: {e}")

        try:
            if hasattr(self, 'client') and self.client and hasattr(self.client, 'socket') and self.client.socket:
                if self.client.socket.fileno() != -1:
                    print("クライアントソケットをクローズします。")
                    self.client.close()
                else:
                    print("クライアントソケットは既にクローズされています。")
            else:
                print("クライアントオブジェクトまたはソケットが存在しません。")
        except Exception as e:
            print(f"ソケットクローズ中にエラーが発生しました: {e}")
        finally:
            if hasattr(self, 'root') and self.root:
                try:
                    if self.root.winfo_exists():
                        print("Tkinterウィンドウを破棄します。")
                        self.root.destroy()
                    else:
                        print("Tkinterウィンドウは既に破棄されています。")
                except tk.TclError as e:
                    print(f"ウィンドウ破棄中にTclエラー: {e} (無視します)")
            
            # スレッドが残っている場合、安全に終了させるための処理も検討 (ここではsys.exitで強制終了)
            print("プロセスを終了します。")
            sys.exit(0) # mainloopの外なので、確実に終了させる


    def update_score(self):
        if hasattr(self, 'board') and self.board: # boardが初期化されてから実行
            black_count = sum(row.count("black") for row in self.board if row) # rowがNoneでないことも確認
            white_count = sum(row.count("white") for row in self.board if row)
            self.score_label.config(text=f"Black: {black_count}  White: {white_count}")
        else:
            self.score_label.config(text="Score: N/A")

    
    def highlight_valid_moves(self):
        self.canvas.delete("highlight")
        if self.is_spectator or self.turn != self.player_color: # 観戦者または自分の手番でなければハイライトしない
            return

        has_moves = False
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move(row, col, self.turn):
                    has_moves = True
                    x0 = col * self.cell_size + self.cell_size // 2 - 5
                    y0 = row * self.cell_size + self.cell_size // 2 - 5
                    x1 = col * self.cell_size + self.cell_size // 2 + 5
                    y1 = row * self.cell_size + self.cell_size // 2 + 5
                    self.canvas.create_oval(x0, y0, x1, y1, fill="gray", tags="highlight")
        if not has_moves and not self.is_spectator: # プレイヤーモードで有効手がない場合
            print(f"{self.turn.capitalize()} has no valid moves. (Client-side check)")
            # サーバーからのパス通知を待つ
            # self.info_label.config(text=f"{self.turn.capitalize()} の有効手がありません。パスになります。") # これはサーバーからの指示で行うべき
            
        
    def pass_turn(self): # このメソッドはサーバーからの指示で実行される想定。クライアント単独では呼ばない。
        # サーバーから "PASS" ケースで盤面と手番が更新されるので、このメソッドのクライアント側での役割は限定的
        print(f"--- Client received pass instruction for: {self.turn} (now handled by server update) ---")
        # self.turn = "white" if self.turn == "black" else "black" # サーバーから新しいturnが来る
        # self.update_turn_display()
        # self.highlight_valid_moves()
        # if not self.has_valid_moves(self.turn) and not self.is_spectator:
            # if not self.has_valid_moves("white" if self.turn == "black" else "black"): # 次の次の手番もなければ終了
                # self.root.after(0, self.end_game) # 両者パスで終了のロジックはサーバー側で判断されるべき

    def has_valid_moves(self, color): # クライアント側の補助関数
        # print(f"Checking valid moves for {color} (client-side)")
        if not hasattr(self, 'board') or not self.board: # board未初期化の場合
            return False
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move(row, col, color):
                    # print(f"Valid move found for {color} at ({row},{col})")
                    return True
        # print(f"No valid moves found for {color} (client-side)")
        return False
    
    def end_game(self): # ゲーム終了時の最終処理 (勝敗表示など)
        if not hasattr(self, 'board') or not self.board:
             self.info_label.config(text="ゲーム結果を計算できません（盤面情報なし）。")
             self.disable_game_interaction()
             return

        black_count, white_count = self.count_pieces()
        winner_text = ""
        if black_count > white_count:
            winner_text = "黒の勝利！"
        elif white_count > black_count:
            winner_text = "白の勝利！"
        else:
            winner_text = "引き分け！"

        self.info_label.config(text=f"ゲーム終了: {winner_text} (黒: {black_count}, 白: {white_count})")
        
        # キャンバス中央に大きく結果を表示
        self.canvas.create_text(
            self.board_size * self.cell_size // 2,
            self.board_size * self.cell_size // 2,
            text=f"{winner_text}\n黒:{black_count} 白:{white_count}", # 複数行表示
            font=("Helvetica", 24 if self.board_size == 8 else 30, "bold"), # サイズ調整
            fill="red",
            tags="game_over_text",
            justify=tk.CENTER # 中央揃え
        )
        self.disable_game_interaction()

    def end_game_message(self, message): # 汎用的な終了メッセージ表示
        self.info_label.config(text=f"ゲーム終了: {message}")
        self.canvas.create_text(
            self.board_size * self.cell_size // 2,
            self.board_size * self.cell_size // 2,
            text=message,
            font=("Helvetica", 24, "bold"),
            fill="blue",
            tags="game_over_text"
        )
        self.disable_game_interaction()

    def disable_game_interaction(self):
        """ゲーム操作を無効にする (クリックイベントの解除など)"""
        if not self.is_spectator:
            try:
                self.canvas.unbind("<Button-1>")
                print("Canvas click event unbound.")
            except tk.TclError as e:
                print(f"Error unbinding canvas click: {e}")
        # 必要に応じて他のUI要素も無効化


    def count_pieces(self):
        black_count = 0
        white_count = 0
        if hasattr(self, 'board') and self.board:
            for row in range(self.board_size):
                for col in range(self.board_size):
                    if self.board[row][col] == "black":
                        black_count += 1
                    elif self.board[row][col] == "white":
                        white_count += 1
        return black_count, white_count

    def update_turn_display(self):
        if self.is_spectator:
            self.turn_label.config(text=f"Turn: {self.turn.capitalize()} (観戦中)")
        elif self.player_color and self.turn == self.player_color:
            self.turn_label.config(text=f"あなたの番: {self.turn.capitalize()}")
        else:
            self.turn_label.config(text=f"相手の番: {self.turn.capitalize()}")
        
    def create_sidebar(self):
        self.sidebar = tk.Frame(self.root)
        self.sidebar.grid(row=0, column=1, sticky="ns", padx=10) # 少し余白を追加

        # 自分の色表示ラベル (プレイヤーモードのみ意味を持つ)
        my_color_text = ""
        if not self.is_spectator:
            my_color_text = f"あなたの色: 未定" # 初期値
            if self.player_color:
                my_color_text = f"あなたの色: {self.player_color.capitalize()}"
        else:
            my_color_text = "観戦モード"
        
        self.my_color_label = tk.Label(self.sidebar, text=my_color_text, font=("Helvetica", 14))
        self.my_color_label.pack(pady=(10,5)) # 上に余白、下に少し余白

        self.turn_label = tk.Label(self.sidebar, text="Turn: Black", font=("Helvetica", 14))
        self.turn_label.pack(pady=5)

        self.score_label = tk.Label(self.sidebar, text="Score: Black 2 White 2", font=("Helvetica", 14))
        self.score_label.pack(pady=5)

        # ゲームモード表示
        mode_display_text = "モード: 観戦者" if self.is_spectator else "モード: プレイヤー"
        self.mode_display_label = tk.Label(self.sidebar, text=mode_display_text, font=("Helvetica", 10))
        self.mode_display_label.pack(pady=(20,5)) # 下に少し大きな余白


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Othello Client")
    parser.add_argument("-s", "--server", default="127.0.0.1", help="Server IP address")
    parser.add_argument("-p", "--port", type=int, default=PORT, help="Server port")
    parser.add_argument("-m", "--mode", choices=['player', 'spectator'], default='player', help="Mode to run the client in (player or spectator)")
    args = parser.parse_args()
    
    root = tk.Tk()
    gui = ClientGUI(root, args.server, args.port, args.mode) # modeを渡す

    signal.signal(signal.SIGINT, lambda sig, frame: gui.on_close(sig, frame))
    root.protocol("WM_DELETE_WINDOW", gui.on_close)
    
    try:
        root.mainloop()
    except KeyboardInterrupt: # mainloop中のCtrl+Cでもon_closeを呼ぶようにする (念のため)
        print("KeyboardInterrupt in mainloop caught.")
        gui.on_close(signal.SIGINT, None)