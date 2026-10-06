# Windows Sağlık Kontrolü

Windows bilgisayarın temel disk, RAM ve aygıt sürücüsü durumunu raporlayan,
Python standart kütüphanesini kullanan küçük bir konsol uygulamasıdır.

## Çalıştırma

PowerShell'de proje klasörüne geçip:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe .\main.py
```

Yönetici yetkisi normalde gerekmez. Windows PowerShell ve CIM sorguları
kullanılır. Uygulama sistemde değişiklik yapmaz veya onarım çalıştırmaz.

## Kontroller ve kapsam

- RAM kullanımını ve Windows'un bildirdiği takılı bellek miktarını gösterir.
- Yerel disk bölümlerindeki boş alanı kontrol eder.
- Destekleniyorsa `Get-PhysicalDisk` ile fiziksel disk sağlık durumunu,
  desteklenmiyorsa Windows'un temel disk durumunu gösterir.
- Windows tarafından hata koduyla işaretlenen tak-çalıştır aygıtlarını listeler.

Fiziksel disk sağlık bilgisi donanım, sürücü ve Windows depolama sağlayıcısına
bağlıdır; bu rapor SMART testi veya kapsamlı bir sürücü envanteri değildir.

## Testler

```powershell
.\.venv\Scripts\python.exe -m unittest discover
```
