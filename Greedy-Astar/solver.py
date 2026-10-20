"""
solver.py - Solver Minesweeper: Greedy vs A*
Bekerja langsung di atas kelas Minesweeper (minesweeper.py) tanpa GUI.

Pemakaian benchmark :  python solver.py --games 100 --levels 1 2 3
Pemakaian di game   :  solver = make_solver("astar"); r, c = solver.next_move(game)
"""
import argparse, heapq, io, itertools, random, time
from collections import defaultdict
from contextlib import redirect_stdout

from minesweeper import Minesweeper

DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ----------------------------------------------------------------------
# Pandangan papan: hanya informasi yang boleh dilihat pemain
# ----------------------------------------------------------------------
class Board:
    def __init__(self, game):
        self.g, self.R, self.C = game, game.x, game.y

    def neighbors(self, r, c):
        for dr, dc in DIRS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < self.R and 0 <= cc < self.C:
                yield rr, cc

    def is_open(self, r, c):
        return self.g.matrix[r][c].unlocked

    def number(self, r, c):
        # engine memakai -1 untuk petak "0" yang sudah dibersihkan cleanZeros
        v = self.g.matrix[r][c].mines_around
        return 0 if v == -1 else v


# ----------------------------------------------------------------------
# Kelas dasar: inferensi logika pasti (dipakai Greedy & A*)
# ----------------------------------------------------------------------
class BaseSolver:
    name = "base"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.mines = set()          # petak yang sudah pasti ranjau
        self.queue = []             # petak aman yang menunggu dibuka
        self.total = 0
        self.last_was_guess = False
        self.stats = {"deduksi": 0, "tebakan": 0, "node": 0}

    # --- constraint: (himpunan petak tertutup, jumlah ranjau di dalamnya)
    def _constraints(self, b):
        cons = set()
        for r in range(b.R):
            for c in range(b.C):
                if not b.is_open(r, c):
                    continue
                unk, m = [], 0
                for rr, cc in b.neighbors(r, c):
                    if b.is_open(rr, cc):
                        continue
                    if (rr, cc) in self.mines:
                        m += 1
                    else:
                        unk.append((rr, cc))
                if unk:
                    cons.add((frozenset(unk), b.number(r, c) - m))
        return list(cons)

    @staticmethod
    def deduce(cons):
        """Aturan dasar + aturan subset sampai tidak ada perubahan."""
        safe, mines = set(), set()
        changed = True
        while changed:
            changed = False
            new = set()
            for cells, need in cons:
                cells2 = cells - safe - mines
                if cells2:
                    new.add((cells2, need - len(cells & mines)))
            cons = list(new)
            for cells, need in cons:
                if need == 0 and not cells <= safe:
                    safe |= cells; changed = True
                elif need == len(cells) and not cells <= mines:
                    mines |= cells; changed = True
            if changed:
                continue
            for a, na in cons:                      # aturan subset
                for b2, nb in cons:
                    if a < b2:
                        diff, nd = b2 - a, nb - na
                        if nd == 0 and not diff <= safe:
                            safe |= diff; changed = True
                        elif nd == len(diff) and not diff <= mines:
                            mines |= diff; changed = True
        return safe, mines

    def infer(self, b, cons, unknown):      # hook untuk subclass
        return set(), set()

    def guess(self, b, cons, unknown):      # wajib di-override
        raise NotImplementedError

    def _pick_min(self, risk, prefer=None):
        best = min(risk.values())
        cand = sorted(x for x, v in risk.items() if v <= best + 1e-9)
        if prefer:
            pref = [x for x in cand if x in prefer]
            cand = pref or cand
        return self.rng.choice(cand)

    # --- satu langkah keputusan
    def next_move(self, game):
        b = Board(game)
        self.total = game.mines
        self.last_was_guess = False
        self.queue = [x for x in self.queue if not b.is_open(*x)]
        if self.queue:
            return self.queue.pop(0)

        if not any(b.is_open(r, c) for r in range(b.R) for c in range(b.C)):
            return (0, 0)                   # langkah pertama: pojok (peluang nol tertinggi)

        while True:
            cons = self._constraints(b)
            safe, mines = self.deduce(cons)
            new = mines - self.mines
            self.mines |= mines
            if safe or not new:
                break

        unknown = [(r, c) for r in range(b.R) for c in range(b.C)
                   if not b.is_open(r, c) and (r, c) not in self.mines]
        remaining = self.total - len(self.mines)
        if not safe and remaining == 0:
            safe = set(unknown)             # semua ranjau sudah ketemu
        if not safe:
            s2, m2 = self.infer(b, cons, unknown)
            safe |= s2
            self.mines |= m2
        if safe:
            self.stats["deduksi"] += 1
            self.queue = sorted(safe)
            return self.queue.pop(0)

        self.last_was_guess = True
        self.stats["tebakan"] += 1
        return self.guess(b, cons, unknown)


# ----------------------------------------------------------------------
# GREEDY: tebak petak dengan risiko lokal terkecil saat ini (tanpa lookahead)
# ----------------------------------------------------------------------
class GreedySolver(BaseSolver):
    name = "Greedy"

    def guess(self, b, cons, unknown):
        risk = {}
        for cells, need in cons:
            p = need / len(cells)
            for x in cells:
                risk[x] = max(risk.get(x, 0.0), p)      # risiko terburuk dari tetangga
        dens = (self.total - len(self.mines)) / len(unknown)
        for x in unknown:
            risk.setdefault(x, dens)                    # petak non-frontier: kepadatan global
        return self._pick_min(risk)


# ----------------------------------------------------------------------
# A*: cari konfigurasi ranjau frontier yang konsisten, urut dari yang paling mungkin
# ----------------------------------------------------------------------
def astar_enumerate(cells, cons, max_mines, max_sol=400, max_nodes=6000):
    """
    State  : assignment parsial (0/1) untuk cells[0..k-1]
    Aksi   : tetapkan petak ke-k sebagai aman(0) / ranjau(1)
    g(n)   : jumlah ranjau yang sudah ditempatkan
    h(n)   : max_c (kebutuhan_c - ranjau_terpasang_c)  -> admissible & konsisten
    Goal   : semua petak terisi & semua constraint terpenuhi
    Goal keluar urut dari jumlah ranjau paling sedikit (= paling mungkin).
    """
    n = len(cells)
    pos = {c: i for i, c in enumerate(cells)}
    C = [(sorted(pos[x] for x in cs), need) for cs, need in cons]
    touch = [[] for _ in range(n)]
    for ci, (ps, _) in enumerate(C):
        for p in ps:
            touch[p].append(ci)

    def feasible(a, idx):
        for ci in touch[idx]:
            ps, need = C[ci]
            m = left = 0
            for p in ps:
                if p <= idx: m += a[p]
                else: left += 1
            if m > need or m + left < need:
                return False
        return True

    def h(a):
        k, best = len(a), 0
        for ps, need in C:
            m = sum(a[p] for p in ps if p < k)
            best = max(best, need - m)
        return best

    tie = itertools.count()
    heap = [(h(()), 0, next(tie), 0, ())]       # (f, -kedalaman, urutan, g, assignment)
    sols, nodes = [], 0
    while heap:
        f, _, _, g, a = heapq.heappop(heap)
        nodes += 1
        if len(a) == n:
            sols.append(a)
            if len(sols) >= max_sol:
                return sols, False, nodes
            continue
        if nodes >= max_nodes:
            return sols, False, nodes
        for v in (0, 1):
            if g + v > max_mines:
                continue
            na = a + (v,)
            if feasible(na, len(a)):
                heapq.heappush(heap, (g + v + h(na), -len(na), next(tie), g + v, na))
    return sols, True, nodes


class AStarSolver(BaseSolver):
    name = "A*"

    def __init__(self, seed=None):
        super().__init__(seed)
        self.risk, self.interior_risk = {}, 0.0

    @staticmethod
    def _components(cons):
        cell_cons = defaultdict(list)
        for i, (cs, _) in enumerate(cons):
            for x in cs:
                cell_cons[x].append(i)
        seen, comps = set(), []
        for i in range(len(cons)):
            if i in seen:
                continue
            seen.add(i)
            queue, ci, order, seen_cells = [i], [], [], set()
            while queue:
                k = queue.pop(0)
                ci.append(k)
                for x in sorted(cons[k][0]):
                    if x not in seen_cells:
                        seen_cells.add(x); order.append(x)
                        for j in cell_cons[x]:
                            if j not in seen:
                                seen.add(j); queue.append(j)
            comps.append((order, [cons[k] for k in ci]))
        return comps

    def infer(self, b, cons, unknown):
        remaining = self.total - len(self.mines)
        dens = min(max(remaining / len(unknown), 1e-6), 1 - 1e-6)
        ratio = dens / (1 - dens)
        self.risk, safe, mines, expected = {}, set(), set(), 0.0
        for cells, ccons in self._components(cons):
            sols, exhaustive, nodes = astar_enumerate(cells, ccons, remaining)
            self.stats["node"] += nodes
            if not sols:                                  # fallback
                for cs, need in ccons:
                    for x in cs:
                        self.risk[x] = max(self.risk.get(x, 0), need / len(cs))
                continue
            kmin = min(sum(s) for s in sols)
            tot, cnt, hit = 0.0, defaultdict(float), defaultdict(int)
            for s in sols:
                w = ratio ** (sum(s) - kmin)              # bobot: rasio ranjau^jumlah
                tot += w
                for i, v in enumerate(s):
                    if v:
                        cnt[i] += w; hit[i] += 1
            for i, x in enumerate(cells):
                p = cnt[i] / tot
                self.risk[x] = p
                expected += p
                if exhaustive:                            # pasti hanya jika enumerasi lengkap
                    if hit[i] == 0: safe.add(x)
                    elif hit[i] == len(sols): mines.add(x)
        interior = [x for x in unknown if x not in self.risk]
        self.interior_risk = (max(0.0, remaining - expected) / len(interior)) if interior else 1.0
        return safe, mines

    def guess(self, b, cons, unknown):
        risk = {x: self.risk.get(x, self.interior_risk) for x in unknown}
        return self._pick_min(risk, prefer=set(self.risk))   # seri -> pilih frontier (lebih informatif)


SOLVERS = {"greedy": GreedySolver, "astar": AStarSolver}

def make_solver(name, seed=None):
    return SOLVERS[name.lower()](seed)


# ----------------------------------------------------------------------
# Benchmark headless
# ----------------------------------------------------------------------
def _new_game(level):
    with redirect_stdout(io.StringIO()):
        return Minesweeper(level)

def run_game(cls, level, seed):
    random.seed(seed)                       # papan identik untuk kedua solver
    while True:
        game, solver = _new_game(level), cls(seed)
        move = solver.next_move(game)
        if not game.matrix[move[0]][move[1]].mine:
            break                           # klik pertama aman (engine tidak menjamin ini)
    t0, moves, won = time.perf_counter(), 0, False
    while moves <= game.x * game.y:
        with redirect_stdout(io.StringIO()):
            res = game.playerDecision(move[0], move[1], 1)
        moves += 1
        if res == 2:
            break
        if res == 1 or game.solved():
            won = True
            break
        move = solver.next_move(game)
    return won, moves, time.perf_counter() - t0, solver.stats

def benchmark(games, levels):
    names = {1: "Easy 8x8/10", 2: "Inter 16x16/40", 3: "Expert 16x30/99"}
    print(f"{'Level':16}{'Solver':8}{'Menang':>8}{'Langkah':>9}{'Tebakan':>9}{'Node A*':>9}{'ms/game':>9}")
    for lv in levels:
        for cls in (GreedySolver, AStarSolver):
            w = mv = gs = nd = tm = 0
            for s in range(games):
                won, moves, t, st = run_game(cls, lv, s)
                w += won; mv += moves; gs += st["tebakan"]; nd += st["node"]; tm += t
            print(f"{names[lv]:16}{cls.name:8}{100*w/games:7.1f}%{mv/games:9.1f}"
                  f"{gs/games:9.1f}{nd/games:9.0f}{1000*tm/games:9.1f}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 3])
    a = ap.parse_args()
    benchmark(a.games, a.levels)
