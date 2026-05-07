# Google Drive Quick Setup

## 1) Buat OAuth Client ID (Web)

1. Buka Google Cloud Console.
2. Aktifkan Google Drive API.
3. Buat OAuth Client ID tipe Web Application.
4. Tambahkan Authorized JavaScript Origin:
   - `https://<domain-app-vercel-kamu>`
   - contoh: `https://xdownloader.vercel.app`

## 2) (Opsional) Siapkan Folder Tujuan Drive

- Buka folder di Google Drive.
- Ambil `folderId` dari URL folder.
  - Contoh URL: `https://drive.google.com/drive/folders/<FOLDER_ID>`

## 3) Isi Environment Variable di Vercel

Di Project Settings -> Environment Variables:

- `GOOGLE_CLIENT_ID` = OAuth Client ID kamu
- `GOOGLE_DRIVE_FOLDER_ID` = folder id (opsional)

## 4) Deploy Ulang

- Redeploy project setelah env diisi.

## 5) Setup dari UI aplikasi (sekali saja)

1. Buka halaman app.
2. Cek panel **Google Drive Setup Cepat**.
3. Pastikan Client ID dan Folder ID sudah benar.
4. Klik **Simpan Setting**.
5. Klik **Connect Google** lalu beri izin.
6. Pilih file dari perangkat.
7. Klik **Upload ke Drive**.

## Catatan Penting

- Upload ke Drive dilakukan langsung dari browser user ke Google API.
- Ini lebih ringan untuk Vercel dibanding memproses file besar di function.
- Untuk file besar, koneksi user tetap jadi faktor utama.
