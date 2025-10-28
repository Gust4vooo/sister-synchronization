# Deployment Guide and Troubleshooting

Dokumen ini berisi panduan langkah demi langkah untuk menjalankan dan memverifikasi setiap komponen dari Sistem Sinkronisasi Terdistribusi ini menggunakan Docker.

---

## Prasyarat 

Sebelum memulai, pastikan perangkat Anda telah terinstal perangkat lunak berikut:
* **Git** untuk mengkloning repositori.
* **Docker Desktop** (atau Docker Engine & Docker Compose di Linux) yang sedang dalam keadaan berjalan (*running*).

---

## Langkah-langkah Deployment 

Proses deployment dibagi menjadi dua tahap utama: mendapatkan kode dan menjalankan sistem yang diinginkan melalui Docker Compose.

### 1. Kloning Repositori

Buka terminal Anda dan jalankan perintah berikut untuk mengunduh kode proyek:
```bash
git clone <URL_REPOSITORI_ANDA>
cd distributed-sync-system
```

### 2. Menjalankan Sistem dengan Docker Compose

File `docker-compose.yml` di direktori utama proyek ini dirancang untuk menjalankan salah satu dari tiga sistem terdistribusi (Lock Manager, Queue System, atau Cache System) secara terpisah. Anda hanya perlu mengaktifkan (un-comment) bagian yang relevan untuk sistem yang ingin Anda jalankan.

**Penting:** Sebelum menjalankan satu sistem, pastikan layanan dari sistem lain sudah dinaktifkan (dikomentari dengan `#`) di dalam file `docker-compose.yml`.

#### Menjalankan Klaster Distributed Lock Manager (Bagian A)

1.  **Konfigurasi**: Buka `docker-compose.yml` dan pastikan hanya layanan `redis`, `lock-manager-1`, `lock-manager-2`, dan `lock-manager-3` yang **aktif** (tidak diawali dengan `#`).
2.  **Jalankan**: Dari direktori utama proyek, jalankan perintah:
    ```bash
    docker-compose up --build
    ```
    Perintah ini akan membangun image Docker dan memulai keempat kontainer. Anda akan melihat log dari ketiga node, dan setelah beberapa detik, salah satu node akan terpilih sebagai **Leader**.

#### Menjalankan Klaster Distributed Queue System (Bagian B)

1.  **Konfigurasi**: Buka `docker-compose.yml`, nonaktifkan layanan Lock Manager, dan pastikan hanya layanan `queue-node-1`, `queue-node-2`, dan `queue-node-3` yang **aktif**.
2.  **Jalankan**: Dari direktori utama proyek, jalankan perintah:
    ```bash
    docker-compose up --build
    ```
    Ini akan memulai tiga node antrian yang masing-masing mendengarkan di port 9001, 9002, dan 9003.

#### Menjalankan Klaster Distributed Cache Coherence (Bagian C)

1.  **Konfigurasi**: Buka `docker-compose.yml`, nonaktifkan layanan lain, dan pastikan hanya layanan `redis`, `cache-node-1`, `cache-node-2`, dan `cache-node-3` yang **aktif**.
2.  **Jalankan**: Dari direktori utama proyek, jalankan perintah:
    ```bash
    docker-compose up --build
    ```
    Ini akan memulai tiga node cache yang terhubung ke satu database Redis.

---

## Verifikasi Sistem 

Setelah sistem berjalan, buka **terminal baru** untuk mengirim permintaan `curl` dan memverifikasi fungsionalitasnya.

* **Untuk Lock Manager**:
    1.  Cari tahu siapa Leader (misalnya, `lock-manager-2` di port 8002) dari log `docker-compose`.
    2.  Kirim permintaan `ACQUIRE`:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{"action": "ACQUIRE_EXCLUSIVE", "lock_name": "test-resource", "client_id": "curl-test"}' http://localhost:8002/lock
        ```

* **Untuk Queue System**:
    1.  Kirim pesan (`produce`) ke salah satu node:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{"key": "test-key", "message": "hello docker"}' http://localhost:9001/produce
        ```
    2.  Ambil pesan (`consume`) dari node yang menerimanya (lihat log `docker-compose`):
        ```bash
        curl http://localhost:900X/consume
        ```

* **Untuk Cache System**:
    1.  Lakukan `write` melalui `cache-node-1`:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{"key": "mykey", "value": "myvalue"}' http://localhost:10001/write
        ```
    2.  Baca dari `cache-node-2` untuk melihat `Cache MISS` (karena diinvalidaasi):
        ```bash
        curl http://localhost:10002/read/mykey
        ```

---

## Panduan Troubleshooting 

Berikut adalah beberapa masalah umum yang mungkin terjadi dan cara mengatasinya.

* **Masalah:** Error `port is already allocated` atau `The container name ... is already in use`.
    * **Penyebab:** Ada kontainer lama dari eksekusi sebelumnya yang masih berjalan atau belum terhapus.
    * **Solusi:** Jalankan perintah `docker-compose down` untuk menghentikan dan menghapus semua kontainer yang terkait dengan proyek ini. Kemudian, coba jalankan `docker-compose up` lagi.

* **Masalah:** Error `Cannot connect to the Docker daemon`.
    * **Penyebab:** Docker Desktop tidak berjalan.
    * **Solusi:** Buka aplikasi Docker Desktop dan tunggu hingga statusnya berubah menjadi "running" (biasanya ditandai dengan ikon paus yang stabil).

* **Masalah:** Error `Connection refused` saat menjalankan `curl` atau di log node.
    * **Penyebab:** Anda mungkin menargetkan port yang salah, atau layanan yang relevan tidak diaktifkan di `docker-compose.yml`.
    * **Solusi:** Pastikan Anda telah mengaktifkan layanan yang benar di `docker-compose.yml` dan menjalankan ulang. Untuk Lock Manager, pastikan Anda mengirim `curl` ke port **Leader** yang sebenarnya.

* **Masalah:** Perubahan pada kode Python tidak terlihat saat menjalankan `docker-compose up`.
    * **Penyebab:** Docker menggunakan *cache* dari *build* sebelumnya untuk mempercepat proses.
    * **Solusi:** Selalu gunakan flag `--build` saat Anda melakukan perubahan pada kode sumber: `docker-compose up --build`. Ini akan memaksa Docker untuk membangun ulang *image* dengan kode terbaru.