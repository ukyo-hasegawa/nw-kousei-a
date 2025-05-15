import socket
import threading
import json

PORT = 8080

class OthelloGame:
    def __init__(self, board_size=8):
        self.board_size = board_size
        self.board = [[None for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.turn = "black"
        self.case = "CONTINUE" #プレイヤー間のやり取りを示す変数。"continue","pass","finish"の3種類
        
    def initialize_board(self):
        print("Initializing board")
        center = self.board_size // 2
        self.board[center - 1][center - 1] = "white"
        self.board[center][center] = "white"
        self.board[center - 1][center] = "black"
        self.board[center][center - 1] = "black"

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

    def is_valid_move_for_pass(self, row, col, color):
        # 既に駒が置かれていれば、Falseを返す。
        if self.board[row][col] is not None:
            return False
        # 八方向（縦、横、斜め）
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        # デフォルトをFalseに設定
        valid = False
        # 各方向のマスの状態を確認
        for direction in directions:
            if self.check_direction_for_pass(row, col, direction, color):
                valid = True
        return valid

    def check_direction(self, row, col, direction, color):
        #print("check_direction")
        #相手のコマの色を代入
        opponent_color = "white" if color == "black" else "black"
        #指定の方向のマスを確認
        d_row, d_col = direction
        row += d_row
        col += d_col
        #盤面外であればfalse
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False
        #相手の駒がなければfalse
        if self.board[row][col] != opponent_color:
            return False
        while 0 <= row < self.board_size and 0 <= col < self.board_size:
            #マスがnoneであればfalse
            if self.board[row][col] is None:
                return False
            #自分の駒があれば、trueを返す
            if self.board[row][col] == color:
                return True
            row += d_row
            col += d_col
        return False
    
    #passの処理判定のためだけに使う関数
    # def check_direction_for_pass(self, row, col, direction, color):
    #     #print("check_direction")
    #     #相手のコマの色を代入
    #     print(f"check_direction_color:{color}")
    #     opponent_color = color 
    #     #指定の方向のマスを確認
    #     d_row, d_col = direction
    #     row += d_row
    #     col += d_col
    #     #盤面外であればfalse
    #     if not (0 <= row < self.board_size and 0 <= col < self.board_size):
    #         return False
    #     #相手の駒がなければfalse
    #     if self.board[row][col] != opponent_color:
    #         return False
    #     while 0 <= row < self.board_size and 0 <= col < self.board_size:
    #         #マスがnoneであればfalse
    #         if self.board[row][col] is None:
    #             return False
    #         #自分の駒があれば、trueを返す
    #         if self.board[row][col] == color:
    #             return True
    #         row += d_row
    #         col += d_col
    #     return False
    
    def check_direction_for_pass(self, row, col, direction, color):
    
        # 指定した位置にcolorの石を置くとして、指定方向に挟めるかどうかを確認する。
        # color: 自分の色（置こうとしている色）
        
        d_row, d_col = direction
        row += d_row
        col += d_col

        # 盤面外ならFalse
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False

        # 最初のマスが自分と同じ色ならFalse（＝相手の石が無いので挟めない）
        if self.board[row][col] != ("white" if color == "black" else "black"):
            return False

        # さらに進みながら調査
        while 0 <= row < self.board_size and 0 <= col < self.board_size:
            if self.board[row][col] is None:
                return False
            if self.board[row][col] == color:
                return True  # 挟める条件を満たした
            row += d_row
            col += d_col

        return False

    def place_piece(self, row, col, color):
        # マスの状態を更新
        self.board[row][col] = color
        
    #次のplayerが打つ盤面が存在するのかどうかを確認する関数
    def next_check(self,color):
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move_for_pass(row, col, color):
                    return True
        return False

    def flip_pieces(self, row, col, turn):
        #print("flip_pieces")
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        for direction in directions:
            if self.check_direction(row, col, direction, turn):
                self.flip_in_direction(row, col, direction, turn)

    def flip_in_direction(self, row, col, direction, turn):
        #print("flip_in_direction")
        opponent_color = "white" if turn == "black" else "black"
        d_row, d_col = direction
        row += d_row
        col += d_col
        while self.board[row][col] == opponent_color:
            self.board[row][col] = turn
            row += d_row
            col += d_col

    def judge_check(self):
        print("judge_check")
        """
        ゲームが終了しているか確認する関数
        盤面確認してNoneが存在しない(全て黒か白の石が置かれた)状態かどうかを確認。
        """
        for row in self.board:
            if None in row:
                print("return False")
                return False
            print("return True")
            return True
        
    def has_valid_moves(self, color):
        print("has_valid_moves")
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move(row, col, color):
                    return True
        return False


class Server:
    def __init__(self, host="0.0.0.0", port=PORT):
        #step0: サーバーの初期化
        self.server_address = (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(self.server_address)
        self.socket.listen(2)
        self.clients = []
        self.player_color_list = [] # プレイヤーカラーと対応するclientを格納するタプル,clientが接続し、色が割り当てられわりあてられたことを確認するためのもの。
        self.game = OthelloGame()
        #step1: クライアントの接続を待機
        print("Waiting for clients to connect...")

        #step2: クライアントの接続を受け入れ、色を割り当てる。→step3:クライアントが初期盤面データ(json形式)を待っているんで送信する。
        self.start()

        #step3:クライアントが初期盤面データ(json形式)を待っているんで送信する。
        self.game.initialize_board()
        self.broadcast_board(self.game.turn,self.game.case)

        #step4: クライアントからの手を受け取る。→受け取った手が有効な手であれば、盤面を更新し、クライアントに盤面データを送信する。無効な手であれば、エラーメッセージを送信する。
        for client in self.clients:
            threading.Thread(target=self.handle_client, args=(client, self.server_address)).start()

    def broadcast_board(self, turn,case):
        print("Broadcast board")
        data = json.dumps({"board": self.game.board, "turn": turn, "case":case}).encode() #ここのturnは、サーバー側で管理しているターンの情報を送信するためのもの。
        print(f"send_data:{data}")
        for client in self.clients:
            client.sendall(data) #client 2人に送信

    #ゲーム終了をクライアントへ送信
    def send_finish_message(self):
        print("send_finish_message")
        message = json.dumps({"finish":"game_end"}).encode()
        for client in self.clients:
            client.sendall(message)

    def handle_client(self, conn, addr):
        print(f"Handling client {addr}")
        try:
            while True: 
                try:
                    data = conn.recv(1024)
                    if not data:
                        print("切断されました")
                        self.game.case = "FORCED_TERMINATION"
                        self.broadcast_board(self.game.turn,self.game.case)

                        break
                except (ConnectionResetError, BrokenPipeError):
                    print("接続が失われました")
                    break
                #print(f"Received data from {addr}: {data}")
                move = json.loads(data.decode())

                x, y, turn= move["x"], move["y"], move["turn"]
                print(f"--------------------------------今手を打ったのは:{turn}-------------------------------")

                #合法手かどうかの確認
                if(self.game.is_valid_move(y, x, turn)):
                    #コマを置く(描画はしない)
                    self.game.place_piece(y,x,turn)
                    #コマをひっくり返す
                    self.game.flip_pieces(y, x, turn)
                    #最終的なスコアはclient側で計算させるので不要
                    
                    #player turnの切り替え
                    turn = "white" if turn == "black" else "black"
                    print(f"turn:{turn}")
                    #盤面を更新した結果、次のプレイヤーが打つ手があるのかどうかを確認→打つ手があれば盤面をブロードキャスト
                    if(self.game.next_check(turn)):
                        self.game.case = "CONTINUE"
                        self.broadcast_board(turn,self.game.case)
                    elif self.game.judge_check(): #盤面が埋まった場合の勝敗処理
                        self.game.case = "FINISH"
                        self.broadcast_board(turn,self.game.case)
                        #return
                    else:
                        self.game.case = "PASS"
                        #単純に打つ手無し(パス)
                        print(f"{turn} PASS!!!!!!!!!!!!")

                        self.broadcast_board(turn,self.game.case)

        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally: #try抜けたら確実に実行される処理
            conn.close()
            self.clients.remove(conn)

    

    # def pass_turn(self):
    #     print("--------------------Pass turn !!!!!!!!!!!!!!!!----------------------")
    #     # パスしたら次のプレイヤーに手番を渡す
    #     passed_turn = self.game.turn
    #     self.game.turn = "white" if self.game.turn == "black" else "black"
    #     #self.update_turn_display()
    #     #self.highlight_valid_moves()

    #     #パスしたことをclientに伝達
    #     pass_message = json.dumps({"PASS":f"---------------------{passed_turn} is PASS!!!!!!!!!!!-------------------"}).encode()
    #     for client in self.clients:
    #         client.sendall(pass_message)

    #     # 次のプレイヤーにも合法手がない場合、ゲームを終了する
    #     if not self.game.next_check(self.game.turn):
    #         self.send_finish_message()

    def start(self):
        print("Start")
        print(f"Server started on {self.server_address}")
        while True:
            conn, addr = self.socket.accept()
            print(f"Client connected: {addr}") #ここで接続したクライアントのIPアドレスを表示する。

            # プレイヤーカラーを決定
            if len(self.clients) % 2 == 0:
                player_color = "black"
            elif len(self.clients) % 2 == 1:
                player_color = "white"
            else:
                conn.sendall(json.dumps({"error": "Game already has 2 players"}).encode())
                conn.close()
                continue

            # 色をクライアントに送信
            conn.sendall(json.dumps({"player_color": player_color}).encode())
            print(f"Assigned color {player_color} to {addr}")

            #各クライアントからの色を確認した旨を受信するまで待機
            check_player_color_raw = conn.recv(1024)
            check_player_color = check_player_color_raw.decode() #.strip()は必要ないのかどうかは調べる必要がある。
            if "Setting_OK" in check_player_color:
                check_player_color = json.loads(check_player_color)["Setting_OK"]
                print(f"Received player color confirmation from {addr}: {check_player_color}")
            self.player_color_list.append((conn, check_player_color))
            self.clients.append(conn) 
            #2人から色の確認が取れたらループを抜ける
            if len(self.player_color_list) == 2:    
                break
        return 

if __name__ == "__main__":
    server = Server()
    #server.start()