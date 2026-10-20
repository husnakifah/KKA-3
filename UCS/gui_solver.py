"""
Tambahan di sini:
  * hijau  = langkah AMAN (hasil deduksi, risiko 0%)
  * oranye = langkah TEBAKAN (sel risiko terendah menurut UCS)
  * merah  = sel yang meledak (kalah)
  * B merah = sel yang sudah pasti ranjau (hasil deduksi)
  * judul jendela = nomor langkah, jenis, risiko, peluang selamat
"""
import PySimpleGUI as sg

from solver_ucs import UCSMinesweeperSolver, WIN, LOSE

SAFE_COLOR = ("black", "#9be28a")
GUESS_COLOR = ("black", "#ffb347")
BOOM_COLOR = ("white", "#e03131")
MINE_COLOR = ("white", "#c0392b")


def solve_on_gui(game_window, delay=0.4, verbose=True):
    """Return 1 (menang), 2 (kalah) atau None (jendela ditutup)."""
    game = game_window.game
    win = game_window.window
    win.finalize()
    cols = game.y
    key_of = lambda r, c: str(r * cols + c + 1)
    flagged = set()

    def opener(r, c):
        return game_window.play(key_of(r, c))

    def on_step(info):
        r, c = info["cell"]
        res = info["result"]
        if res == LOSE:
            color = BOOM_COLOR
        else:
            color = SAFE_COLOR if info["safe"] else GUESS_COLOR
        win[key_of(r, c)].update(button_color=color)

        if res == 0:                                  # tandai ranjau hasil deduksi
            for mr, mc in solver.known_mines - flagged:
                win[key_of(mr, mc)].update("B", button_color=MINE_COLOR)
                flagged.add((mr, mc))

        kind = "AMAN" if info["safe"] else "TEBAK"
        try:
            win.TKroot.title(f"Solver UCS | langkah {info['move']} {kind} ({r},{c}) "
                             f"risiko {info['risk']:.1%} | P(selamat) {2.718281828 ** -info['g']:.1%}")
        except Exception:
            pass
        event, _ = win.read(timeout=int(delay * 1000))
        return event not in (None, sg.WIN_CLOSED)

    solver = UCSMinesweeperSolver(game, verbose=verbose, opener=opener, on_step=on_step)
    result = solver.solve()
    if result == WIN:
        game_window.unlock_all_buttons()
        try:
            win.TKroot.title("Solver UCS | SELESAI - MENANG")
        except Exception:
            pass
        win.read(timeout=800)
    return result
