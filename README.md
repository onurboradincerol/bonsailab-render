# BonsaiLAB V27 — Render

40 tür, 20 substrat ve üç dane grubu için yıl boyu tek reçete tasarımı. Hesaplar Python sunucusunda yapılır. Mevcut V27 seçim motoru ve kaynak verileri değişmeden kopyalanmıştır. Kaynak tahminleri gerçek ürün partisi veya biyolojik optimum ölçümü değildir.

## Çalıştırma

Python 3.14.2, `pip install -r requirements.txt`. Üretim başlangıcı render.yaml içinde. Yerel kontrol: `python app.py`. `/healthz` sağlık ve veri kimliğini döndürür. `/api/config` tam veri tabanı, `/api/calculate` JSON hesap isteğidir.

Render kurulumu açıkça `free` planını kullanır. Ücretsiz plan kullanılmadığında uykuya geçebilir; ilk ziyaret yeniden başlatmayı bekler. Kalıcı disk veya veri tabanı gerekmez. Seçimler tarayıcıda tutulur; hesap girdisi yalnız sonuç üretmek için sunucuya gönderilir.

## Kaynak yönetimi ve yük sınırı

Bir anda bir hesap çalışır. Diğer istekler 429 ve Retry-After yanıtıyla tekrar denenir. Aynı girdinin sonucu en fazla 15 dakika, en fazla 64 kayıt olacak şekilde bellek içinde tutulur; yeniden başlatmada silinir. Girdiler dosyaya kaydedilmez. JSON gövdesi 150 KB ile sınırlıdır; arama oranları ve aday sayısı V27 sınırlarını korur.

Tarayıcı için Python/WebAssembly paketi gerekmez. Aynı kökenli JSON istekleri kabul edilir. Güncelleme sonrasında yapılandırma/rapor kimliği değişmeyen hesap motoruyla karşılaştırılır.
