# SESI 2026-08-14 (#12) — **F13 DITUTUP** + tiga temuan pemilik: form wajib pakai MASTER · kartu punya latar

> **Permintaan user:** *"lanjutkan development dari repo ini
> https://github.com/hajsisifufjsj/DA — sebelumnya development terhenti di
> `Now registering gate INV-F13 (one edit at a time, then syntax check)`"*
> lalu ditambah dua temuan: *"lauching product … masih belum tersambung dengan
> product yang ada di katalog masih custom field input … jangan sampai ada cacat
> logic seperti ini di form lainya pastikan kembali, silahkan verifikasi dulu
> untuk semua form lainya"* dan *"beberapa page di portal marketing cardsnya
> masih belum terdesign dengan baik seperti lupa di kasih background cardsnya,
> lalu ada beberapa yang masih abu abu itu perbaiki."*
> **Pilihan user:** urutan A → B → C; Fase B dibatasi 4–6 layar UANG/STOK paling mahal.

## 0) TITIK BERHENTI — DIUKUR, BUKAN DITEBAK

| Yang mungkin diduga | Kenyataan sesudah bring-up |
|---|---|
| "F13 belum dikerjakan" | **SALAH.** Keempat layar (`FinanceKasbon`, `EmployeeExpenseApproval`, `WMSFabricRolls`, `WMSDeliveryNotes`) sudah punya tabel ≥8 kolom + pengalih + urut + halaman + unduh; `test_core_f13` **39/39** pada jalan PERTAMA |
| "gate.sh tinggal ditambah entri" | **SALAH.** `insert_text` terakhir sesi lalu menyisipkan `fi` LIAR di baris 380 ⇒ `bash -n scripts/gate.sh` = *syntax error near unexpected token `else`* ⇒ **gate.sh tidak bisa dijalankan sama sekali** |
| — | **YANG BENAR-BENAR HILANG:** perbaikan `gate.sh`, entri gate `INV-F13`, dan dokumen sesi #12 |

Bring-up: `/app` datang sebagai template kosong ⇒ klon + `rsync` (env platform dipertahankan)
+ `bootstrap.sh` (92 detik, 6 akun HTTP 200). Frontend tetap **bundel statis**
(`scripts/rebuild_frontend.sh` sesudah setiap ubah `src`) — kuota 1 core / 2 GiB.

## 1) FASE A — F13 DITUTUP

| # | Isi | Bukti |
|---|---|---|
| A1 | `fi` liar dibuang; **satu edit, lalu `bash -n`** (aturan sesi #11) | `bash -n` lolos · 466 baris · ekor berkas utuh |
| A2 | gate **INV-F13** didaftarkan di bagian **STATIK** — sengaja BUKAN di blok `AUTH_READY`: penjaganya membaca BERKAS layar, bukan HTTP; kalau ditaruh di blok backend ia akan di-`skip` tiap backend mati, padahal justru saat itulah regresi layar paling mungkin lolos | `scripts/gate.sh` |
| A3 | `test_core_f13_layar_uang_bisa_dibawa.py` **39/39 HIJAU** | keluaran uji |
| A4 | **Dibuktikan MERAH lewat sabotase** (`rows={csvRows}` → daftar mentah) ⇒ `C-2·kasbon` gagal (38/39) ⇒ dipulihkan | keluaran uji |

## 2) TEMUAN PEMILIK #1 — "LAUNCHING PRODUCT MASIH CUSTOM FIELD"

### Yang diukur (bukan dugaan)
`marketing_product_launches`: **8 dari 8** dokumen tanpa `model_id`. Nama/bahan/model
teks bebas ("Gamis Busui Friendly DA-2026 Series 1", "Katun Linen Premium"), padahal
`rahaza_models` berisi produk DA sungguhan beserta varian FG, HPP, dan harga resmi.

**Kenapa ini bukan soal kenyamanan mengetik — tiga akibat berantai:**
1. **Master stok kotor.** `_auto_create_fg_from_launch()` MEMBUAT barang jadi dari teks:
   `code = style_code OR model OR product_name.replace(" ","-").upper()[:30]` ⇒ FG
   `GAMIS-BUSUI-FRIENDLY-DA-2026-S` tanpa `model_id`, tanpa varian, `hpp = 0`, kategori
   literal `"launch"`. Satu produk jadi **dua** barang di master stok ⇒ "stok produk ini
   berapa?" punya **dua jawaban** — dan tidak ada satu pun galat, hanya sebaris log info.
2. **Harga tak bisa direkonsiliasi** — rencana (ketikan) vs katalog (`harga_jual`) vs
   master (`retail_price`); tidak ada yang tahu ketiganya berhubungan.
3. **Ejaan = identitas** — "Katun Linen Premium" ≠ "katun linen premium" bagi mesin.

### Yang dikerjakan
* **`MasterProductSelect`** (`components/erp/pickers/`) — SATU pemilih ber-pencarian yang
  membaca `GET /api/marketing/catalogs/master-products`, endpoint **yang sama** dengan layar
  Katalog dari Master ⇒ dua layar mustahil menampilkan daftar produk berbeda.
* **`_resolve_master_model()`** — satu-satunya penulis field turunan master. Mengikuti
  pelajaran `received_at`/`closed_at`: **kiriman browser DIABAIKAN**. Dibuktikan runtime:
  POST membawa `product_name: "NAMA PALSU KIRIMAN BROWSER"` ⇒ yang tersimpan
  `"Celana Jogger Tapered Fit"`. PUT juga tidak bisa menimpanya (`MASTER_DERIVED_FIELDS`).
* **`model_id` WAJIB** pada pembuatan; produk tak dikenal / non-aktif ditolak **400 dengan
  alasan + jalan keluar**, bukan "gagal menyimpan".
* **Barang jadi kembar tidak bisa lahir lagi** — `_auto_create_fg_from_launch()` sekarang
  MENAUTKAN ke varian FG master yang sudah ada; tidak ada `insert_one` ke `rahaza_materials`.
  Dibuktikan: `launched` ⇒ jumlah FG **330 → 330**.
* **Warisan DIAKUI, bukan ditebak** — server menghitung `master_link.unlinked_total`, layar
  menampilkan banner amber + penanda "belum tertaut" per baris, form Edit mengatakan
  keadaannya. Migrasi `relink_product_launches_to_master.py` membuang **contoh** yang
  melanggar aturan (data contoh yang salah MENGAJARKAN pola salah) tetapi **menolak menebak**
  padanan untuk dokumen NYATA — menebak = menautkan ke produk salah tanpa bisa dibedakan.
* **Seeder** menyemai dari master; kalau master kosong, **0 contoh** (layar kosong + petunjuk
  lebih jujur daripada 8 rencana untuk produk yang tidak ada).

## 3) TEMUAN PEMILIK #2 — "VERIFIKASI SEMUA FORM LAIN"

`scripts/_audit_form_master_refs.py` memindai **582 layar** untuk 10 konsep ber-master.

**Jalan pertama: 13 temuan di 9 layar. Sesudah ditriase, 4 di antaranya TUDUHAN SALAH** —
dan itu penting: penjaga yang salah tuduh berhenti dipercaya, dan penjaga yang tidak
dipercaya sama dengan tidak ada penjaga (pelajaran sesi #10). Yang dikecualikan **beserta
alasannya**:

| Layar | Kenapa BUKAN cacat |
|---|---|
| `EmployeeExpenseGLMappingModule.category` | kategori **BIAYA** (Transportasi/Konsumsi) — dan form ini justru yang mendefinisikannya |
| `HRKPIModule.category` | kategori penilaian **KPI** ("Tanggung Jawab") |
| `CreateAssetDialog.model` | model **ASET IT** ("XPS 13 9310") — master aset tidak menyimpan daftar model laptop |
| `MaklonBuyerCatalogModule.product_name` | form ini **ADALAH** master katalog buyer; produk yang sedang dibuat belum ada di master mana pun |

**Yang benar-benar cacat & diperbaiki:**
| Layar | Perbaikan |
|---|---|
| `ProductLaunchModule` | 3 kotak ketik → `MasterProductSelect`; bahan & kode model jadi read-only dari master |
| `AIContentGeneratorModule` | produk dari master; kategori/material read-only; warna dari varian master. **Teks ini TAYANG ke pembeli** — bahan karangan di caption adalah klaim produk yang salah. Backend meresolusi ulang dari `model_id` dan menyimpannya di riwayat |
| `CMTComponentRequestModule` | produk dari master lewat `_resolve_product_from_master()` (opsional, karena permintaan bisa lahir dari inspeksi sebelum produk ditentukan — tetapi kalau diisi, WAJIB ada di master) |
| `MaklonAIQuoteModule` | `BuyerCatalogSelect` **dua mode**: artikel dari katalog, atau "artikel baru" yang DITANDAI `is_new_article`. Melarang teks bebas di sini justru berbahaya: staf akan memilih artikel yang MIRIP supaya form mau lanjut ⇒ penawaran menempel pada artikel yang salah |

**Dua jebakan audit yang sempat membuatnya BOHONG (dan sudah dijaga):**
* `product_name: e.target.value` ikut cocok dengan pola "diisi dari objek lain" ⇒ audit
  melaporkan **0 temuan padahal semua kotak ketik masih utuh**. Objek event kini dikecualikan.
* Aturan "ada pemilih di berkas ⇒ temuan gugur" terlalu longgar — satu berkas bisa punya
  pemilih **dan** kotak ketik sekaligus, dan justru itu bentuk yang paling mudah lolos.

## 4) TEMUAN PEMILIK #3 — "CARDS LUPA BACKGROUND, ADA YANG ABU-ABU"

Ketiganya punya satu sifat: **tidak pernah menjadi galat**, jadi build & lint tetap HIJAU
sementara layarnya rusak.

| Cacat | Jumlah | Sebab | Perbaikan |
|---|---|---|---|
| **Kelas Tailwind RUSAK** `bg-foreground/[0.06]0` | **23** di 9 berkas | find/replace massal gagal: `bg-white/60` → ganti `white/6` jadi `foreground/[0.06]` → `…[0.06]0`. Angka nyasar sesudah `]` ⇒ Tailwind **tidak menghasilkan CSS apa pun** ⇒ elemen benar-benar tanpa latar | dipetakan ke padanan sadar-tema per KONTEKS (`bg-background/60`, `border-border`, `border-foreground/30`). Perkecualian disengaja: `UniversalScanPortal` memakai panel `bg-zinc-900` yang selalu gelap ⇒ `border-white/10` memang jawaban yang benar |
| **Abu-abu di atas abu-abu** `text-muted-foreground/50\|60\|70` pada `bg-muted` | **56** | `muted-foreground` sudah warna redup; modifikator opasitas hanya mencampurnya ke latar. Rasio kontras **1.9–2.6** (lantai 3.0) di tema terang MAUPUN gelap | modifikator dibuang ⇒ rasio ± 4.3 terang / 4.9 gelap |
| **Cadangan token MUSTAHIL** `localStorage.getItem('auth_token')` | **30** | `auth_token` **tidak pernah ditulis** (`setItem('auth_token')` = **0** kejadian); kunci yang benar `erp_token`. Begitu prop `token` kosong ⇒ `Bearer null` dan layar berkata "gagal memuat" tanpa sebab | semua → `erp_token`. Cadangan yang mustahil bekerja LEBIH BURUK daripada tidak ada cadangan: ia membuat orang berhenti mencurigai token |

**Bonus (ditemukan lewat lint saat memeriksa yang di atas):** `PickingListModal` memakai
`accountFilter` milik komponen **INDUK** ⇒ `ReferenceError` = layar putih begitu modal
dibuka. JavaScript baru mengeluh saat baris itu dijalankan, jadi build tidak pernah merah.
Sekarang dikirim sebagai prop — sekaligus membuat daftar picking mengikuti toko yang dipilih,
bukan diam-diam semua toko.

Audit yang mengukurnya (`scripts/_audit_ui_card_contrast.py`) **MENGHITUNG rasio kontras
WCAG**, bukan memakai ambang opasitas kasar. Versi pertama memakai "opasitas < 100 = cacat"
dan menuduh `text-foreground/80` yang rasionya **8.6** — sangat terbaca.

## 5) BUKTI

* `python3 test_core_f13_layar_uang_bisa_dibawa.py` → **39/39** · sabotase ⇒ 38/39 MERAH
* `python3 test_core_f14_form_pakai_master.py` → **34/34** · sabotase (kotak ketik nama
  produk dikembalikan) ⇒ 33/34 MERAH, dan **audit ikut menangkapnya**
* `python3 test_core_f15_kartu_terbaca.py` → **13/13** · sabotase (kelas rusak dikembalikan)
  ⇒ 12/13 MERAH
* `bash scripts/gate.sh` → **HIJAU** (3 gate baru: INV-F13 · INV-F14 · INV-F15)
* **Uji LAYAR** (Playwright, bundel statis): form Launching tidak lagi punya kotak ketik
  nama/bahan/model; pemilih master berisi 5 produk; memilih `CLN-0001` mengisi kategori
  *Celana*, HPP *Rp 76.000*, harga resmi *Rp 175.000*, 2 varian, dan Harga Asli otomatis
  *175000* — **0 page error · 0 console error**
* Runtime: POST tanpa `model_id` ⇒ **422** · `model_id` palsu ⇒ **400 dengan alasan** ·
  nama palsu kiriman browser ⇒ **diabaikan** · `launched` ⇒ FG **330 → 330** (0 produk kembar)

## 7) FASE B — **5 LAYAR UANG/STOK BERIKUTNYA DITUTUP** + cacat kelas dinamis

### Yang dipilih (dengan satu pertanyaan: kalau salah, berapa mahalnya?)

| Layar | Kelas | Kenapa mahal kalau salah |
|---|---|---|
| `HRKasbonModule` | UANG | antrian persetujuan kasbon — yang disetujui menjadi POTONGAN GAJI |
| `KasbonStaffModule` | UANG | riwayat kasbon karyawan sendiri; bukti yang sering diminta HR/Finance |
| `ReceivingModule` | STOK | **pintu masuk seluruh stok**; kolom *qty ditolak* adalah dasar klaim ke supplier |
| `ProcurementRequestModule` | UANG | permintaan pengadaan = komitmen belanja |
| `AccessoriesDashboard` | STOK+UANG | nilai stok aksesoris (Rp 9,66 juta) + item yang **belum dinilai** ⇒ ikut laporan keuangan |

**Tidak dipilih (dan alasannya dicatat):** `PutAwayModule` berbentuk **wizard 3 langkah**,
bukan layar daftar. Memasang tabel di situ akan merusak alurnya — pola tidak boleh
dipaksakan hanya supaya angka "layar KARTU-SAJA" turun.

### Keputusan yang tidak kosmetik
* **Pengurutan Pengadaan dipindah ke SERVER** (`sort_by`/`sort_dir` + daftar putih kolom).
  Kalau layar mengurutkan sendiri, ia hanya bisa mengurutkan halaman yang sedang dibuka:
  pertanyaan yang membuat kolom itu ada — *"PR mana yang nilainya PALING BESAR?"* — akan
  dijawab dengan urutan 15 baris pertama, dan **jawabannya terlihat meyakinkan padahal
  salah**. Itu lebih berbahaya daripada tidak ada pengurutan.
* **Item aksesoris yang belum dinilai DIAKUI di layar** (banner + penanda `BELUM`): selama
  angkanya > 0, total nilai stok pasti LEBIH RENDAH dari kenyataan — dan angka itu masuk
  laporan keuangan.
* **`PaginationLite` dipakai juga untuk paginasi SERVER** di Pengadaan, sehingga label
  "Menampilkan a–b dari N" menyebut jumlah SEBENARNYA, bukan jumlah baris yang kebetulan
  sedang dirender.

### CACAT BARU YANG DITEMUKAN SAAT MENGERJAKANNYA — kelas Tailwind DIRAKIT saat berjalan

    className={`bg-${color}-500/5 border border-${color}-500/20 …`}

Tailwind menghasilkan CSS dengan **membaca teks berkas sumber**; ia tidak menjalankan
JavaScript. Kelas itu **tidak pernah dibuat**. Yang membuatnya nyaris mustahil dilihat:
kadang kelasnya KEBETULAN ada karena berkas LAIN memakainya secara harfiah.

**Diukur langsung pada bundel hasil build (`main.*.css`) sebelum perbaikan:**
`bg-violet-500/5` **ADA** · `bg-teal-500/5`, `border-teal-500/20`, `border-teal-500/25`
**TIDAK ADA** ⇒ pada komponen KPI yang **sama**, kartu "violet" tampil benar sementara
kartu **"Perlu Diserahkan" (teal)** tampil **polos tanpa latar dan tanpa garis**. Itu
persis keluhan pemilik, dan sebabnya bukan selera.

Ditutup lewat `lib/tone.js` (nama warna boleh dinamis, **kelasnya harfiah**) untuk
**21 kejadian di 7 berkas**. Sesudah rebuild, `bg-teal-50`/`border-teal-200`/`bg-teal-100`
ada di CSS.

**Bonus (ditemukan lewat lint):** `TabBtn` di Pengadaan didefinisikan **di dalam** komponen
induk ⇒ React melihat TIPE komponen baru setiap render dan membongkar-pasang subtree-nya:
fokus keyboard hilang & state ter-reset saat pemakai sedang mengetik di penyaring. Gejalanya
terasa seperti "kadang aplikasinya nge-lag", jadi hampir tidak pernah dilaporkan sebagai bug.

### Bukti Fase B
* `test_core_f13_layar_uang_bisa_dibawa.py` diperluas 4 → **9 layar** ⇒ **84/84 HIJAU**
* Ambang KARTU-SAJA **diketatkan 74 → 69** (kalau dibiarkan longgar, layar baru tanpa tabel
  & unduhan lolos diam-diam dan "kemajuan" hanya berarti tidak memburuk)
* `test_core_f15_kartu_terbaca.py` **15/15** (penjaga kelas dinamis ditambahkan)
* `bash scripts/gate.sh` → **VERDICT HIJAU**
* `testing_agent_v3` iterasi 64: backend **4/4** · frontend **100%** · tampilan **100%** ·
  regresi **100%** · **0 bug**
* Uji LAYAR: kartu KPI teal kini berlatar; tabel stok aksesoris menampilkan **2 item belum
  dinilai** dengan banner yang menjelaskan akibatnya

## 6) URUTAN KERJA BERIKUTNYA

| Fase | Isi | Status |
|---|---|---|
| **B** | Konsolidasi **5 layar UANG/STOK** non-marketing (HRKasbon · KasbonStaff · Receiving · ProcurementRequest · AccessoriesDashboard) | ✅ **SELESAI** — KARTU-SAJA 74 → **69** |
| **C** | **F9 Pencairan/Settlement** — dibangun sebagai **INPUT MANUAL** (keputusan pemilik). Blokir BD-2 dihapus: tidak ada kolom yang ditebak. Jurnal **DRAFT**, selisih wajib DINAMAI sebelum bisa dijurnal | ✅ **SELESAI** |
| **D** | Sisa konsolidasi layar (69 kartu-saja · 133 tabel tanpa pengalih) · impor berkas pencairan saat contoh asli tersedia | ⏳ BERIKUTNYA |
| — | 3 toko DEMO tidak muncul di pemilih toko (penyaring `status=active`, dokumen DEMO tanpa field itu). Tidak mengganggu, layak dirapikan | 📝 |
| — | Master produk belum punya field **bahan**; `composition` terisi **0/331** FG ⇒ layar jujur menulis "Belum dicatat di Master Produk". Melengkapinya = pekerjaan Master Produk, bukan tambal di form | 📝 |

---

# SESI 2026-08-14 (#11) — **F11 + F12 DITUTUP**: pratinjau impor per baris · berkas ekspor tidak boleh masuk toko yang salah

> **Permintaan user:** *"saya ingin anda lanjutkan development dari repo ini
> https://github.com/gantengtyihajsa/da — titik berhenti development ada di
> `execute_bash sed -n '255,345p' scripts/gate.sh`"* (agent sesi lalu sedang MEMBACA
> `gate.sh` untuk mencari tempat mendaftarkan gate berikutnya).
> **Pilihan user sesi ini:** (1) tutup F11 dulu sampai HIJAU + terdaftar di gate;
> (2) sesudahnya: F9 Settlement · kualitas impor lanjutan · konsolidasi layar non-marketing.

## 0) TITIK BERHENTI — DIUKUR, BUKAN DITEBAK

| Yang mungkin diduga | Kenyataan sesudah bring-up |
|---|---|
| "F11 belum dikerjakan" | **SALAH.** Backend (`/plan`, `/plan.csv`, `/result.csv`, `_plan_rows`, `_diff_changes`, `_commit_blockers`) **dan** layar (`ImportPlanPanel.jsx`, sudah di-*wire* ke langkah 5 `DataImportWizard.jsx`) sudah LENGKAP |
| "penjaganya belum ada" | **SALAH.** `test_core_f11_pratinjau_impor.py` (26 KB) sudah ditulis — tetapi **belum pernah dijalankan** |
| — | **YANG BENAR-BENAR HILANG:** entri gate `INV-F11` di `scripts/gate.sh` (persis berkas yang sedang dibaca saat berhenti), plus dokumen sesi (#11 tidak ada di `plan.md`/`CHANGELOG.md`) |

Bring-up: `/app` datang sebagai template kosong ⇒ klon ulang + `rsync` (env platform
dipertahankan). **Pod restart di tengah `yarn build`** (gejala berulang sesi #8/#9/#10):
build SELESAI tetapi seed TIDAK jalan ⇒ DB kosong padahal login admin sukses.
Dipulihkan `bootstrap.sh --skip-deps` (54 detik, idempoten) ⇒ 6 akun HTTP 200, bundel statis 200.
Kuota container dikonfirmasi lagi: `cpu.max = 1 core` · `memory.max = 2 GiB` ⇒ **bundel statis
DIPERTAHANKAN** (jangan `craco start`).

## 1) YANG DIKERJAKAN (Fase 1 = F11, SELESAI)

| # | Isi | Bukti |
|---|---|---|
| 1a | `test_core_f11_pratinjau_impor.py` dijalankan pertama kali ⇒ **36/36 PASS** | keluaran uji |
| 1b | **Dibuktikan MERAH lewat sabotase**: `_diff_changes` dipaksa `return [], 0` ⇒ `B-10` GAGAL (35/36) ⇒ dipulihkan | keluaran uji |
| 1c | **11 penjaga BARU** menutup janji yang belum dijaga apa pun: `A-9`/`A-10` (tabel + chip 5 akibat + cari + halaman + unduh; `total` halaman WAJIB dari server), `E-2b` (CSV rencana benar-benar memuat NILAI lama→baru, bukan hanya judul kolom), `F-1..F-6` (penyaring & halaman JUJUR), `B-12`/`B-13` (perubahan palsu & baris tanpa perubahan yang menjelaskan diri) | **47/47 PASS** |
| 1d | **CACAT NYATA ditemukan lewat UJI LAYAR** (lihat §2) + ditutup di SATU tempat (`_norm_dt`) | `B-12` MERAH saat disabotase (4 temuan) |
| 1e | gate **INV-F11** didaftarkan (`run_gate` + daftar `skip_gate` saat backend mati) | `scripts/gate.sh` |
| 1f | Uji LAYAR 6 cerita (Playwright, bundel statis) | **0 page error · 0 console error** |

**Gate:** `bash scripts/gate.sh` → **29/29 VERDICT HIJAU** (`memory/GATE_RECEIPT.md`).

## 2) CACAT YANG 45 PENJAGA BACKEND TIDAK BISA LIHAT — "PERUBAHAN PALSU"

Mode **"Perbarui yang lama"** di layar memajang, untuk **setiap** baris:

    Waktu Pesanan Dibuat: 2026-08-05 10:15 → 2026-08-05 10:15

**Sebabnya:** MongoDB mengembalikan `datetime` **naive** (isinya UTC), sedangkan berkas yang
baru dibaca menghasilkan `datetime` **ber-zona** (`timezone.utc`). Di Python `aware == naive`
**selalu** False ⇒ setiap kolom tanggal dilaporkan "berubah".

**Kenapa ini bukan cacat kosmetik:**
* staf belajar **mengabaikan** kolom "yang berubah" — padahal kolom itulah alasan panel ini ada;
* perubahan PALSU **memakan kuota tampilan** (`_DIFF_MAX = 14`) ⇒ perubahan **NYATA** bisa
  terdorong ke ringkasan "+N field lain" dan tidak terlihat sama sekali;
* catatan jujur *"tidak ada nilai yang berubah — hanya penanda waktu pembaruan yang ditulis"*
  **tidak pernah muncul**, karena daftar perubahan tidak pernah kosong.

**Ditutup di SATU tempat:** `_norm_dt()` menyamakan bentuk waktu sebelum dibandingkan, dipakai
`_same()` yang sudah menjadi satu-satunya pembanding (`_diff_changes` + `_plan_fulfillment_row`).
Penjaga `B-12` (tidak boleh ada perubahan dengan `before == after`) & `B-13` (baris "diperbarui"
tanpa perubahan wajib mengatakannya) mencegahnya terulang.
Diperiksa juga apakah kelas cacat yang sama ada di jejak audit: `marketing_change_log` **bersih**
(50 perubahan tercatat, 0 palsu) ⇒ tidak perlu ditambal.

## 3) BUKTI LAYAR (Playwright, bundel statis, 0 page error)

| Cerita | Hasil |
|---|---|
| A — rencana baris BARU | chip «semua 4 · 4 baru · 0 diperbarui · 0 sebagian · 0 dilewati · 0 ditolak», tabel 5 kolom berisi 4 baris, teks "4 baris menyentuh data · 0 tidak diapa-apakan · 0 tidak masuk" |
| B — chip & pencarian | saring «baru» ⇒ 4 badge semuanya `baru`; chip «ditolak» **nonaktif** karena 0; cari `DEMO-A-1001` ⇒ **1 baris**; dikosongkan ⇒ 4 baris |
| C — mode mengubah angka | Lewati ⇒ **4 dilewati** + alasan "sudah ada (duplikat) · status sekarang: paid"; Perbarui ⇒ **4 diperbarui**; kembali ke Lewati ⇒ **4 dilewati** (angka hidup, bukan angka mati) |
| D — unduh rencana | `rencana-impor.csv` benar-benar terunduh (fetch ber-token, bukan `window.open`) |
| E — penghalang | panel merah **"Simpan akan DITOLAK — 1 penghalang"** + kalimat lengkap dengan jalan keluarnya, dan tombol **"Simpan 4 baris" MATI** (title menjelaskan sebabnya) |
| F — regresi | Riwayat impor tetap berisi + tombol "Batalkan impor" ada |

**Kebersihan:** seluruh jejak uji dibersihkan lewat rollback/DELETE resmi ⇒
`marketing_orders` kembali **559**, 0 pesanan `DEMO-A-*`, 0 sesi impor uji, **0 periode terkunci**.

> Catatan tentang `testing_agent_v3` (iterasi 61): agen itu **tidak berhasil** memilih toko di
> `Select` Radix, lalu menyimpulkan cerita B–E "berfungsi" dari **membaca kode**. Itu BUKAN bukti,
> jadi keenam cerita diverifikasi ulang oleh main agent lewat Playwright (tabel di atas).
> Resep memilih opsi Radix yang berhasil: klik trigger `[data-testid=…]`, tunggu, lalu iterasi
> `[role="option"]` dan klik yang teksnya cocok.

## 5) FASE 2 — **F12 SELESAI**: berkas ekspor tidak boleh masuk ke toko yang salah

### Lubang yang diukur (bukan ditebak)
Penjaga toko yang sudah ada ternyata **hanya menempel pada SATU jenis data**
(`marketplace_orders`): `platform_guard` ("berkas Shopee masuk toko TikTok") dan
`shop_guard` (gudang platform di berkas bukan gudang toko tujuan). Diukur atas 22 jenis data:

| Jenis | platform_guard | shop_guard | Akibat kalau salah pilih toko |
|---|---|---|---|
| `marketplace_orders` | ✅ | ✅ | terjaga |
| **`marketplace_fulfillment` (Ekspor B/C)** | ❌ | ❌ | hanya "3 baris ditolak: belum pernah diimpor" — BENAR tetapi menyembunyikan sebabnya |
| 20 jenis lain (KPI, iklan, konten, komplain, retur, …) | ❌ | ❌ | **MASUK ke toko yang salah tanpa satu pun galat** |

Kalimat "belum pernah diimpor" bukan cacat kecil: staf menyimpulkan berkasnya rusak, lalu
(jauh lebih mahal) memilih jenis **"Pesanan Marketplace"** supaya "mau masuk" ⇒ pesanan
**HANTU** tanpa item, tanpa omzet, tanpa kreator — dan jumlah pesanan bulan itu naik tanpa
ada penjualan.

### Yang dikerjakan — BUKTI, bukan dugaan
1. **`SourceType.identity`** — tanda pengenal GLOBAL satu baris (nomor pesanan platform ·
   nomor komplain · URL konten). Kalau tanda itu sudah tercatat pada toko LAIN, itu FAKTA
   bahwa berkasnya milik toko itu. 7 jenis mendapat `identity`; kepemilikan nomor pesanan
   selalu diperiksa di SSOT `marketing_orders` (bukan koleksi turunan retur/ulasan).
2. **`NO_IDENTITY_REASON`** — 15 jenis yang isinya MEMANG tanpa penanda toko terdaftar
   **beserta alasannya** (mis. statistik toko Shopee hanya berisi tanggal + kanal; setiap toko
   punya tanggal yang sama ⇒ memakainya sebagai tanda pengenal akan **MENUDUH SALAH**).
   Dijaga `A-1`: jenis baru tanpa `identity` dan tanpa alasan ⇒ gate MERAH.
3. **Ambang yang tidak boleh dibalik** — mayoritas baris milik toko lain ⇒ **PENGHALANG**
   (commit 409, tombol Simpan MATI); minoritas ⇒ **PERINGATAN** yang tetap boleh disimpan
   (berkas gabungan, dan staf yang justru sedang memperbaiki keadaan tidak boleh terkunci).
4. **Bukti kedua untuk jenis tanpa penanda toko** — `content_sha256`: berkas dengan ISI sama
   persis yang sudah DISIMPAN ke toko lain (satu berkas ekspor tidak mungkin milik dua toko).
   Riwayat lama yang belum ber-sidik dihitung **di memori** (25 calon: jenis sama + jumlah
   baris sama) — jalur pratinjau tetap **tidak menulis apa pun**.
5. **SATU sumber** — `_shop_evidence()` dipakai `_commit_blockers()` (jadi commit menolak
   dengan kalimat yang sama persis) dan pratinjau. Kode pesan ditulis 1× (dijaga `A-3`).

### Bukti
* `python3 test_core_f12_sidik_toko.py` → **28/28 PASS**, dan **dibuktikan MERAH lewat
  sabotase** (`_shop_evidence` dilumpuhkan ⇒ **7 penjaga gagal**, termasuk `B-7` yang menerima
  **HTTP 200** untuk berkas toko lain — lubangnya nyata, bukan teoretis).
* `bash scripts/gate.sh` → **30/30 VERDICT HIJAU** (gate baru **INV-F12**).
* **Uji LAYAR** (Playwright, 0 page error · 0 console error): berkas *Shopee Daluna* diunggah
  ke *Shopee Moen* ⇒ panel MERAH *"4 dari 4 nomor pesanan … sudah tercatat pada toko LAIN —
  Shopee Daluna (mis. DEMO-A-1001, DEMO-A-1002, DEMO-A-1003) … Ganti toko tujuan ke 'Shopee
  Daluna'"* + panel KUNING *"Berkas dengan ISI yang sama persis sudah pernah disimpan ke toko
  'Shopee Daluna' pada 2026-08-14 19:28 oleh admin@garment.com"* + tombol **Simpan MATI**.
* Seluruh jejak uji dibersihkan lewat rollback resmi ⇒ `marketing_orders` kembali **559**.

### PELAJARAN LINGKUNGAN (mahal, jangan diulang)
Dua `search_replace` **paralel pada berkas yang SAMA** (`scripts/gate.sh`) melahirkan
**korupsi senyap**: entri gate F12 hilang, dan 44 baris terakhir berkas terduplikasi
setengah jalan (`ODUK — payslip karyawan"…`). `bash` **menyembunyikannya** karena
`exit $OVERALL` dieksekusi sebelum sampah itu terbaca — gate tetap "HIJAU 29/29" padahal
gate ke-30 tidak pernah jalan. Ditemukan oleh `bash -n`. **Aturan: satu berkas = satu edit
per waktu, dan `bash -n scripts/gate.sh` setiap kali gate.sh disentuh.**

## 6) URUTAN KERJA BERIKUTNYA

| Fase | Isi | Status |
|---|---|---|
| **3** | Konsolidasi layar **non-marketing** (Produksi/Gudang/Keuangan) memakai pola tabel F10 | ⏳ BERIKUTNYA |
| **4** | **F9 Settlement/Pencairan** — berkas ASLI owner belum ada ⇒ dibangun tanpa MENEBAK format (pemetaan kolom oleh staf + label "pemetaan belum diverifikasi") | ⏳ |
| — | Catatan: 3 toko DEMO (`SHOPEE-OFFICIAL`, `SHOPEE-RESELLER`, `TIKTOK-STORE`) tidak muncul di pemilih toko layar karena pemilihnya menyaring `status=active` sementara dokumen DEMO tidak punya field itu. Tidak mengganggu (uji layar memakai toko nyata), tetapi layak dirapikan | 📝 |


---

# SESI 2026-08-14 (#9) — **RENCANA & HASIL**: gate MERAH ditutup · retur terlihat · F6 · F10 · kualitas impor

> **Permintaan user:** *"lanjutkan development dari repo ini https://github.com/sakkajxxy/da — titik
> berhentinya: rebuild selesai, verifikasi layar impor bertindih HIJAU (panel 'sudah ada di sistem'
> = 1, 4 baris duplikat terdeteksi, 0 page error), tetapi `bash scripts/gate.sh` melaporkan
> **VERDICT: MERAH** padahal semua baris yang terlihat PASS."*

## 0) TITIK BERHENTI — DIUKUR, BUKAN DITEBAK

`/app` datang sebagai template kosong ⇒ repo diklon ulang + `rsync` (env platform dipertahankan) +
`scripts/bootstrap.sh`. Pod **restart di tengah `yarn build`** (gejala yang sama seperti sesi #8);
dipulihkan dengan `bootstrap.sh --skip-deps` ⇒ 6 akun login **HTTP 200**, bundel statis HTTP 200.

**Kenapa `grep FAIL` sesi lalu tidak menemukan apa pun:** `head -5` memotong keluaran; lima
kecocokan pertama adalah ringkasan INTERNAL skrip (`FAIL 0`), bukan baris gate. Baris yang benar
ada di `memory/GATE_RECEIPT.md`: **tepat satu gate FAIL**.

| Dugaan sesi lalu | Kenyataan |
|---|---|
| `INV-KPIIMPOR` gagal karena `reason` jadi WAJIB di sesi #8b | **SALAH** — `test_core_f7_kpi_impor.py` **40/40 PASS** |
| — | **`INV-MKTCYCLE` (`verify_marketing_cycle.py`) → `CYC-5c` GAGAL** |

### Cacat sesungguhnya (soal KEJUJURAN ANGKA, bukan tes yang cerewet)
`core/marketing_cycle._data_notes()` pada keadaan "belum ada pesanan per baris" hanya berbunyi
*"Marjin belum bisa dihitung: tidak ada pesanan per baris pada bulan ini"* — kata **HPP tidak pernah
muncul**. Akibatnya pembaca layar melihat **marjin 0%** tanpa pernah tahu SEBABNYA, dan "belum ada
dasar hitung" mudah dibaca sebagai "jualan tanpa untung". Catatan kejujuran sekarang menyebut HPP
terbuka: *"Marjin & HPP belum bisa dihitung … HPP hanya diketahui dari pesanan yang tertaut item
katalog — rekap yang diketik/diimpor per hari tidak membawa HPP."*

### Cacat kedua: environment segar melahirkan MERAH & layar kosong yang bukan salah produk
Empat seeder hanya hidup sebagai **perintah manual di HANDOFF**, jadi siapa pun yang cuma
menjalankan `bootstrap.sh` mendapat: 9 toko NYATA hilang (cuma 3 toko DEMO), `marketing_orders`
KOSONG ⇒ `CYC-8` di-SKIP, katalog tanpa varian internal ⇒ HPP tak punya dasar join. Keempatnya
sekarang **terdaftar di `scripts/bootstrap.sh`** (idempoten, lewat API resmi):
`seed_marketing_real_accounts.py --apply` · `seed_internal_variants.py` ·
`seed_katalog_order_demo.py` · `seed_marketing_cycle_demo.py`.

**BUKTI:** `bash scripts/gate.sh` → **25/25 · VERDICT HIJAU** (receipt: `memory/GATE_RECEIPT.md`).

## 1) KEPUTUSAN PEMILIK YANG DIAMBIL SESI INI

| Pertanyaan | Jawaban owner |
|---|---|
| Pesanan `returned` dikeluarkan dari omzet? | **Tampilkan DUA-DUANYA** — omzet bruto (tidak berubah) **dan** omzet setelah retur |
| Prioritas berikutnya | **Ketiganya**: F6 RBAC per toko + layar "siapa mengubah apa" · F10 konsolidasi layar marketing · kualitas impor bertindih |
| Berkas asli owner (Ekspor B/C, Settlement, `shop_kpi`, Shopee Orders) | belum ada ⇒ **F9 settlement TIDAK dimulai**, label "pemetaan belum diverifikasi" tetap dipasang |
| Cakupan uji | `gate.sh` cepat + `testing_agent_v3` per fitur |

## 2) URUTAN KERJA SESI INI

| Fase | Isi | Status |
|---|---|---|
| **0** | bring-up + `CYC-5c` ditutup + 4 seeder masuk bootstrap ⇒ gate HIJAU | ✅ SELESAI |
| **1** | **RETUR TERLIHAT** — satu kalkulator kanonik: `revenue_gross` (tetap) · `returned_amount` · `returned_orders` · `revenue_net_returns`; tampil di Siklus, Scorecard Kreator (+CSV), rekap harian/mingguan, Portal Manajemen; gate **INV-RETUR** membuktikan angka lama TIDAK bergeser | ✅ SELESAI — `test_core_returns_visibility.py` **51/51**, gate **26/26 HIJAU**, `testing_agent_v3` iter 10 **22/22 · 0 bug**, layar 0 page error (bruto Rp 59.783.811 tetap · setelah retur Rp 57.561.529) |
| **2** | **F6** — `scope_filter`/`assert_account_visible` ke endpoint marketing yang masih unscoped + endpoint & **layar "Perubahan Marketing"** (filter toko/entitas/pelaku/tanggal, paginasi, CSV) + gate | ⏳ |
| **3** | **F10** — modul marketing KARTU-SAJA → tabel nyata (cari/sort/paginasi/CSV), diukur ulang `_audit_ui_tables_v2.py` | ⏳ |
| **4** | **Kualitas impor** — pratinjau "apa yang akan berubah" per baris sebelum commit (tanpa berkas owner) | ⏳ |

Aturan yang dipegang: satu rumus satu tempat (`core/marketing_cycle.py`, `core/marketing_daily_rollup.py`,
`core/order_status.py`) · setiap fitur baru wajib **layar + penjaga di `test_core_*` + entri gate** ·
setiap ubah `frontend/src` wajib `bash scripts/rebuild_frontend.sh` · gate hanya boleh menghapus
dokumen BERTANDA gate.

---

# SESI 2026-08-14 (#8c) — **IMPOR BERTINDIH**: deteksi dobel di pratinjau + lubang stok/uang ditutup

> Pertanyaan pemilik: impor tanggal 1–7 lalu 5–12 ⇒ apakah dobel tanggal 5–7 terdeteksi, dan apakah
> baris yang sama (kunci: no. pesanan) ikut terupdate bila di berkas baru statusnya berubah jadi
> dibatalkan?

**Jawabannya YA untuk keduanya**, tetapi audit menemukan **cacat uang/stok** pada jalur itu:
mode "Perbarui yang lama" menulis `status` dengan `$set` mentah ⇒ pesanan yang dibatalkan berkas
baru **tidak melepas reservasi stok** (risiko barang sama dijanjikan ke dua pembeli), tetap di
antrean gudang, dan status bisa **MUNDUR** saat berkas lama diunggah ulang. Sekarang status wajib
lewat SSOT `core.order_status.apply_status` (`forward_only` + bukti batal/retur + pelepasan
reservasi + jejak), dan penolakan transisi dijelaskan di catatan hasil.

**Deteksi dobel dipindah ke PRATINJAU** (dulu hanya muncul sesudah commit): respons unggah/pemetaan
membawa `duplicates` = jumlah `existing`/`new`, kunci dedupe yang dipakai, rentang tanggal berkas,
**rentang tanggal yang bertindih**, dan contoh baris + status sekarang. Layar langkah 5
menampilkannya persis di atas pemilih "Lewati / Perbarui yang lama".

**Bukti:** `test_core_f8_assign_ingat_scorecard.py` **47/47 PASS** (13 penjaga baru seksi `[D]`).

**Catatan penting:** pencocokan **per BARIS** (kunci dedupe), **bukan per rentang tanggal** — jadi
mengimpor rentang beririsan tidak pernah melahirkan baris kembar. Untuk **laporan iklan Shopee**
justru sebaliknya: periode yang beririsan **ditolak 409** karena biayanya per-periode (anti dobel
hitung anggaran).

---

# SESI 2026-08-14 (#8b) — **F8 SELESAI**: Assign Toko (SPV) · “Ingat Pemetaan Saya” · Scorecard Kreator

> Permintaan user: **(1)** “Selesaikan layar SPV untuk menetapkan staf pemegang tiap toko lengkap
> dengan riwayatnya”, **(2)** “Tawarkan pemetaan kolom yang tersimpan dari impor sebelumnya agar
> berkas rutin harian langsung siap sekali klik”, **(3)** “Tampilkan konten dan omzet tiap kreator
> dengan target vs aktual, tanpa mencampur GMV KPI dan omzet pesanan”.

## 0) TEMUAN AUDIT — ketiganya SUDAH ADA, yang belum ada justru yang membuatnya bisa DIPERCAYA

| Fitur | Keadaan sebelum sesi ini | Yang sebenarnya hilang |
|---|---|---|
| Assign Toko | endpoint + layar (tab “Assign Staf”) lengkap | **alasan tidak wajib** (padahal kepala berkasnya menjanjikan), **jejaknya dimusnahkan gate**, tidak ada sudut pandang per-ORANG, staf nonaktif tak ditandai |
| Ingat Pemetaan | mesin sudah mengingat & memakai ulang pemetaan | **diingat DIAM-DIAM** (layar tak pernah menyebutnya), **tidak bisa dilupakan**, **pemetaan basi diterima apa adanya** |
| Scorecard Kreator | 15 kolom, 3 sumber uang dipisah, basis penilaian tertulis | **tidak bisa ditelusuri** (tak ada jalan melihat konten/pesanan/sesi pembentuk angka), tanpa paginasi/CSV, dan **layarnya selalu kosong** karena tak ada seed kreator |

### CACAT NYATA YANG DITEMUKAN & DITUTUP
`test_core_f7_kpi_impor.py` membersihkan dirinya dengan
`delete_many({"account_id": aid, "entity": "marketing_platform_accounts"})` pada
`marketing_change_log`. Toko uji = **toko shopee aktif pertama (toko NYATA)**. Artinya **setiap
`bash scripts/gate.sh` memusnahkan seluruh riwayat “siapa memegang toko ini”** — satu-satunya
jawaban untuk “kenapa akses toko saya dicabut?”. Diukur: `marketing_change_log` = **0 dokumen**
walau log backend memuat perubahan assign. Sekarang hanya baris bertanda `[gate-kpiimpor]` yang
dihapus, dan penjaga statik `A-2e` menahannya kalau kembali longgar.

## 1) YANG DIKERJAKAN

### A. Assign Toko (SPV)
* **Backend** (`routes/marketing_account_assign.py`): `reason` **WAJIB** (≥4 huruf ⇒ 400 dengan
  contoh kalimat) diperiksa SESUDAH validasi daftar staf supaya galat spesifik tidak tertutup ·
  `GET /by-staff` (satu staf memegang toko apa; **staf dengan 0 toko ikut terdaftar** — dialah yang
  melihat layar kosong) · `GET /history` (riwayat SEMUA toko, berpaginasi, berlingkup F6) ·
  staf berakun **NONAKTIF** ditandai + `warnings[]` (“tidak ada orang yang bisa login untuk toko
  ini”) · `overview` menambah `unassigned_count`/`stale_count` (toko yang seluruh pemegangnya
  nonaktif dihitung **belum terpegang**).
* **Layar** (`AccountAssignView.jsx`): **3 tampilan** (Per Toko · Per Staf · Riwayat) · pencarian +
  filter “hanya yang belum terpegang” + paginasi 10/hal · tombol **Simpan terkunci** sampai alasan
  diisi (dengan hint yang menjelaskan kenapa) · **panel akibat MENETAP** (nama toko, alasan yang
  tercatat, efek 403, peringatan akun nonaktif) — bukan toast 5 detik.

### B. “Ingat Pemetaan Saya”
* **Backend** (`routes/marketing_data_import.py`): respons unggah kini membawa **`format_memory`**
  (`use_count`, `last_used_at`, `last_used_by`, `saved_at`, `dropped[]`) · pemetaan tersimpan
  **DIVALIDASI terhadap skema**: entri yang menunjuk field yang sudah tidak ada **dibuang** dan
  kolomnya **dipetakan ulang mesin** (dulu diterima apa adanya ⇒ kolomnya hilang dari hasil tanpa
  galat) · kolom berkas yang tidak ada di ingatan tetap memakai hasil mesin ·
  `GET /formats` (daftar yang diingat) · `DELETE /formats/{fingerprint}?source_type=` (**lupakan**).
* **Layar** (`DataImportWizard.jsx`): panel **“Pemetaan ini DIINGAT dari impor sebelumnya”** —
  dipakai N×, terakhir oleh siapa & kapan, **“ini bukan tebakan AI”**, peringatan bila ada pemetaan
  yang dibuang · tombol **“Lupakan pemetaan ini”** + keterangan menetap sesudahnya · dialog daftar
  semua susunan kolom yang diingat (bisa dibuka **sebelum** unggah dari langkah 3).

### C. Scorecard Kreator
* **Backend** (`routes/marketing_targets.py`): `GET /creator/{id}/detail` — **konten · pesanan ·
  sesi** baris demi baris; totalnya memakai **sumber rumus yang SAMA** dengan scorecard
  (`EXCLUDED_FOR_REVENUE`, `order_revenue_product`) sehingga wajib sama persis; pesanan yang
  dikecualikan **tetap tampil** dengan `counted:false` + sebabnya.
  **PERLU KEPUTUSAN PEMILIK (dibuat TERLIHAT, tidak diubah diam-diam):** `EXCLUDED_FOR_REVENUE`
  hanya memuat `cancelled`, jadi pesanan **`returned` IKUT dihitung** sebagai omzet. Mengubahnya
  menyentuh F2 (rekap harian) & F5 (siklus target) sekaligus ⇒ respons rincian memuat catatan
  “PERLU KEPUTUSAN PEMILIK …” beserta jumlah & nilainya.
* **Layar** (`CreatorScorecardView.jsx`): klik **“Lihat asalnya”** ⇒ dialog rincian (4 kartu total +
  3 tab daftar, tanpa satu pun angka gabungan) · paginasi 10/hal · pencarian kreator ·
  **unduh CSV** (kolom uang tetap terpisah, sengaja tanpa kolom “total”) · CTA “Tetapkan target
  kreator”.
* **Seeder** `backend/scripts/seed_marketing_creator_demo.py` (idempoten, **tidak** membuat master
  toko baru, sengaja menyisakan 1 kreator tanpa target & 2 konten tanpa KPI) + didaftarkan di
  `scripts/bootstrap.sh`. Tanpa ini layar Scorecard selalu berbunyi “belum ada kreator” pada
  environment segar — fitur jadi tampak belum jadi dan cacatnya tak pernah terlihat.

## 2) BUKTI

* `python3 test_core_f8_assign_ingat_scorecard.py` → **34 PASS · 0 GAGAL**.
* **Dibuktikan MERAH (25/34)** saat tiga fitur dilepas sekaligus (alasan dijadikan opsional,
  `format_memory` dimatikan, pembersihan gate dikembalikan ke versi lama) → dipulihkan ⇒ 34/34.
* `bash scripts/gate.sh` → **25/25 VERDICT HIJAU** (gate baru **INV-MKTOPS**).
* Verifikasi layar sendiri (Playwright, bundel statis baru), **0 console/page error**:
  A1 3 tampilan + cari (“1 dari 3 toko”) + paginasi · A2 Simpan terkunci tanpa alasan (juga saat
  “ab”), sesudah disimpan panel akibat menetap menyebut alasannya · A3 Riwayat global memuat baris
  baru (pelaku · ditambah · alasan) & Per Staf berubah 0 ⇒ 1 toko · B1 dialog daftar format ·
  B2 panel “sudah dipakai 2× — terakhir oleh admin@garment.com” · B3 lupakan ⇒ panel hilang +
  keterangan menetap · C1 3 kreator dengan **3 basis penilaian berbeda**, 1 “Belum ada target” +
  CTA, cari “rina” ⇒ 1 baris · C2 dialog rincian (Konten 5 · Pesanan · Sesi 2) dengan tanda
  “tidak dihitung” beserta sebabnya · regresi 3 tab konten + Daftar Toko tanpa crash.
* Agen uji (iter 57 & 58): **0 bug ditemukan**; keduanya berhenti karena sesi Playwright antar
  panggilan terputus (batasan lingkungan uji) — sisa cerita diselesaikan main agent dalam satu sesi.

## 3) SISA / LANGKAH BERIKUTNYA

1. **KEPUTUSAN PEMILIK:** apakah pesanan **`returned`** harus keluar dari omzet? Kalau ya, itu
   perubahan lintas-F2/F5 (rekap harian + siklus target + scorecard) dan wajib satu kartu kerja
   sendiri beserta gate-nya.
2. Berkas **Ekspor B & C asli** masih dibutuhkan untuk melepas label “pemetaan perlu diperiksa”.
3. Sesi live kreator masih dua bentuk field (`viewers` vs `peak_viewers` di seeder lama
   `scripts/seed_marketing_demo.py`) — seeder itu satu-satunya penulis yang tidak menulis
   `viewers`, sehingga kolom “Penonton” 0 untuk data lamanya. Rapikan bila seeder itu dipakai lagi.

---

# SESI 2026-08-14 (#8) — **F3 SELESAI**: Impor Ekspor B/C (status pengiriman) + “Batalkan impor” yang menepati janji

> Lanjutan sesi #7 yang berhenti **di tengah edit layar** (`DataImportWizard.jsx`): JSX penolong
> pemetaan sudah ditulis, tetapi dua fungsinya (`sampleFor`, `unmappedCols`) **belum pernah
> didefinisikan** ⇒ layar “Pemetaan kolom” pasti **crash** (ReferenceError) saat dibuka.
> Sesi ini menutup itu dan MENYELESAIKAN seluruh sisa kartu F3 (F3.D … F3.K).

## 0) TITIK BERHENTI SESI SEBELUMNYA (diukur, bukan dugaan)

| Kartu | Status saat sesi ini dimulai |
|---|---|
| F3.A mesin pemulihan `update_only` | SELESAI (backend) |
| F3.B rollback sesi `update_only` | SELESAI (backend) |
| F3.C endpoint `undo-report` + angka pemulihan disimpan di sesi | SELESAI (backend) |
| F3.G `test_core_f3_fulfillment.py` 52/52 | SELESAI |
| **F3.D** ringkasan hasil khusus `update_only` | **separuh** (badge & 2 peringatan ada; layar HASIL masih generik) |
| **F3.E** UI pemetaan pintar | **RUSAK** (`sampleFor`/`unmappedCols` tidak ada ⇒ crash) |
| **F3.F** Riwayat impor (kolom “Diperbarui”, tombol jujur, laporan pemulihan) | belum |
| F3.H gate · F3.I rebuild+verifikasi layar · F3.J testing agent · F3.K dokumen | belum |

Lingkungan juga harus dibangun ulang dari repo (`/app` datang sebagai template kosong):
`rsync` repo → `/app` (env platform dipertahankan) → `bash scripts/bootstrap.sh`. Pod **restart di
tengah build** (06:00) sehingga seed sempat kosong; diselesaikan dengan `bootstrap.sh --skip-deps`
(seed OK, 6 akun login 200).

## 1) YANG DIKERJAKAN & MENGAPA (semuanya soal salah-baca yang mahal)

### F3.E — layar “Pemetaan kolom” yang bisa DIPERIKSA (dan tidak crash)
* **`sampleFor(column)`** → kolom baru **“Contoh isi”** (nilai asli baris pertama yang tidak kosong,
  dibaca dari `preview[].original`, tanpa permintaan jaringan tambahan). Tanpa ini staf memilih
  field untuk nama kolom yang tidak ia kenali — misalnya `Order SN` vs `Order ID`.
* **`unmappedCols`** → kalimat “N kolom berkas tidak dipakai — itu boleh” (kolom tak dikenal
  **tidak** ditebak diam-diam).
* **`requiredHints`** → **pembalikan** usulan mesin: dari *kolom → field* menjadi
  **field WAJIB → kolom kandidat**, tampil sebagai tombol **“pakai kolom «X» (98%)”**. Tanpa
  pembalikan itu, satu-satunya petunjuk adalah badge kecil “wajib belum terpetakan”, dan staf harus
  membuka 40+ dropdown untuk mencari kolom yang cocok.
* **Backend (`core/marketing_import_engine.auto_map` + `_cand_list`)**: pilihan mesin sekarang JUGA
  dicatat sebagai **usulan #1**. Sebelumnya kolom `exact`/`synonym` punya `candidates: []`, sehingga
  begitu staf melepas kolom itu (“— tidak dipakai —”) **usulannya hilang selamanya**.
* Badge “N kolom punya usulan menunggu keputusan Anda” + skor keyakinan pada badge `mirip/perlu dipilih`.

### F3.D — layar HASIL untuk impor “hanya memperbarui”
Empat kartu yang sama dipakai untuk dua bentuk impor yang artinya berbeda. Pada Ekspor B/C
**“Baris masuk 0” adalah hasil yang BENAR**, tetapi staf membacanya sebagai gagal lalu mengunggah
ulang Ekspor A — dan justru pengulangan itu yang mengembalikan pesanan yang sudah dikirim ke
“perlu dikirim”. Sekarang: urutan kartu dibalik (**Pesanan diperbarui** jadi kartu utama), angka 0
diberi keterangannya sendiri, ada kartu **“Bisa dipulihkan”**, plus larangan eksplisit
*“Jangan unggah ulang Ekspor A untuk memperbaiki angka ini”*.
Backend: `_commit_message()` — kalimat hasil menyebut arti angkanya (bukan “0 baris masuk”),
dan respons commit menambah `update_only` + `undo_count`.

### F3.F — Riwayat impor yang jujur
* Kolom **“Diperbarui”** (`updated_count`) di samping “Masuk”, plus keterangan tabel; baris
  `update_only` diberi badge **“hanya memperbarui”** dan kolom Masuk-nya ditandai 0 by-design.
* Tombol berlabel **“Batalkan & pulihkan”** (bukan “Batalkan impor”) untuk jenis `update_only` —
  dua akibat berbeda tidak boleh memakai satu label.
* **Dialog konfirmasi memuat angka sebenarnya** (dibaca dari `undo-report` SEBELUM tombol dipakai):
  berapa pesanan yang dikembalikan, dan peringatan bahwa pesanan **batal/retur tidak dihidupkan**.
* **Dialog “Laporan pemulihan”** (menetap, bisa dibuka lagi besok dari Riwayat): 7 angka
  (diperbarui · dipulihkan · status dipulihkan · hanya field · sudah tidak ada · jejak belum/sudah
  dipakai), catatan per pesanan **dalam bahasa manusia** (bukan JSON), dan tabel jejak
  (No. Pesanan · status sebelum diimpor · sudah dipulihkan kapan). Sesudah pembatalan, laporan ini
  **dibuka otomatis** bila ada pemulihan — angka “N pesanan hanya field-nya yang dipulihkan” adalah
  pekerjaan manual yang mustahil dikerjakan dari toast 5 detik.

## 2) BUKTI (bukan klaim)

* `python3 test_core_f3_fulfillment.py` → **55 PASS · 0 GAGAL** (52 lama + 3 penjaga baru).
* **Penjaga baru dibuktikan MERAH saat fiturnya dilepas**: dengan `_cand_list` dikembalikan ke
  `candidates[:3]`, **F3-M8 & F3-M10 FAIL** (53/55) → lalu dipulihkan ⇒ 55/55.
  * `F3-M8` kolom yang dilepas TETAP menyimpan usulan mesin (sekali klik bisa dikembalikan)
  * `F3-M9` pratinjau membawa isi asli per kolom (kolom “Contoh isi” tidak kosong)
  * `F3-M10` field WAJIB yang dilepas: laporan menyebutnya **DAN** masih ada kolom yang mengusulkannya
* Gate: `run_gate "… (INV-MKTFULFILL)"` ditambahkan di `scripts/gate.sh` (+ daftar SKIP saat backend mati).
* Verifikasi layar sendiri (Playwright, bundel statis baru): kartu jenis (2 badge) → langkah 2 →
  unggah `samples/ekspor_B_status_dikirim_contoh.csv` → langkah 4 (**Contoh isi** terisi:
  `DEMO-A-1001`, `Dikirim`, `JX1234567890`) → lepas field wajib ⇒ panel merah + tombol
  **“pakai kolom «Order Status» (98%)”** + tombol “Lihat pratinjau” **terkunci** → satu klik ⇒ siap →
  commit ⇒ **Diperbarui 2 · Ditolak 1 · Baris masuk 0 (“0 memang benar”) · Bisa dipulihkan 2** →
  Riwayat (kolom Diperbarui = 2) → “Batalkan & pulihkan” ⇒ pratinjau menyebut **2 pesanan** →
  laporan pemulihan (2 dipulihkan, jejak 2 dipakai, tabel `DEMO-A-1001/1002` ← `paid`).
* Berkas contoh baru untuk staf & agen uji: `samples/ekspor_A_pesanan_contoh.csv`,
  `samples/ekspor_B_status_dikirim_contoh.csv`, `samples/ekspor_C_batal_retur_contoh.csv`.

## 3) KONTRAK SSOT

`memory/SSOT_KONTRAK_DATA_2026-08-12.md` → section baru **§PEMULIHAN IMPOR —
`marketing_data_import_undo`** (field, idempotensi, `_NEVER_RESTORE`, `_TERMINAL_KEEP`, angka
pemulihan yang disimpan di sesi, kunci periode) + field sesi yang WAJIB dibaca layar.

## 4) SISA / LANGKAH BERIKUTNYA

1. **Pemetaan Ekspor B/C masih berlabel “belum diverifikasi”** — labelnya baru bisa dilepas setelah
   owner mengirim **berkas Ekspor B & C asli** (yang ada sekarang disusun dari bentuk Ekspor A).
2. Tiga tugas user yang masih menunggu dari sesi #7: **Impor KPI Shopee (F7.2)** sudah ada
   (`shopee_*` source types + `test_core_f7_kpi_impor.py`) — sisa **Assign Toko (layar SPV)** dan
   **Scorecard Kreator (layar)** bila belum lengkap di UI.
3. ~~`mapping_unverified` berbunyi “…sebelum menyimpan” walau dibaca sesudah commit~~ — **SUDAH
   DIPOLES di sesi ini**: pada langkah 6 judulnya menjadi “Hasil di atas memakai pemetaan yang
   BELUM diverifikasi” + jalan keluarnya (batalkan & unggah ulang, jangan menambal manual).

---

# SESI 2026-08-13 (#7) — **RECOVERY INSIDEN** + lanjut 3 tugas: **Impor KPI Shopee → Assign Toko → Scorecard Kreator**

> Permintaan user terbaru: lanjutkan sesuai rekomendasi, file Shopee yang diberikan **hanya contoh** (jangan tergantung datanya), dan lanjut 3 task tertunda berurutan.

## 0) INSIDEN LINGKUNGAN (14:01) — **KORUPSI DISK MASIF** → SUDAH DIPULIHKAN ✅

**Kejadian:** container restart 14:01 menyebabkan banyak file berubah menjadi null-bytes (bukan bug kode). Dampak:
- `/etc/supervisor/*` rusak (supervisorctl gagal parse)
- Python venv `/root/.venv` rusak berat (banyak site-packages null) → backend tidak bisa start
- `frontend/src` & `scripts/` banyak file null
- `node_modules` & `yarn.lock` korup → yarn install gagal
- MongoDB gagal start karena metadata WiredTiger + `storage.bson` berisi null

**Pemulihan (diukur & dilakukan):**
- Restore 522 berkas tracked yang korup dari git (`git checkout -- <paths>`)
- Pulihkan supervisor config utama + hilangkan conf proxy yang korup
- Rebuild venv dari `backend/requirements.txt` (pip OK)
- MongoDB: perbaiki `WiredTiger` + buang `storage.bson` korup + `mongod --repair` **berhasil**, DB tidak hilang
- Frontend: bersihkan `yarn.lock` + reinstall `node_modules`, lalu `bash scripts/rebuild_frontend.sh`
- Verifikasi: `bash scripts/gate.sh` **22/22 HIJAU**

**Catatan pencegahan:** setelah fitur selesai, disarankan lakukan **push/backup ke GitHub** (cadangan di luar disk ephemeral) agar insiden sejenis tidak menghapus pekerjaan.

---

## 1) STATUS SAAT INI (setelah recovery)

- Backend: RUNNING, `GET /api/health` 200
- MongoDB: RUNNING, `test_database` ada
- Frontend: static bundle server RUNNING (port 3000), rebuild sukses
- Gate: `scripts/gate.sh` 22/22 HIJAU

**Yang sudah ada dari sesi-sesi sebelumnya (tetap berlaku):**
- F4 Katalog ✅
- F5 Siklus target·anggaran·omzet ✅
- F6 inti RBAC per toko + change-log endpoint ✅ (dibuktikan `test_core_f6_f7.py`)
- F7 inti konten+kreator (published_url guard, KPI, laporan performa) ✅ (dibuktikan `test_core_f6_f7.py`)

**Yang akan dikerjakan berikutnya (3 tugas user):**
1) **Impor KPI Shopee** (konten + iklan + statistik toko)
2) **Assign Toko (SPV)** (assign/unassign staf per toko + jejak)
3) **Scorecard Kreator** (target vs aktual, dipisah GMV KPI vs omzet pesanan)

---

## 2) UPDATE OBJECTIVES (tujuan yang disesuaikan)

1. **Impor KPI Shopee tanpa AI**: file Shopee (CSV/XLSX) yang punya metadata/section/blank rows tetap bisa diimpor lewat mesin impor SSOT (`marketing_import_schema` + `marketing_import_engine`) dengan **pranormalisasi deterministik**.
2. **Tidak ada dobel hitung omzet**: GMV dari KPI konten **tidak dijumlah** dengan omzet pesanan (`marketing_orders`). Ditampilkan berdampingan seperti pola F7 performance.
3. **RBAC operasional**: SPV bisa assign toko ke staf; staf langsung kehilangan akses (403) saat di-unassign.
4. **Scorecard kreator**: satu endpoint dan satu layar yang mempertemukan target kreator (`marketing_creator_targets`) + KPI konten (`marketing_content_calendar.kpi`) + omzet pesanan (`marketing_orders.creator_id`) **tanpa mencampur sumber angka**.

---

## 3) IMPLEMENTATION PLAN — Tahap demi tahap

### 3.1 F7.2 — Impor KPI Shopee (prioritas 1)

#### A. Desain skema & SourceType baru (SSOT)
Tambahkan jenis impor baru di `backend/core/marketing_import_schema.py`:

1) `shopee_shop_kpi` (group: Penjualan/KPI)
- **Input:** XLSX “Shopee shop stats” (contoh berisi banyak sheet)
- **Output:** koleksi baru `marketing_platform_kpi_daily`
- **Account scope:** required
- **Dedupe:** (`account_id`, `date`, `metric_scope`) atau bentuk field kanonik yang stabil

2) `shopee_content_kpi` (group: Konten)
- **Input:** CSV “Live 1d export”, “overview-v2”, “video-overview-v3” (struktur header ganda + blok section “Sumber Penonton”)
- **Output:** `marketing_platform_kpi_daily` (agar KPI harian tersimpan konsisten)
- **Catatan:** baris section & baris kosong harus dibuang; angka utama harian diambil dari baris utama (row data dengan `Periode Data` valid)

3) `shopee_ads_cpc` (group: Iklan)
- **Input:** CSV “Data Keseluruhan Iklan CPC” (ada metadata header 6 baris lalu tabel)
- **Output:** `marketing_ads_data` (koleksi yang sudah ada)
- **Kunci penting agar F5 terbaca:** field `date` harus bisa dipakai `_auto_ads` (`date` diawali `YYYY-MM`). Solusi:
  - simpan `date` sebagai string `YYYY-MM-DD` untuk **start date** periode (atau datetime) + pastikan query `_auto_ads` cocok
  - bila tetap `datetime`, pastikan `_auto_ads` tidak hanya `$regex` string (perlu patch minimal agar menerima datetime)

4) `content_performance` (group: Konten)
- **Input:** CSV/XLSX KPI per konten (contoh tidak diberikan, jadi dibuat generik)
- **Output:** update/insert ke `marketing_content_calendar` via **kunci `published_url`**
- **Aturan:** status `posted` wajib URL; impor harus menolak/menandai baris tanpa URL

> **Catatan SSOT:** bila menambah koleksi baru `marketing_platform_kpi_daily`, wajib:
> - daftar di `backend/core/collection_registry.py`
> - tulis kontrak ringkas di `memory/SSOT_KONTRAK_DATA_2026-08-12.md` (minimal: tujuan, field wajib, dedupe key)

#### B. Pranormalisasi file Shopee (tanpa AI)
**Masalah nyata:** file Shopee mengandung:
- metadata header (beberapa baris sebelum tabel)
- header ganda (baris 0 = judul grup kolom, baris 1 = header sebenarnya)
- blok section (contoh “Kunjungan - Sumber Penonton - …” yang bukan baris data)

**Solusi:** buat modul baru `backend/core/marketing_import_prenorm.py`:
- `prenorm_shopee_ads_cpc(rows)`: buang metadata sampai menemukan header tabel `Urutan,Nama Iklan,...`
- `prenorm_shopee_overview(rows)`: ambil hanya baris data utama (tanggal) dan buang section blocks
- `prenorm_shopee_shop_stats_xlsx(sheet_rows)`: untuk xlsx, ambil block tabel “Tanggal …” lalu jadikan baris harian

Tambahkan properti `prenorm` pada `SourceType` (atau mekanisme setara) sehingga `routes/marketing_data_import.upload()` memanggil prenorm berdasarkan `source_type`.

#### C. Implement commit handler spesifik (bila perlu)
- Reuse commit generic di `routes/marketing_data_import.py` selama dokumen output sudah sesuai.
- Untuk `content_performance`: commit harus **update existing** entry di `marketing_content_calendar` bila `published_url` sama (dedupe by URL), bukan insert duplikat.

#### D. Frontend: update wizard impor
File terkait: `frontend/src/components/erp/marketing/DataImportWizard.jsx`
- Tambahkan kartu jenis impor baru (4 SourceType) di daftar
- Untuk jenis yang account-scope required: pilih toko + tanggal/period (manual) bila dibutuhkan
- Tampilkan preview mapping + summary (valid/warn/error) seperti jenis lain
- Pastikan pesan error prenorm/mapping **menetap** (bukan hanya toast)

#### E. Bukti & test
Tambahkan core test baru:
- `test_core_f7_kpi_impor.py`:
  - upload contoh file Shopee (pakai contoh yang ada di artefak sebagai fixture, tapi test harus robust terhadap nilai)
  - pastikan prenorm membuang metadata/section
  - commit menghasilkan dokumen ke target collection
  - untuk ads: pastikan `_auto_ads` F5 membaca spend (atau patch `_auto_ads` agar kompatibel)
  - untuk content_performance: update entry by `published_url` dan KPI tersimpan + derived dihitung

Registrasikan ke `scripts/gate.sh` agar gate tetap 22/22 (atau bertambah 1 tapi tetap HIJAU).

---

### 3.2 Assign Toko (SPV) (prioritas 2)

#### A. Backend API
Tambah route baru (hindari konflik dengan `/accounts/{id}`):
- `POST /api/marketing/account-assign/assign`
- `POST /api/marketing/account-assign/unassign`
- `GET /api/marketing/account-assign/history?account_id=...`

Implementasi:
- Hanya role `owner/admin/superadmin/spv_marketing/manager_marketing` yang boleh menulis
- Update `marketing_platform_accounts.assigned_staff[]` (addToSet/pull)
- Tulis jejak ke `marketing_change_log` via `core/marketing_cycle.log_change`:
  - entity=`marketing_platform_accounts`, action=`assign_staff|unassign_staff`
  - before/after memuat daftar staf atau delta

#### B. Frontend UI
Tambahkan tab/section di `AccountManagementModule.jsx`:
- Panel “Assign Staff” per toko:
  - list staf marketing eligible
  - tombol assign/unassign
  - tampilkan assigned_staff saat ini
  - link “Riwayat perubahan”

#### C. Bukti
- Update/extend `test_core_f6_f7.py` atau test baru untuk:
  - assign staff ke toko → staff melihat toko
  - unassign → staff 403 pada cycle/orders
  - change-log memuat aksi assign/unassign

---

### 3.3 Scorecard Kreator (prioritas 3)

#### A. Backend endpoint
Tambah endpoint baru (di `routes/marketing_targets.py` atau file baru khusus laporan):
- `GET /api/marketing/targets/creator/scorecard?year=YYYY&month=MM&creator_id?=&account_id?=`

Perhitungan:
- Target: `marketing_creator_targets` (revenue_target/sessions_target/viewers_target)
- Aktual KPI konten: agregasi dari `marketing_content_calendar` (posted + kpi)
- Aktual omzet pesanan: agregasi dari `marketing_orders.creator_id` (dipisah dari GMV KPI)
- (Opsional) sesi kreator jika ada koleksi `marketing_creator_sessions`

Output:
- per kreator: target vs actual, % pencapaian
- tampilkan dua angka uang: `gmv_kpi` dan `order_revenue`

#### B. Frontend UI
Tempat paling aman (satu pintu, tidak bikin modul kembar):
- Tambahkan tab “Scorecard Kreator” di `ContentCalendarModule.jsx` (sejajar dengan “Performa Konten”)
- Reuse komponen table+cards pattern

#### C. Bukti
- Core test memverifikasi:
  - endpoint mengembalikan target & actual
  - `gmv_kpi` tidak dijumlah dengan `order_revenue`
  - catatan “dua sumber angka” muncul seperti F7 performance

---

## 4) CHANGELOG DOKUMEN / PLAN UPDATE

Plan lama menyatakan F6/F7 masih sebagian; **audit terbaru** setelah recovery menunjukkan:
- F6 inti sudah selesai (RBAC + change-log endpoint + test) ✅
- F7 inti sudah selesai (published_url guard + KPI + performance UI) ✅
- Sisa F7 berikutnya adalah **impor KPI konten** dan **scorecard** (yang menjadi fokus plan update ini)

---

## 5) Gate wajib hijau setiap akhir tahap
```bash
cd /app && bash scripts/gate.sh
cd /app && python3 scripts/gate_marketing_ssot.py
cd /app && python3 scripts/verify_marketing_scope.py
cd /app && python3 scripts/verify_marketing_cycle.py
# setelah menambah test baru:
cd /app && python3 test_core_f7_kpi_impor.py
```

## 6) Catatan lingkungan (tetap)
- Frontend = **static bundle**, setiap perubahan `frontend/src` wajib:
  - `bash /app/scripts/rebuild_frontend.sh`
- Kredensial marketing:
  - `marketing@dewiaditya.id` / `Dewi@123` (manager_marketing)
  - `staffmkt@dewiaditya.id` / `Dewi@123` (staff_marketing)

---

# SESI 2026-08-13 (#6) — F4 **DIVERIFIKASI** + F5 **SIKLUS TARGET·ANGGARAN·OMZET SELESAI** ✅

> (Bagian ini dipertahankan dari plan sebelumnya; tidak diubah kecuali status recovery di atas.)

## 1) VERIFIKASI TITIK BERHENTI (F4) — 6/6 bukti TERPENUHI
| Bukti F4 | Hasil |
|---|---|
| 1–4 status turunan · pagar bukti tayang · foto master · kontrak baris | `test_core_f4_katalog.py` **36/36 PASS** |
| 5 layar `marketing-catalog` ≥19 kolom + pengalih Tabel/Kartu + bertahan | **21 kolom**, toggle OK, `catalog_items_view` bertahan |
| 5b deep-link `toko-products` ⇒ diarahkan | mendarat di **Manajemen Katalog Produk**, sidebar menyorot benar |
| 6 `stock_summary.by_status` = total item | PASS |

## 2) FASE F5 SELESAI — satu layar siklus, realisasi otomatis, kunci periode, peringatan
| # | Isi | Berkas |
|---|---|---|
| F5.1 | `core/marketing_cycle.py` SSOT angka siklus + endpoint cycle | `core/marketing_cycle.py`, `routes/marketing_budget.py` |
| F5.2 | Realisasi anggaran otomatis + bukti | idem |
| F5.3 | Kunci periode + 423 + commit impor ditolak sebelum simpan | idem |
| F5.4 | Flags/peringatan dari satu fungsi | `core/marketing_cycle.py` |
| F5.5 | Layar CycleView + dialog + bukti | FE marketing |

**Bukti:** `bash scripts/gate.sh` 22/22 HIJAU; `test_core_f5_siklus.py` 58/58 PASS.

---

# plan.md — RENCANA EKSEKUSI (aktif)

> Dokumen sumber tetap sama:
> 1) `memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`
> 2) `memory/SSOT_KONTRAK_DATA_2026-08-12.md`
> 3) `memory/VERIFIKASI_2026-08-12.md`
> 4) `memory/REGISTRY_KOLEKSI_MARKETING.md`

## Status fase (ringkas, diperbarui)
- F0 ✅
- F1 ✅
- F2 ✅
- F3 🟡 (monitoring UI selesai; sisa impor Ekspor B/C masih menunggu BD-1)
- F4 ✅
- F5 ✅
- F6 ✅ **(inti RBAC per toko + jejak sudah terbukti)**
- F7 ✅ **(inti konten+kreator sudah terbukti)**; berikutnya: **impor KPI konten + scorecard**
- F8 🟡 (laporan mingguan selesai; sisa impor/form KPI menunggu BD-3)
- F9 ⏳ (blocked BD-2)
- F10 ⏳
