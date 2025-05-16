import socket
import tkinter as tk
import json
import threading
import argparse  # 追加: コマンドライン引数を扱う
import time   # リトライ時の待機のため追加
import signal # Ctrl+Cによる終了処理のため追加 (念のため確認)
import sys    # sys.exitのため追加 (念のため確認)

PORT = 8080
SERVER_IP = "" #端末のローカルIPアドレス
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
    def __init__(self, root, host, port):  # hostとportを受け取る
        self.root = root
        self.root.title("Othello Client")
        self.player_color = None
        self.turn = "black"
        self.board_size = 8 #簡易版のため、4*4
        self.cell_size = 50
        self.canvas = tk.Canvas(self.root, width=self.board_size * self.cell_size, height=self.board_size * self.cell_size)
        self.canvas.grid(row=0, column=0)
        # 自分の色を表示するラベル
        self.info_label = tk.Label(self.root, text="マッチング中...") # 初期表示を「マッチング中...」に変更
        self.info_label.grid(row=1, column=0)
        self.canvas.bind("<Button-1>", self.handle_click)

        self.host = host
        self.port = port

        # マッチング処理を別スレッドで開始
        threading.Thread(target=self.connect_and_setup_game, daemon=True).start()

    def connect_and_setup_game(self):
        try:
            #step1:サーバーに接続し接続できたことを出力
            self.client = Client(self.host, self.port)
        except ConnectionError as e:
            error_message = f"サーバー接続エラー: {e}\nリトライ上限に達しました。"
            self.info_label.config(text=error_message, wraplength=self.board_size * self.cell_size) # メッセージが長い場合に折り返す
            print(f"ClientGUI: {error_message}")
            # 終了ボタンを作成して表示
            self.exit_button = tk.Button(self.root, text="終了", command=self.on_close)
            # info_label の下に配置するか、別の場所に配置するか検討
            # ここでは info_label の下 (row=2) に配置
            self.exit_button.grid(row=2, column=0, pady=10)
            return

        #step2:サーバーから色を割り当てられたことを確認する。
        # サーバー接続が成功した場合のみ、色設定に進む
        if not self.set_player_color(): # 色設定が失敗したら終了
            # set_player_color内でエラーメッセージが表示されるか、ここで設定
            if "サーバー接続または色割り当てに失敗しました。" not in self.info_label.cget("text"):
                 self.info_label.config(text="サーバーからの色割り当てに失敗しました。")
            return
        # サーバーから初期盤面データを受信するまで、マッチング中のラベルを表示
        self.info_label.config(text=f"あなたの色: {self.player_color} - 対戦相手を待っています...")

        #step3:サーバーから初期盤面データを受信し、初期盤面を描画する。
        self.create_sidebar()
        self.receive_initialboard_data()
        self.update_turn_display()
        self.update_score()
        self.highlight_valid_moves()
        # マッチング中のラベルを非表示、自分の色を表示
        self.info_label.config(text=f"Your color: {self.player_color} ")
        #step4: 石を置いて、サーバーに送信する(GUIをクリックしたときに、サーバーに送信する)、その結果となる盤面データを受信し、盤面を更新する。→受信したデータを元に盤面を更新し描画する。
        threading.Thread(target=self.receive_updates_loop, daemon=True).start()

    def initialize_board(self):
        # 盤面を空に初期化
        self.board = [[None for _ in range(self.board_size)] for _ in range(self.board_size)]

        # 初期配置（中央4マス）
        self.board[3][3] = "white"
        self.board[3][4] = "black"
        self.board[4][3] = "black"
        self.board[4][4] = "white"

    def handle_click(self, event):
        print("Handle click")
        col = event.x // self.cell_size
        row = event.y // self.cell_size

        # クリック位置が正しくない場合は、無効
        if not (0 <= col < self.board_size and 0 <= row < self.board_size):
            return
        #自分のターンでない場合は、無効
        if self.turn != self.player_color:
            print("Not your turn!!!!")
            return

        if self.board[row][col] is None:
            move = {"x": col, "y": row, "turn": self.player_color}
            self.client.send(json.dumps(move))

    def set_player_color(self):
        print("Receive player color")
        while True:
            try:
                response = self.client.socket.recv(1024).decode("utf-8")
                data = json.loads(response)
                print(f"Received player color: {data}") #受信したデータの確認
                
                # プレイヤーカラーを設定できたことをサーバーに通知
                if "player_color" in data:
                    self.player_color = data["player_color"]
                    self.info_label.config(text=f"Your color: {self.player_color}")
                    print(f"Player color set to: {self.player_color}")
                    #self.client.send(json.dumps(self.player_color))
                    #setting okということをサーバーに通知
                    self.client.send(json.dumps({"Setting_OK": self.player_color})) #encodingは必要かどうか調べる必要がある。
                    return True # 色設定成功
                else:
                    print("No player color received")
                    # self.info_label.config(text="色情報を受信できませんでした。") # 必要に応じてエラー表示
                    return False # 色設定失敗

            except Exception as e:
                print(f"Error receiving updates: {e}")
                # self.info_label.config(text=f"エラー: {e}") # 必要に応じてエラー表示
                return False # 色設定失敗
        return False # ループを抜けたら失敗

    def receive_initialboard_data(self):
        print("receive_initialboard_data")
        try:
            response = self.client.socket.recv(1024).decode("utf-8") #サーバーからの初期盤面データを受信したい
            if not response:
                print("No data received from server")
                return
            data = json.loads(response)
            #print(f"Received data: {data}") #受信したデータの確認
            self.update_board(data) #初期盤面を描画
        except Exception as e:
            print(f"Error received initial board: {e}")
    
    def receive_updates_loop(self): #サーバーからの更新を受信する。別スレッドで実行し続ける
        while True:
            try:
                response = self.client.socket.recv(1024).decode("utf-8")

                if not response:
                    print("サーバーとの接続が切断されました。ゲームを終了いたします。")
                    self.end_game()
                    return 

                data = json.loads(response)

                #片方の接続が切れた、強制終了のパターン
                if data["case"] == "FORCED_TERMINATION":
                    print("disconnected player")
                    self.end_game()
                    exit()

                #打つ手なし、パスするパターン
                if data["case"] == "PASS":
                    self.root.after(0, self.update_board_from_server, data)
                    self.pass_turn()
                    #end_gameせず、ゲーム続行
                    
                #盤面が埋まったので終了するパターン
                if data["case"] == "FINISH":
                    #最終的な盤面の描画
                    self.root.after(0, self.update_board_from_server, data)
                    self.end_game()

                #問題なし、game続行
                if data["case"] == "CONTINUE":
                    self.root.after(0, self.update_board_from_server, data)

            except json.JSONDecodeError:
                print("received data is wrong. End game.")
                self.end_game()
                break

            except Exception as e:
                print(f"Error receiving updates loop: {e}")
                break

    def update_board_from_server(self, server_response): #受け取ったserver_responseを元に盤面を更新し描画する
        print("Received board update from server")
        print(f"Received data: {server_response}")
        if not server_response:
            print("No data received from server")
            return
        if "error" in server_response:
            print("Error from server:", server_response["error"])
            return
       
        self.board = server_response["board"]
        self.turn = server_response["turn"]
        #print(f"Current board state: {self.board}")
        print(f"Turn: {self.turn}")
        self.canvas.delete("piece")
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])
        self.update_turn_display()
        self.highlight_valid_moves()
        self.update_score()
    
    def is_valid_move(self, row, col, color):
        # 既に駒が置かれていれば、Falseを返す。
        if self.board[row][col] is not None:
            return False
        # 八方向（縦、横、斜め）
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        # デフォルトをFalseに設定
        valid = False
        # 各方向のマスの状態を確認
        for direction in directions:
            if self.check_direction(row, col, direction, color):
                valid = True
        return valid
    
    def check_direction(self, row, col, direction, color):
        # 相手の駒の色を代入
        opponent_color = "white" if color == "black" else "black"
        # 指定の方向のマスを確認
        d_row, d_col = direction
        row += d_row
        col += d_col
        # 盤面外であれば、Falseを返す
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False
        # 相手の駒がなければ、Falseを返す
        if self.board[row][col] != opponent_color:
            return False
        while 0 <= row < self.board_size and 0 <= col < self.board_size:
            # マスがNoneであれば、Falseを返す
            if self.board[row][col] is None:
                return False
            # 自分の駒があれば、Trueを返す
            if self.board[row][col] == color:
                return True
            row += d_row
            col += d_col
        return False
                

    def first_draw_board(self):
        print("first_draw_board")
        self.canvas.delete("all")
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])

    def update_board(self, data):
        print("Update board")
        self.board = data["board"]
        self.canvas.delete("all")
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])

    def place_piece(self, row, col, color):
        #print("Place piece")
        x0 = col * self.cell_size + self.cell_size // 4
        y0 = row * self.cell_size + self.cell_size // 4
        x1 = (col + 1) * self.cell_size - self.cell_size // 4
        y1 = (row + 1) * self.cell_size - self.cell_size // 4
        self.canvas.create_oval(x0, y0, x1, y1, fill=color)
    
    def draw_board_line(self):
        # 盤面全体を緑色で塗りつぶす
        self.canvas.create_rectangle(
            0, 0,
            self.board_size * self.cell_size,
            self.board_size * self.cell_size,
            fill="green",
            outline="green"
        )
        for i in range(self.board_size + 1):
            # 横線
            self.canvas.create_line(0, i * self.cell_size, self.board_size * self.cell_size, i * self.cell_size, fill="black")
            # 縦線
            self.canvas.create_line(i * self.cell_size, 0, i * self.cell_size, self.board_size * self.cell_size, fill="black")

    def on_close(self, signal_received=None, frame=None): # シグナルハンドラ対応済みの想定
        if signal_received:
            print(f"シグナル {signal_received} を受信しました。終了処理を行います...")
        else:
            print("終了処理が呼び出されました...") # ウィンドウクローズまたはボタンクリック
        
        try:
            if hasattr(self, 'client') and self.client and hasattr(self.client, 'socket') and self.client.socket:
                # ソケットが既に閉じているか確認してからクローズを試みる
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
                    # ウィンドウが存在するか確認してから破棄
                    if self.root.winfo_exists():
                        print("Tkinterウィンドウを破棄します。")
                        self.root.destroy()
                    else:
                        print("Tkinterウィンドウは既に破棄されています。")
                except tk.TclError as e:
                    print(f"ウィンドウ破棄中にTclエラー: {e} (無視します)") # よくあるエラーなので無視
            if signal_received: # シグナルで終了した場合、明示的にプロセスを終了
                print("プロセスを終了します。")
                sys.exit(0)
            elif not signal_received and hasattr(self, 'exit_button') and self.exit_button.winfo_exists():
                # ボタン経由で終了した場合、プロセスを終了させる (Ctrl+Cの場合と挙動を合わせる)
                # ただし、mainloopが終了すれば通常はプロセスも終了するはず
                # Tkinterのmainloopが正常に終了すれば不要な場合もある
                print("ボタン経由での終了。プロセスを終了します。")
                sys.exit(0)


    def update_score(self):
        black_count = sum(row.count("black") for row in self.board)
        white_count = sum(row.count("white") for row in self.board)
        self.score_label.config(text=f"Black: {black_count}  White: {white_count}")
    
    def highlight_valid_moves(self):
        # 前の盤面でのハイライトを削除
        self.canvas.delete("highlight")
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
        if not has_moves:
            print(f"{self.turn.capitalize()} has no valid moves")
          
            
    def pass_turn(self):
        print(f"--------------------Pass turn:{self.turn} !!!!!!!!!!!!!!!!----------------------")
        # パスしたら次のプレイヤーに手番を渡す
        self.turn = "white" if self.turn == "black" else "black"
        print(f"--------------------Pass turn:{self.turn} !!!!!!!!!!!!!!!!----------------------")
        self.update_turn_display()
        self.highlight_valid_moves()
        print(f"--------------------Pass turn:{self.turn} !!!!!!!!!!!!!!!!----------------------")
        self.turn = "white" if self.turn == "black" else "black"
        print(f"self.turn:{self.turn}")
        print(f"--------------------Pass turn:{self.turn} !!!!!!!!!!!!!!!!----------------------")
        # 次のプレイヤーにも合法手がない場合、ゲームを終了する
        if not self.has_valid_moves(self.turn):
            self.end_game()
        else:
            self.update_turn_display()
            self.highlight_valid_moves()

    def has_valid_moves(self, color):
        print("has_valid_moves")
        print(f"color:{color}")
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move(row, col, color):
                    print("has_valid_moves_true")
                    return True
        print("has_valid_moves_false")
        return False
    
    def end_game(self):

        black_count, white_count = self.count_pieces()
        if black_count > white_count:
            winner = "黒の勝利！"
        elif white_count > black_count:
            winner = "白の勝利！"
        else:
            winner = "引き分け！"

        self.canvas.create_text(
            self.board_size * self.cell_size // 2,
            self.board_size * self.cell_size // 2,
            text=f"{winner}",
            font=("Helvetica", 36),
            fill="red"
        )
    
    def count_pieces(self):
        black_count = 0
        white_count = 0
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] == "black":
                    black_count += 1
                elif self.board[row][col] == "white":
                    white_count += 1
        return black_count, white_count

    def update_turn_display(self):
        self.turn_label.config(text=f"Turn: {self.turn.capitalize()}")
        
    def create_sidebar(self):
        self.sidebar = tk.Frame(self.root)
        self.sidebar.grid(row=0, column=1, sticky="ns")

        self.turn_label = tk.Label(self.sidebar, text="Turn: Black", font=("Helvetica", 14))
        self.turn_label.pack(pady=10)

        self.score_label = tk.Label(self.sidebar, text="", font=("Helvetica", 14))
        self.score_label.pack(pady=10)
    
    
    


if __name__ == "__main__":
    # signal と sys のインポートはファイルの先頭に配置
    import signal
    import sys
    parser = argparse.ArgumentParser(description="Othello Client")
    parser.add_argument("-s", "--server", default="127.0.0.1", help="Server IP address")
    parser.add_argument("-p", "--port", type=int, default=PORT, help="Server port")
    args = parser.parse_args()
    root = tk.Tk()
    gui = ClientGUI(root, args.server, args.port)

    # SIGINT (Ctrl+C) のハンドラを設定
    # lambdaを使用して、gui.on_close に引数を渡せるようにする
    signal.signal(signal.SIGINT, lambda sig, frame: gui.on_close(sig, frame))

    root.protocol("WM_DELETE_WINDOW", gui.on_close)
    root.mainloop()
