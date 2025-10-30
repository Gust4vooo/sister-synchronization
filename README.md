# Tugas 2 - Sinkronisasi Sistem Terdistribusi

Proyek ini adalah implementasi sistem terdistribusi yang mendemonstrasikan beberapa konsep sinkronisasi dan komunikasi antar-node.

- **Nama:** Gusti Muhammad Risandha
- **NIM:** 11221028
- **Link Video Demonstrasi:** [https://youtu.be/C_sFpbHBIR4](https://youtu.be/C_sFpbHBIR4)

---

## Deskripsi Proyek

Sistem ini dibangun di atas arsitektur berbasis *microservices* di mana beberapa node dengan peran berbeda bekerja sama untuk mencapai tujuan tertentu. Proyek ini mengimplementasikan:
- **Distributed Lock Manager**: Node yang bertanggung jawab untuk mengelola kunci (lock) secara terdistribusi untuk mencegah *race condition* pada sumber daya yang sama.
- **Distributed Queue**: Sistem antrian terdistribusi di mana setiap node dapat menambahkan (enqueue) dan mengambil (dequeue) pesan dari antrian.
- **Distributed Cache**: Cache terdistribusi yang konsisten di antara beberapa node untuk mempercepat akses data.

Komunikasi antar-node dilakukan secara asinkron menggunakan `aiohttp` dan Redis digunakan sebagai *message broker* dan penyimpanan data.

## Arsitektur

Sistem ini terdiri dari beberapa layanan yang didefinisikan dalam `docker-compose.yml`:

- **Redis**: Sebagai pusat komunikasi dan penyimpanan state.
- **Lock Manager Nodes** (`lock_manager_1`, `lock_manager_2`, `lock_manager_3`): Tiga node yang membentuk cluster untuk manajemen kunci.
- **Queue Nodes** (`queue_node_1`, `queue_node_2`, `queue_node_3`): Tiga node yang mengelola sistem antrian terdistribusi.
- **Cache Nodes** (`cache_node_1`, `cache_node_2`, `cache_node_3`): Tiga node yang menyediakan caching terdistribusi.

Setiap node diekspos pada port yang berbeda (mulai dari 8001 hingga 8009) dan saling mengenali satu sama lain melalui konfigurasi `PEERS`.

## Teknologi yang Digunakan

- **Bahasa Pemrograman**: Python 3.10+
- **Orkestrasi**: Docker & Docker Compose
- **Komunikasi & Caching**: Redis
- **Framework Web/API**: `aiohttp`
- **Dokumentasi API**: `aiohttp-swagger3`
- **Lainnya**: `uhashring` untuk *consistent hashing*, `aiofiles` untuk operasi file asinkron.

## Cara Menjalankan Proyek

### 1. Persiapan

- Pastikan Docker dan Docker Compose sudah terinstal di sistem Anda.
- *Clone* repositori ini.
- Buat file `.env` dari contoh yang ada.

  ```bash
  cp .env.example .env
  ```
- Sesuaikan isi file `.env` jika diperlukan (misalnya, jika `HOST` atau `REDIS_HOST` bukan `localhost`).

### 2. Menjalankan dengan Docker Compose

Untuk membangun dan menjalankan semua layanan, gunakan perintah berikut dari direktori utama proyek:

```bash
docker-compose up --build
```

Perintah ini akan membuat *image* untuk semua node, menjalankan semua kontainer, dan menghubungkannya dalam satu jaringan.

### 3. Mengakses API

Setelah semua layanan berjalan, Anda dapat mengakses API dari masing-masing node. Dokumentasi API interaktif (Swagger) tersedia di endpoint `/api/doc` untuk setiap node.

Contoh:
- **Lock Manager 1 API**: `http://localhost:8001/api/doc`
- **Queue Node 1 API**: `http://localhost:8004/api/doc`
- **Cache Node 1 API**: `http://localhost:8007/api/doc`

## Menjalankan Pengujian

Untuk menjalankan pengujian (misalnya *load testing* dengan Locust), Anda dapat menjalankan skrip yang ada di direktori `benchmarks/`. Pastikan untuk menginstal dependensi terlebih dahulu.

```bash
pip install -r requirements.txt
locust -f benchmarks/load_test_scenarios.py --host=http://localhost:8004
```
