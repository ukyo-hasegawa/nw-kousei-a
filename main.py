import tkinter as tk

class OthelloGame:
    def __init__(self, root):
        # rootオブジェクト
        self.root = root
        # ウィンドウのタイトル
        self.root.title("Othello Game")
        # 盤面サイズ
        self.board_size = 8
        # マス目の大きさ
        self.cell_size = 50
        # ボードの状態（黒、白、None）
        self.board = [[None for _ in range(self.board_size)] for _ in range(self.board_size)]
        # 先行を黒に指定
        self.turn = "black"
        self.create_sidebar()
        self.create_board()
        self.initialize_board()
        self.update_turn_display()
        self.update_score()
        self.highlight_valid_moves()

    def create_board(self):
        # Canvasの定義
        self.canvas = tk.Canvas(self.root, width=self.board_size * self.cell_size, height=self.board_size * self.cell_size)
        # グリッドの作成
        self.canvas.grid(row=0, column=0)
        # グリッドの設定
        for i in range(self.board_size):
            for j in range(self.board_size):
                x0 = i * self.cell_size
                y0 = j * self.cell_size
                x1 = x0 + self.cell_size
                y1 = y0 + self.cell_size
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="black", fill="green")
                
        # クリックイベント（左ボタンクリック時に、handle_clickメソッドを呼び出す）
        self.canvas.bind("<Button-1>", self.handle_click)

    def initialize_board(self):
        # 初期盤面
        center = self.board_size // 2
        self.place_piece(center-1, center-1, "white")
        self.place_piece(center  , center  , "white")
        self.place_piece(center-1, center  , "black")
        self.place_piece(center  , center-1, "black")

    def place_piece(self, row, col, color):
        x0 = col     * self.cell_size + self.cell_size // 4
        y0 = row     * self.cell_size + self.cell_size // 4
        x1 = (col+1) * self.cell_size - self.cell_size // 4
        y1 = (row+1) * self.cell_size - self.cell_size // 4
        # マスの状態を更新
        self.board[row][col] = color
        # 駒を描画
        self.canvas.create_oval(x0, y0, x1, y1, fill=color)

    def handle_click(self, event):
        # クリック位置からマスを判定
        col = event.x // self.cell_size
        row = event.y // self.cell_size
        
        # クリック位置が正しくない場合は、無効
        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            return
        
        # 合法手かどうか判定し、
        if self.is_valid_move(row, col, self.turn):
            # 駒を置く
            self.place_piece(row, col, self.turn)
            # 駒をひっくり返す
            self.flip_pieces(row, col)
            # スコアの更新
            self.update_score()
            # 手番の更新
            self.turn = "white" if self.turn == "black" else "black"
            # 盤面を更新
            self.update_turn_display()
            # 駒を置けるマスをハイライト表示
            self.highlight_valid_moves()
            
            # 駒を置けるマスがなければ、パス
            if not self.has_valid_moves(self.turn):
                self.pass_turn()

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

    def flip_pieces(self, row, col):
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        for direction in directions:
            if self.check_direction(row, col, direction, self.turn):
                self.flip_in_direction(row, col, direction)

    def flip_in_direction(self, row, col, direction):
        opponent_color = "white" if self.turn == "black" else "black"
        d_row, d_col = direction
        row += d_row
        col += d_col
        while self.board[row][col] == opponent_color:
            # 相手の駒を自分の駒に置き換える
            self.place_piece(row, col, self.turn)
            row += d_row
            col += d_col

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

    def has_valid_moves(self, color):
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.is_valid_move(row, col, color):
                    return True
        return False

    def pass_turn(self):
        # パスしたら次のプレイヤーに手番を渡す
        self.turn = "white" if self.turn == "black" else "black"
        self.update_turn_display()
        self.highlight_valid_moves()

        # 次のプレイヤーにも合法手がない場合、ゲームを終了する
        if not self.has_valid_moves(self.turn):
            self.end_game()

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

    def create_sidebar(self):
        self.sidebar = tk.Frame(self.root)
        self.sidebar.grid(row=0, column=1, sticky="ns")

        self.turn_label = tk.Label(self.sidebar, text="Turn: Black", font=("Helvetica", 14))
        self.turn_label.pack(pady=10)

        self.score_label = tk.Label(self.sidebar, text="", font=("Helvetica", 14))
        self.score_label.pack(pady=10)

    def update_turn_display(self):
        self.turn_label.config(text=f"Turn: {self.turn.capitalize()}")

    def update_score(self):
        black_count, white_count = self.count_pieces()
        self.score_label.config(text=f"Black: {black_count}  White: {white_count}")

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

if __name__ == "__main__":
    root = tk.Tk()
    game = OthelloGame(root)
    root.mainloop()
    