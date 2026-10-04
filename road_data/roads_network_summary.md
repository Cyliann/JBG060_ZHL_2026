# South Sudan road-condition extraction: project summary

This document explains how the weekly road-access maps were turned into a single dataset (`roads_all.csv`) and a road-network graph (`.edges`, `.mtx`, nodes file). It covers the rules used, what changed week to week, the final clean-up, and how the graph was built.

## 1. Source material

The project files hold one access-constraints map per week from 2024-01-05 to 2025-12-24. Although they are named `.pdf`, each is really a zip containing only a low-resolution map image, so the road table could not be read from the files directly. Instead, screenshots of each week's road table were transcribed by hand, one week at a time.

Each map's table lists every road with an ID, a printed name (e.g. "Baliet – Akwot – Kiech kon"), a row colour for its condition, and the heaviest truck that can use it.

## 2. Output files

| File | What it is |
|---|---|
| `roads_all.csv` | The main dataset: one row per road per map date, 96 dates × 140 roads = 13,239 rows. IDs and names standardised to the 2025-12-24 map (see section 6). |
| `roads_all_as_printed.csv` | The same data before standardisation: IDs and names exactly as printed each week. Keeps the full rename history. |
| `roads_2025-12-24.edges` | Edge list of the road network on the last map: `node_a node_b weight`, one edge per line. |
| `roads_2025-12-24.mtx` | The same network in Matrix Market format (symmetric, lower triangle only). |
| `roads_2025-12-24_nodes.csv` | Node ID → place name lookup, plus each node's degree (number of connected roads). |

CSV columns: `road_id, date, from, to, conditions, condition_code, via, road_name_original, truck_type, note`.

## 3. Extraction rules

- **Condition comes from the row colour**, not the truck type:

  | Colour | Condition | Code |
  |---|---|---|
  | Green | passable | 0 |
  | Orange | partially passable | 1 |
  | Red | impassable | 2 |

  When colour and truck type disagree, colour wins. Examples: road 67 was orange but printed 40MT (2025-08-07), and road 98 was green but printed 20MT (from 2025-11-27).
- **Truck type** is recorded as printed: 40MT, 20MT, 15MT or Specialized Trucks. It is left empty for red rows.
- **from / to / via** are parsed from the printed name. The first place is `from`, the last is `to`, and anything in between goes in `via`, separated by `; `.
- **Place spellings** are merged into one name in the from/to/via columns, for example Kilo30 → Kilo 30, Mir mir → Mirmir, Yaui → Yuai, Lankein → Lankien and Dim Zubeir → Deim Zubeir.
- **Unchanged weeks** are recorded by copying the previous week's rows with the new date.
- **Every week is checked**: exactly one row per road ID, and no missing IDs.
- **Wrong printed IDs** are recorded under the correct ID, with an explanation in `note`.

## 4. Timeline

### 2024-01-05 → 2025-07-31 (80 maps, done earlier)

The network grew from 134 to 140 roads over this period:

| Road | Added |
|---|---|
| 135 | 2024-05-16 |
| 136–138 | 2024-06-21 |
| Panakuach – Pariang | 2024-11-01 |
| 140 Maiwut – Pagak | 2025-06-12 (split off from road 20) |

Several roads were renamed on the maps; the per-week names are kept in `roads_all_as_printed.csv`:

- Some renames dropped or added places. For example, road 88 lost Abwong and later gained Baliet; road 124 dropped Boma; road 127 dropped Rupkuai.
- Two segments moved from one road to another: Baliet–Akwot moved from road 7 to road 88 (2025-03-27), and Motot–Walgak moved from road 121 to road 12 (2025-05-22).

Some maps printed IDs incorrectly:

- Road 133 was printed as 132 (May–June 2024) and as 134 (2025-06-12 to 2025-10-02).
- Vertet – Labarab has been printed as 103 since 2025-05-22.
- Mabior – Kongor and Panakuach – Pariang have been printed with swapped IDs since 2024-11-01.

### 2025-08-07 → 2025-12-24 (16 maps)

IDs below use the final numbering (Mabior – Kongor = 139, Panakuach – Pariang = 138).

| Date | Passable | Partial | Impassable | Changes |
|---|---|---|---|---|
| 2025-08-07 | 38 | 42 | 60 | Opened to partially passable (Specialized Trucks): 40 Baidit – Mabior – Duk Padiet, 74 Duk Padiet – Ayod, 132 Ayod – Mogok, 139 Mabior – Kongor. Truck type changed: 38 Bor – Baidit (20MT → Specialized), 67 Mingkaman – Yirol (20MT → 40MT). |
| 2025-08-14 | 37 | 42 | 61 | 133 Kaikang – Roriak / Mayom – Kilo 30 became impassable (from passable). 67 back to 20MT. |
| 2025-08-21 | 37 | 42 | 61 | No change. |
| 2025-08-28 | 35 | 42 | 63 | 118 Bentiu – Kilo 30 and 98 Kilo 30 – Manga Port became partially passable (from passable). 70 Kodok – Paloich and 71 Malakal – Kodok became impassable (from partial). Road 98 printed in reverse order ("Kilo 30 – Manga Port"). |
| 2025-09-04 | 35 | 31 | 74 | 11 roads became impassable (from partial): the Bor–Pibor–Akobo corridor (37, 60, 39, 103, 59, 66, 30) and the Duk Padiet–Ayod area (40, 74, 132, 139). |
| 2025-09-11 | 35 | 31 | 74 | No change. |
| 2025-09-18 | 35 | 28 | 77 | 118, 98 and 138 Panakuach – Pariang became impassable (from partial). |
| 2025-09-25 | 35 | 28 | 77 | No change. |
| 2025-10-02 | 35 | 28 | 77 | No change. |
| 2025-10-31 | 33 | 31 | 76 | 9 Adar – Jemaam – Maban became partially passable (Specialized; from passable). 130 Mathiang – Udier became impassable (from passable). 98 and 133 became partially passable (20MT; from impassable). Road 133 printed with its correct ID again. |
| 2025-11-07 | 33 | 31 | 76 | No change. |
| 2025-11-14 | 33 | 31 | 76 | No change. |
| 2025-11-21 | 33 | 31 | 76 | No change. |
| 2025-11-27 | 35 | 29 | 76 | 9 became passable again. 98 became passable (green, printed 20MT). 73 Bentiu – Guit became partially passable (from impassable). 133 became impassable again. |
| 2025-12-04 | 38 | 29 | 73 | 34 Abiemnhom – Mayom, 133 and 138 Panakuach – Pariang became passable (40MT), straight from impassable. |
| 2025-12-24 | 38 | 29 | 73 | No change (last map). |

### Missing dates

There is no map in the project files for these dates:

- 2024-04-18
- 2024-10-25
- 2025-07-04
- 2025-10-09, 2025-10-16 and 2025-10-23
- 2025-12-11 and 2025-12-18

These dates were left out of the dataset rather than filled in.

The upload recorded as 2025-06-26 was labelled "2025-06-19" a second time. It differs from 06-19 only in road 43, so it was treated as the next week.

## 5. The 2026-09-24 map (not added to the dataset)

A 2026-09-24 map was also checked against the 2025 maps. It is not in the CSV, but it matters for any future work:

- **It has 104 roads, compared with 140.** The split is 38 passable, 43 partially passable and 23 impassable.
- **It uses a completely new ID scheme**: letter codes by area (B, C, E, J, L, N, Q, T, U, W, e.g. J01, T18), instead of 1–140.
- **About 63 roads match a 2025 road** (same places, allowing for spelling).
- **About 41 are new or redrawn.** Some have new places, such as Cueibet, Nyaruop Port, Nagero, Akoka and Canal Mabior Junction. Others are re-split, such as Adar – Maban and Mayom – Kaikang – Roriak.
- **Roughly 77 of the 2025 roads have no exact 2026 counterpart**, many of them in the Jonglei, Unity and Upper Nile red zones.
- Partially passable rows are yellow on this map instead of orange.

Because of this, the 2025 IDs could not simply be replaced with 2026 ones. The dataset was standardised to the last 2025 map instead (section 6). One suggested option for later is a separate `road_id_2026` column that is filled only where a road clearly matches.

The 2026 map was still useful for settling two spelling questions: it uses **Duk Padiet** and **Kaikuny**.

## 6. Standardising to the 2025-12-24 map

To give every road one consistent ID and name across the whole history, `roads_all.csv` was rewritten to match the last 2025 map. The un-standardised version is kept as `roads_all_as_printed.csv`.

**IDs**

- Mabior – Kongor is now **139** and Panakuach – Pariang is now **138** on every date, as printed on the last map.
  - Previously they were recorded the other way round (138 and 139).
  - As a result, there is **no road 138 from 2024-06-21 to 2024-10-18**, because Panakuach – Pariang did not exist yet.
- Vertet – Labarab stays **104**. The last map prints it as 103, but 103 is Manyabol – Gumuruk, and two roads cannot share an ID. The note on those rows explains this.
- Road 133 needed no change; the last map prints it correctly.

**Names**

- Every road now carries its 2025-12-24 `from`, `to`, `via` and `road_name_original` on all dates.
- This removes the rename history from the main file. For example, road 7 reads "Malakal – Baliet" even on dates when it was printed "Akwot – Baliet – Malakal", and road 20 no longer shows Pagak before the split.
- Use `roads_all_as_printed.csv` whenever the weekly printed names matter.

**Spelling merges**

- Two place-name questions left open earlier were settled using the 2026 map: Duk Padiat / Duk Fadiat → **Duk Padiet**, and Kainuny → **Kaikuny**.
- These merges apply to the from/to/via columns and the graph nodes. `road_name_original` keeps the printed spelling, e.g. "Duk Padiat – Pajut".

## 7. Building the graph

The network was built from the 2025-12-24 rows:

1. **Nodes**: every distinct place in from/to/via, sorted alphabetically and numbered from 1. This gives **140 nodes**.
2. **Segments**: each road becomes a chain of edges between consecutive places. For example, Baliet – Akwot – Kiech Kon becomes Baliet–Akwot and Akwot–Kiech Kon.
   - Road 133 is the exception. Its printed name lists two separate stretches, so it becomes Kaikang–Roriak and Mayom–Kilo 30 rather than one chain.
3. **Weights**: condition code + 1, giving 1 = passable, 2 = partially passable and 3 = impassable.
4. **Duplicates**: 162 segments collapsed to **160 edges**. Two place pairs appeared on two roads each: Adar–Jemaam (roads 9 and 85) and Nyambor–Pading (roads 109 and 110). Both copies had the same weight, so merging lost nothing.
5. **Edges are undirected.** The `.mtx` file declares itself symmetric and stores each edge once, in the lower triangle.

**Resulting network**

- 44 edges have weight 1, 32 have weight 2 and 84 have weight 3.
- The network is **not fully connected**; it has 8 separate pieces:
  - A main network of 110 places.
  - An Upper Nile group of 17: Renk, Paloich, Melut, Adar, Jemaam, Maban, Mathiang, Udier, Maiwut, Pagak, Kodok, Malakal, Baliet, Akwot, Nasser, Kiech Kon and Nyandit.
  - Six small isolated pieces: Aduel–Amok Piny–Madol, Diabio–Ezo, Nyal–Ganyiel, Hiyala–Ikotos, Paguir–Keew and New Fangak–Kuernyang.

  This reflects how the maps list the roads, not an extraction error. Keep it in mind for shortest-path or connectivity analysis.

## 8. Open points

- **2026 map**: decide whether to add a `road_id_2026` column, and how to handle roads that were split, merged or dropped.
- **Road 104 / 103 clash** on the last map: currently kept as 104.
- **Gap in ID 138** from 2024-06-21 to 2024-10-18, caused by the renumbering. Any check that expects consecutive IDs 1–N on every date will flag those weeks.
- **Weights for merged edges**: no conflict arose this time. If a future map has two roads over the same place pair with different conditions, a rule is needed (e.g. keep the better condition).
