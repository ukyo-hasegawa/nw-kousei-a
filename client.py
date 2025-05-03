import socket
import tkinter as tk
import json
import threading

PORT = 8080

class Client:
    def __init__(self, host="127.0.0.1", port=PORT):
        self.server = (host, port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(self.server)
        print(f"Connected to server at {self.server}") # サーバーに接続できたことを出力

    def send(self, message): #データの送信のみを行う
        print(f"Send: {message}")
        self.socket.sendall(message.encode("utf-8"))
        #response = self.socket.recv(1024).decode("utf-8")
        #print(f"Received: {response}")
        return 

    def close(self):
        print("Close")
        self.socket.close()

class ClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Othello Client")
        self.player_color = None
        self.board_size = 8
        self.cell_size = 50
        self.canvas = tk.Canvas(self.master, width=self.board_size * self.cell_size, height=self.board_size * self.cell_size)
        self.canvas.grid(row=0, column=0)
        # 自分の色を表示するラベル
        self.info_label = tk.Label(self.master, text="Your color: (waiting...)")
        self.info_label.grid(row=1, column=0)
        self.canvas.bind("<Button-1>", self.handle_click)


        #step1:サーバーに接続し接続できたことを出力
        self.client = Client()
        #step2:サーバーから色を割り当てられたことを確認する。   
        self.set_player_color()
        #step3:サーバーから初期盤面データを受信し、初期盤面を描画する。
        self.receive_initialboard_data()
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
                    break
                else:
                    print("No player color received")
                
            except Exception as e:
                print(f"Error receiving updates: {e}")
                break
        
    def receive_initialboard_data(self):
        print("receive_initialboard_data")
        try:
            response = self.client.socket.recv(1024).decode("utf-8") #サーバーからの初期盤面データを受信したい
            if not response:
                print("No data received from server")
                return
            data = json.loads(response)
            print(f"Received data: {data}") #受信したデータの確認
            self.update_board(data) #初期盤面を描画
        except Exception as e:
            print(f"Error received initial board: {e}")
    
    def receive_updates_loop(self): #サーバーからの更新を受信する。別スレッドで実行し続ける
        while True:
            try:
                response = self.client.socket.recv(1024).decode("utf-8")
                data = json.loads(response)
                # GUI更新はメインスレッドに任せる
                self.master.after(0, self.update_board_from_server, data)
            except Exception as e:
                print(f"Error receiving updates: {e}")
                break

    def update_board_from_server(self, server_response): #受け取ったserver_responseを元に盤面を更新し描画する
        print("Received board update from server")
        if not server_response:
            print("No data received from server")
            return
        #server_response = json.loads(server_response)
        print(f"Received data: {server_response}")
        self.board = server_response["board"]
        self.turn = server_response["turn"]
        #print(f"Current board state: {self.board}")
        #print(f"Turn: {self.turn}")
        self.canvas.delete("piece")
        self.draw_board_line()
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] is not None:
                    self.place_piece(row, col, self.board[row][col])
        #self.highlight_valid_moves()
        #self.update_score()
                
                

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
        print("Place piece")
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

    def on_close(self):
        print("On close")
        self.client.close()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    gui = ClientGUI(root)
    root.protocol("WM_DELETE_WINDOW", gui.on_close)
    root.mainloop()