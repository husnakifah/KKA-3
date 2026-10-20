"""
* State       : papan yang terlihat pemain (sel terbuka + angkanya + sel yang
                sudah pasti ranjau).
* Aksi        : membuka sebuah sel yang masih tertutup.
* Biaya aksi  : cost(a) = -ln(1 - P(ranjau di sel a))
                - sel PASTI aman      -> P = 0 -> cost = 0
                - sel berisiko        -> cost > 0, makin besar bila makin berbahaya
                - sel PASTI ranjau    -> cost = tak hingga (tidak pernah dibuka)
* Biaya jalur : g(n) = jumlah cost = -ln( P(selamat sepanjang jalur) ),
                jadi MINIMUM g  <=>  MAKSIMUM peluang selamat.
* Antrian     : priority queue (heapq) diurutkan menurut g(n); UCS selalu
                meng-expand node dengan g terkecil.
* Re-planning : hasil membuka sel baru diketahui setelah sel itu dibuka, jadi
                UCS dijalankan ulang di setiap giliran dari papan terbaru.

"""
import argparse
import contextlib
import heapq
import io
import math
import random
import time
from itertools import count

from minesweeper import Minesweeper

WIN, LOSE = 1, 2


class _Overflow(Exception):
    """Enumerasi komponen terlalu besar -> pakai heuristik cadangan."""


class UCSMinesweeperSolver:
    def __init__(self, game, verbose=False, delay=0.0, pause=False,
                 opener=None, on_step=None):
        self.opener = opener or (lambda r, c: game.playerDecision(r, c, 1))
        self.on_step = on_step
        self.delay, self.pause = delay, pause
        self.game = game
        self.R, self.C = game.x, game.y
        self.total_mines = game.mines
        self.known_mines = set()
        self.g = 0.0                  # biaya jalur kumulatif = -ln(P selamat)
        self.moves = 0
        self.guesses = 0
        self.verbose = verbose
        self._tie = count()           # tie-breaker FIFO untuk heap

    # ------------------------------------------------------------ observasi
    def neighbors(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr or dc) and 0 <= r + dr < self.R and 0 <= c + dc < self.C:
                    yield (r + dr, c + dc)

    def observe(self):
        """Hanya info yang terlihat pemain: {(r,c): angka} untuk sel terbuka.
        Di minesweeper.py, mines_around == -1 berarti sel 0 yang sudah dibuka."""
        opened = {}
        for r in range(self.R):
            for c in range(self.C):
                cell = self.game.matrix[r][c]
                if cell.unlocked and not cell.mine:
                    opened[(r, c)] = max(cell.mines_around, 0)
        return opened

    # ------------------------------------------------------------- deduksi
    def build_constraints(self, opened):
        """Tiap angka -> (himpunan tetangga tertutup, jumlah ranjau di dalamnya)."""
        cons = set()
        for (r, c), n in opened.items():
            unk = frozenset(nb for nb in self.neighbors(r, c)
                            if nb not in opened and nb not in self.known_mines)
            if unk:
                need = n - sum(nb in self.known_mines for nb in self.neighbors(r, c))
                cons.add((unk, need))
        return cons

    @staticmethod
    def deduce(cons):
        """Aturan single-point + subset sampai tidak ada fakta baru."""
        safe, mines = set(), set()
        while True:
            reduced = set()
            for s, n in cons:
                s2 = frozenset(x for x in s if x not in safe and x not in mines)
                n2 = n - sum(x in mines for x in s)
                if s2:
                    reduced.add((s2, n2))
            cons = reduced
            new_s, new_m = set(), set()
            for s, n in cons:
                if n == 0:
                    new_s |= s
                elif n == len(s):
                    new_m |= s
            lst = list(cons)
            for a, na in lst:
                for b, nb in lst:
                    if a < b:
                        d, nd = b - a, nb - na
                        if nd == 0:
                            new_s |= d
                        elif nd == len(d):
                            new_m |= d
            if not new_s and not new_m:
                return safe, mines, cons
            safe |= new_s
            mines |= new_m

    # --------------------------------------------------------- probabilitas
    @staticmethod
    def _enumerate(cells, cons, node_limit=150000):
        """Backtracking: hitung semua konfigurasi ranjau yang konsisten."""
        idx = {c: i for i, c in enumerate(cells)}
        cl = [([idx[x] for x in s], n) for s, n in cons]
        cell_cons = [[] for _ in cells]
        for k, (ids, _) in enumerate(cl):
            for i in ids:
                cell_cons[i].append(k)
        need = [n for _, n in cl]
        free = [len(ids) for ids, _ in cl]
        assign = [0] * len(cells)
        counts = [0] * len(cells)
        state = {"total": 0, "nodes": 0}

        def rec(i):
            state["nodes"] += 1
            if state["nodes"] > node_limit:
                raise _Overflow
            if i == len(cells):
                state["total"] += 1
                for j, a in enumerate(assign):
                    counts[j] += a
                return
            for v in (0, 1):
                for k in cell_cons[i]:
                    free[k] -= 1
                    need[k] -= v
                if all(0 <= need[k] <= free[k] for k in cell_cons[i]):
                    assign[i] = v
                    rec(i + 1)
                for k in cell_cons[i]:
                    free[k] += 1
                    need[k] += v
            assign[i] = 0

        rec(0)
        return counts, state["total"]

    def probabilities(self, cons, unknown):
        parent = {}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for s, _ in cons:
            s = list(s)
            for x in s:
                parent.setdefault(x, x)
            for x in s[1:]:
                parent[find(x)] = find(s[0])
        groups = {}
        for x in parent:
            groups.setdefault(find(x), []).append(x)

        probs = {}
        for cells in groups.values():
            cells.sort()
            cset = set(cells)
            ccons = [(s, n) for s, n in cons if next(iter(s)) in cset]
            try:
                counts, total = self._enumerate(cells, ccons)
                if total == 0:
                    raise _Overflow
                for i, x in enumerate(cells):
                    probs[x] = counts[i] / total
            except _Overflow:                       # heuristik cadangan
                for x in cells:
                    probs[x] = max(n / len(s) for s, n in ccons if x in s)

        frontier = set(parent)
        others = [c for c in unknown if c not in frontier]
        mines_left = self.total_mines - len(self.known_mines)
        exp_front = sum(probs[x] for x in frontier)
        p_other = 0.0
        if others:
            p_other = min(1.0, max(0.0, (mines_left - exp_front) / len(others)))
        for c in others:
            probs[c] = p_other
        return probs

    # ------------------------------------------------------------------ UCS
    def plan(self):
        """Bangun priority queue UCS dari papan saat ini.
        Return (heap, batch_aman)."""
        opened = self.observe()
        cons = self.build_constraints(opened)
        safe, mines, cons = self.deduce(cons)
        self.known_mines |= mines

        heap = []
        if safe:                                    # semua node ber-cost 0
            for cell in sorted(safe):
                heapq.heappush(heap, (self.g + 0.0, next(self._tie), cell))
            return heap, True

        unknown = [(r, c) for r in range(self.R) for c in range(self.C)
                   if (r, c) not in opened and (r, c) not in self.known_mines]
        probs = self.probabilities(cons, unknown)
        for cell in unknown:
            p = probs[cell]
            if p >= 1.0:                            # ranjau
                continue
            step = -math.log(1.0 - p)
            heapq.heappush(heap, (self.g + step, next(self._tie), cell))
        return heap, False

    # ------------------------------------------------------ tampilan langkah
    def render(self, last=None):
        """Papan dari sudut pandang pemain. [x] = sel yang baru dibuka.
        # tertutup | B ranjau hasil deduksi | . sel 0 | * ranjau (kalah)"""
        out = ["     " + "".join(f"{j:3d} " for j in range(self.C))]
        for i in range(self.R):
            row = []
            for j in range(self.C):
                cell = self.game.matrix[i][j]
                if cell.unlocked:
                    s = "*" if cell.mine else (str(cell.mines_around)
                                               if cell.mines_around > 0 else ".")
                elif (i, j) in self.known_mines:
                    s = "B"
                else:
                    s = "#"
                row.append(f"[{s}]" if (i, j) == last else f" {s} ")
            out.append(f"{i:3d} |" + " ".join(row))
        return "\n".join(out)

    def _show_queue(self, heap, is_safe_batch):
        top = heapq.nsmallest(5, heap)
        print("\n" + "=" * 60)
        if is_safe_batch:
            print(f"Deduksi menemukan {len(heap)} sel PASTI AMAN (semua g = {self.g:.3f}):")
        else:
            print("Tidak ada sel pasti aman -> UCS memilih sel berisiko terendah.")
        print("Priority queue (5 teratas)  [sel | g | risiko langkah ini]:")
        for g, _, cell in top:
            print(f"   {cell}  g={g:.3f}  risiko={1 - math.exp(-(g - self.g)):5.1%}")
        if len(heap) > 5:
            print(f"   ... +{len(heap) - 5} node lain")

    def _wait(self):
        if self.pause:
            input("   [Enter] untuk langkah berikutnya... ")
        elif self.delay:
            time.sleep(self.delay)

    def solve(self):
        game = self.game
        if self.verbose:
            print("Papan awal:\n" + self.render())
        while True:
            if game.solved():
                return WIN
            heap, is_safe_batch = self.plan()
            if not heap:
                return LOSE                         # tidak ada aksi tersisa
            if self.verbose:
                self._show_queue(heap, is_safe_batch)
            while heap:
                g, _, (r, c) = heapq.heappop(heap)  # expand node dengan g terkecil
                risk = 1 - math.exp(-(g - self.g))
                self.moves += 1
                if not is_safe_batch:
                    self.guesses += 1
                self.g = g
                res = self.opener(r, c)
                if self.on_step and self.on_step({
                        "cell": (r, c), "safe": is_safe_batch, "risk": risk,
                        "g": g, "move": self.moves, "result": res}) is False:
                    return None                     # dibatalkan (jendela ditutup)
                if self.verbose:
                    tag = "AMAN " if is_safe_batch else "TEBAK"
                    print(f"\nLangkah {self.moves}: {tag} -> buka ({r},{c})"
                          f"  risiko={risk:5.1%}  g={g:.3f}"
                          f"  P(selamat sejauh ini)={math.exp(-g):.1%}")
                    print(self.render(last=(r, c)))
                    self._wait()
                if res == LOSE:
                    return LOSE
                if res == WIN or game.solved():
                    return WIN
                if not is_safe_batch:
                    break                           # tebakan -> replan dengan info baru


# ----------------------------------------------------------------------------
def new_game(level, quiet=True):
    if quiet:                                       # Minesweeper banyak print debug
        with contextlib.redirect_stdout(io.StringIO()):
            return Minesweeper(level)
    return Minesweeper(level)


def benchmark(n, seed=0):
    random.seed(seed)
    names = {1: "easy (8x8,10)", 2: "intermediate (16x16,40)", 3: "expert (16x30,99)"}
    for level in (1, 2, 3):
        wins = first_move_deaths = 0
        for _ in range(n):
            s = UCSMinesweeperSolver(new_game(level))
            if s.solve() == WIN:
                wins += 1
            elif s.moves == 1:
                first_move_deaths += 1
        print(f"{names[level]:26s} menang {wins}/{n} = {wins / n:5.1%}"
              f"   (kalah di klik pertama: {first_move_deaths})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--bench", type=int, default=0, help="jumlah game per level")
    ap.add_argument("--demo", action="store_true", help="tampilkan log langkah")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--delay", type=float, default=0.0, help="jeda detik antar langkah")
    ap.add_argument("--pause", action="store_true", help="tunggu Enter tiap langkah")
    a = ap.parse_args()
    if a.seed is not None:
        random.seed(a.seed)
    if a.bench:
        benchmark(a.bench)
    else:
        game = new_game(a.level)
        solver = UCSMinesweeperSolver(game, verbose=True, delay=a.delay, pause=a.pause)
        result = solver.solve()
        print("\nPapan asli (semua ranjau terlihat):")
        game.printGame(1)
        print("HASIL:", "MENANG" if result == WIN else "KALAH",
              f"| langkah={solver.moves} tebakan={solver.guesses}",
              f"| P(selamat sepanjang jalur)={math.exp(-solver.g):.3%}")