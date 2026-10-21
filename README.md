# BonsaiLAB V32 — Render

40 tür, 20 substrat ve üç dane grubu için yıl boyu tek reçete tasarımı. Hesaplar Python sunucusunda yapılır. V31, veri eksikliği ve kaynak/numune uyumunun seçim puanına etkisini kaldırır; 20 malzemenin 140 sayısal referans alanını açık yöntemlerle tamamlar. Kaynaklı numuneler, aktarım ve tahminler ayrı etiketlenir. Kaynak tahminleri gerçek ürün partisi veya biyolojik optimum ölçümü değildir.

## Çalıştırma

Python 3.14.2, `pip install -r requirements.txt`. Üretim başlangıcı render.yaml içinde. Yerel kontrol: `python app.py`. `/healthz` sağlık ve veri kimliğini döndürür. `/api/config` tam veri tabanı, `/api/calculate` JSON hesap isteğidir.

Render kurulumu açıkça `free` planını kullanır. Ücretsiz plan kullanılmadığında uykuya geçebilir; ilk ziyaret yeniden başlatmayı bekler. Kalıcı disk veya veri tabanı gerekmez. Seçimler tarayıcıda tutulur; hesap girdisi yalnız sonuç üretmek için sunucuya gönderilir.

## V31 seçim ve sayısal tamamlama

Kaynak sınıfı, numune örtüşmesi veya eksik ölçüm seçim puanını ve koşulluluk sırasını değiştirmez. Temin güçlüğü ana öneride ceza değildir; yalnız kolay temin alternatifinde stok filtresidir. Gerçek stok dane uygunluğu, malzeme oran sınırları, su/hava eşikleri ve türün pH tercih bandı korunur.

Kaynak eğrisi olmayan malzemelerde CC ve AWC ile üstel tutma eğrisi tahmin edilir. Kaynak kap bilinmiyorsa referans 12 cm varsayılır; bu bir ölçüm değildir. İnterpolasyon yalnız uygun ölçüm noktaları arasında yapılır. Her malzemenin tamamlanmış alanları ve kaynakları data_completion içinde bulunur.

## Kaynak yönetimi ve yük sınırı

Ana sonuç kartları karışım oranlarını, miktarları, tahmini su tutma, hava boşluğu, pH, CEC, kullanılabilir su, kuru yoğunluk değerlerini ve dane önerisini gösterir. Numune payı ve aktarım endeksi arayüzden kaldırılmıştır. Mevsim hedefleri, ayrıntılı hesap tabloları ve yöntem açıklamaları kapalı ayrıntı bölümlerindedir. Önemli yetiştirme uyarıları görünür tutulur; motor sonuçları ve tam JSON raporu korunur.

Hesap yalnız “Karışımı hesapla” düğmesiyle başlar. Sayfa açılışı ve seçim değişiklikleri hesap isteği göndermez. Değişiklikler kaydedilir; önceki sonuç ve ona ait rapor ekranda kalır. Küçük eski sonuç uyarısı gösterilir. Hesap beklerken veya hata döndüğünde önceki sonuç korunur. Hesap sürerken düğme tekrar istek göndermez. Sunucu meşgulse otomatik tekrar yapılmaz; kullanıcı düğmeyle yeniden dener.

Bir anda bir hesap çalışır. Diğer istekler 429 ve Retry-After yanıtı alır. Aynı girdinin sonucu en fazla 15 dakika, en fazla 64 kayıt olacak şekilde bellek içinde tutulur; yeniden başlatmada silinir. Girdiler dosyaya kaydedilmez. JSON gövdesi 150 KB ile sınırlıdır; %5 oran adımı ve kullanıcının 1–5 bileşen üst sınırı uygulanır.

Tarayıcı için Python/WebAssembly paketi gerekmez. Aynı kökenli JSON istekleri kabul edilir. Güncelleme sonrasında yapılandırma/rapor kimliği değişmeyen hesap motoruyla karşılaştırılır.

V31: %5 oran adımıyla 1–5 bileşenli tüm uygun reçeteler NumPy gruplarıyla taranır. Bileşen sayısı puana eklenmez; küçük reçete puan avantajı almaz. Fiziksel model ve pH seçimi korunur.

Kullanıcı En fazla bileşen seçeneğiyle 1–5 üst sınırı belirler; varsayılan 5. API max_components alanını doğrular, rapor ve istek kimliğine ekler. Alanı göndermeyen eski istemciler 5 kullanır.

## V31 son denetim

Malzeme adına bağlı tercih, sabit zeolit/diatomit cezası ve referans reçeteye yakınlık puanı sıfırlandı. Ana mineral iskelet malzemelerinde isim bazlı yüzde 100 altı tavanlar kaldırıldı. Asidik malzeme adı minimumu kaldırıldı; tahmini pH bandı önceliği korundu. Leonardit, organik/katkı ve iskelet tasarım sınırları açık model kapsamı olarak korunur. Bu sınırlar evrensel biyolojik eşikler değildir.

CEC 5 cmol(+)/kg altında 0.5*(max(0,5-CEC)/5)^2 kıyas puanı kullanılır; 5 üzeri ilave kazanç sağlamaz. UF/IFAS süs yapraklı kap bitkileri aralığının alt ucu karşılaştırma önkabulü olarak aktarılmıştır, bonsai tür hedefi değildir. Yoğunluk ve kullanılabilir su hesaplanır; doğrulanmış tür hedefi olmadan optimize edildikleri iddia edilmez. Puan bileşenleri selection_explanation içinde raporlanır.

pH raporunun bütün alanları aynı göreli tamponlama tahminini kullanır. CEC kütle ağırlıklıdır; cmol(+)/L ve toplam değişim kapasitesi ayrıca hesaplanır. Kuru kütle, hacim, PWP/AWC ve kaynak eğrisi sınırları otomatik testlerle denetlenir.

## V31 duyarlılık revizyonu

Su/hava hedef uzaklığı tolerans içinde de sürekli kareseldir. Başlangıç, organik hacim payıyla gözenek dağılımı ve yerleşme streslerinin en büyük su/hava uzaklığı kullanılır. pH aralığı tam pozitif ağırlık kutu uçlarıyla hesaplanır; tür bandını aşan normalize karesel kısım seçim puanına eklenir. Nokta pH bandı önceliği korunur. Kaynak eksikliği cezası yoktur.

Stres katsayıları rules.robust_selection içinde görünür: +12 CC organik gözenek sınaması; ayrı yerleşmede organik pay × (+7 CC, -8 TP), bütün reçetelerde ortak -3 TP. Bunlar literatürden aktarılan kaba büyüklükler ve açık tasarım kabulleridir; ürünün yıllık parçalanma oranı değildir. Mineral parçalanması ölçüldü veya sıfırdır denmez. Üç senaryoda su + hava = TP korunur.

Eşitlikte az bileşen veya alfabetik ad avantajı kaldırılmıştır. Model sırası 9 basamakta eşitse sabit malzeme kimliği/oran SHA256 özeti yalnız tekrarlanabilir gösterim için kullanılır; eşit aday sayısı raporlanır. Daha çok bileşen de zorunlu tutulmaz. Ana kart pH aralığını ve yapısal stres su/hava aralığını gösterir. Ayrıntılarda puan bileşenleri ve üç senaryo ayrı izlenebilir.

## V31.1 arayüz

Hesap motoru ve veri tabanı V31 olarak korunur. Seçimler değişince sonuç silinmez; tür/hacim etiketi, Seçimler değişti uyarısı ve Tekrar hesapla düğmesi görünür. Aynı seçimlere geri dönüldüğünde uyarı kalkar. Geç dönen veya iptal edilen hesap eski sonucu değiştiremez. İndirilen JSON her zaman gösterilen hesabın istek görüntüsüdür; export_context güncel seçimlerden farklı olup olmadığını belirtir. Ana ekrandaki tekrar eden açıklamalar sadeleştirilmiştir; yöntem, kaynaklar ve önemli uygunluk uyarıları korunur.

## V32 zorunlu malzeme seçimi

Her stok satırında Mutlaka olsun seçeneği bulunur. API inventory[].required boolean alanını doğrular; eksik alan eski istemciler için false kabul edilir. Zorunlu malzemeler bütün adaylarda pozitif payla bulunur. Özel yüzde 1 hedefi yoktur; mevcut yüzde 5 oran adımı ve malzeme tavanları korunur. Oranları motor seçer. Zorunlu sayı kullanıcı bileşen üst sınırını aşarsa açıklayıcı girdi hatası döner. Leonardit gibi otomatik hacim reçetesi dışında kalan malzemeler zorunlu seçilemez.

Zorunlu seçim kolay temin filtresiyle çakışırsa ana öneri hesaplanır, kolay temin alternatifi açık gerekçeyle oluşturulmaz. Hiçbir zorunlu malzeme sessizce çıkarılmaz. Seçim kayda ve JSON raporuna dahil edilir. Girdi değişince önceki sonuç korunur; yeni zorunluluk yalnız Tekrar hesapla ile uygulanır. Rapor kimliği zorunlu alanları içerir (request_identity_version 3).
