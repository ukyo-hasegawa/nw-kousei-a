import socket
import threading
import json

PORT = 8080

class OthelloGame:
    def __init__(self, board_size=4):
        self.board_size = board_size
        self.board = [[None for _ in range(self.board_size)] for _ in range(self.board_size)]
        self.turn = "black"
        self.current_turn = self.turn
        #self.initialize_board()

    def initialize_board(self):
        print("Initializing board")
        center = self.board_size // 2
        self.board[center - 1][center - 1] = "white"
        self.board[center][center] = "white"
        self.board[center - 1][center] = "black"
        self.board[center][center - 1] = "black"

    def is_valid_move(self, row, col, color):
        #print("is_valid_move")
        if self.board[row][col] is not None:
            return False
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        for direction in directions:
            if self.check_direction(row, col, direction, color):
                return True
        return False

    def check_direction(self, row, col, direction, color):
        #print("check_direction")
        opponent_color = "white" if color == "black" else "black"
        d_row, d_col = direction
        row += d_row
        col += d_col
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return False
        if self.board[row][col] != opponent_color:
            return False
        while 0 <= row < self.board_size and 0 <= col < self.board_size:
            if self.board[row][col] is None:
                return False
            if self.board[row][col] == color:
                return True
            row += d_row
            col += d_col
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
        ゲームが終了しているか確認する関数,client.pyで実装されているpass_turn()からのend_game()に関してはちょっとよく分からなかった。
        盤面確認してNoneが存在しない(全て黒か白の石が置かれた)状態かどうかを確認。
        """
        for row in self.board:
            if None in row:
                print("return False")
                return False
            print("return True")
            return True


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
        self.broadcast_board(self.game.turn)

        #step4: クライアントからの手を受け取る。→受け取った手が有効な手であれば、盤面を更新し、クライアントに盤面データを送信する。無効な手であれば、エラーメッセージを送信する。
        for client in self.clients:
            threading.Thread(target=self.handle_client, args=(client, self.server_address)).start()


    def broadcast_board(self, turn):
        print("Broadcast board")
        data = json.dumps({"board": self.game.board, "turn": turn}).encode() #ここのturnは、サーバー側で管理しているターンの情報を送信するためのもの。
        for client in self.clients:
            client.sendall(data) #client 2人に送信
            #print(f"Broadcasting data: {data}")
    
    def broadcast_end_message(self, winner, reason):
        message = json.dumps({
            "end": f"{winner} wins by {reason}"
        }).encode()
        for client in self.clients:
            client.sendall(message)
    #ゲーム終了をクライアントへ送信
    def send_end_message(self):
        print("send_end_message")
        message = json.dumps("game_end").encode()
        for client in self.clients:
            client.sendall(message)

    def handle_client(self, conn, addr):
        print(f"Handling client {addr}")
        try:
            while True: 
                data = conn.recv(1024) #clientが打った手を受信する予定、x,y,turnの情報を受信できるかどうかは確認する必要がある。
                print(f"Received data from {addr}: {data}")
                move = json.loads(data.decode())
                #降参処理
                if "surrender" in move:
                    surrender_player = move["surrender"]
                    winner = "white" if surrender_player == "black" else "black"
                    self.broadcast_end_message(winner, f"surrender from {surrender_player}")
                    return 
                

                x, y, turn = move["x"], move["y"], move["turn"]
                print(f"--------------------------------今手を打ったのは:{self.game.turn}-------------------------------")
                # クリック位置が正しくない場合は、無効
                if not (0 <= x < self.game.board_size and 0 <= y < self.game.board_size):
                    print("Please reclick ")
                    return
                #自分のターンでない場合は、無効
                if (turn != self.game.turn):
                    print(f"Not your turn!!!!:{turn}")
                    return
                elif(self.game.is_valid_move(y, x, turn)):
                    self.game.board[y][x] = turn
                    self.game.flip_pieces(y, x, turn)
                    self.game.turn = "white" if turn == "black" else "black"
                    self.broadcast_board(self.game.turn)

                if self.game.judge_check():
                    self.send_end_message()
                    return
                
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally: #try抜けたら確実に実行される処理
            conn.close()
            self.clients.remove(conn)

    def pass_turn(self):
        print("--------------------Pass turn !!!!!!!!!!!!!!!!----------------------")
        # パスしたら次のプレイヤーに手番を渡す
        self.turn = "white" if self.turn == "black" else "black"
        #self.update_turn_display()
        #self.highlight_valid_moves()

        #ここら辺にパスしたことをclientに伝えるコード実装予定

        # 次のプレイヤーにも合法手がない場合、ゲームを終了する
        if not self.has_valid_moves(self.turn):
            self.end_game()

    def start(self):
        print("Start")
        print(f"Server started on {self.server_address}")
        while True:
            conn, addr = self.socket.accept()
            print(f"Client connected: {addr}") #ここで接続したクライアントのIPアドレスを表示する。

            # プレイヤーカラーを決定
            if len(self.clients) == 0:
                player_color = "black"
            elif len(self.clients) == 1:
                player_color = "white"
            else:
                conn.sendall(json.dumps({"error": "Game already has 2 players"}).encode())
                conn.close()
                continue

            # 色をクライアントに送信
            conn.sendall(json.dumps({"player_color": player_color}).encode())
            print(f"Assigned color {player_color} to {addr}")

            #各クライアントからの色を確認した旨を受信するまで待機
            #while True:
            check_player_color_raw = conn.recv(1024)
            check_player_color = check_player_color_raw.decode() #.strip()は必要ないのかどうかは調べる必要がある。
            if "Setting_OK" in check_player_color:
                check_player_color = json.loads(check_player_color)["Setting_OK"]
                print(f"Received player color confirmation from {addr}: {check_player_color}")
            self.player_color_list.append((conn, check_player_color))
            self.clients.append(conn) 
            
            if len(self.player_color_list) == 2:    
                break
        return 

if __name__ == "__main__":
    server = Server()
    #server.start()