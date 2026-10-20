# Minesweeper Solver: Greedy, A*, dan UCS

## Tujuan

Proyek ini adalah pembuktian penerapan tiga algoritma pencarian pada game Minesweeper, yaitu **Greedy**, **A\*** (A Star), dan **UCS** (Uniform Cost Search). Setiap algoritma memainkan game secara otomatis di atas GUI, sehingga cara kerja dan perbedaan hasilnya dapat diamati langsung.

- **Greedy** memilih petak dengan risiko lokal terkecil saat itu, tanpa melihat ke depan.
- **A\*** mencari konfigurasi ranjau yang konsisten dengan semua angka di papan, lalu memilih petak dengan probabilitas ranjau terendah.
- **UCS** memilih langkah berdasarkan biaya kumulatif terkecil.

## Struktur Folder

```
.
├── UCS/             # versi UCS
│   └── main.py
└── Greedy_Astar/    # versi Greedy dan A*
    ├── main_greedy.py
    └── main_astar.py
```

## Persyaratan

- Python 3
- PySimpleGUI

```bash
pip install PySimpleGUI
```

## Cara Menjalankan

**UCS**

Buka folder `UCS`, lalu jalankan:

```bash
cd UCS
python main.py
```

**Greedy**

Buka folder `Greedy_Astar`, lalu jalankan:

```bash
cd Greedy_Astar
python main_greedy.py
```

**A\***

Buka folder `Greedy_Astar`, lalu jalankan:

```bash
cd Greedy_Astar
python main_astar.py
```

Pada menu, pilih **Singleplayer** dan tingkat kesulitan (Easy, Intermediate, atau Expert). Solver akan membuka petak satu per satu hingga game selesai.

## Kredit

Game Minesweeper dasar (logika permainan dan GUI) berasal dari repositori asli karya Lucas Rennok:
https://github.com/lucasrennok/Minesweeper/tree/master

Proyek ini menambahkan algoritma solver (Greedy, A\*, dan UCS) di atas game tersebut.
