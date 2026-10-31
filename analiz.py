import csv
import math

# ==============================================================================
# ANALİZ VE RAPORLAMA FONKSİYONU
# ==============================================================================
def analiz_et(telemetri_dosya="telemetri.csv", hedefler_dosya="hedefler.csv", rapor_dosya="rapor.txt"):
    """
    NE İŞE YARAR?: 'gorev.py' tarafından oluşturulan 'telemetri.csv' ve 'hedefler.csv'
    dosyalarını okuyarak uçuş performansını hesaplar; sonuçları hem ekrana yazar
    hem de 'rapor.txt' dosyasına kaydeder.
    """
    zamanlar, x_list, y_list, irtifalar, modlar = [], [], [], [], []
    
    # 1. TELEMETRİ VERİSİNİ OKUMA
    # 'telemetri.csv' dosyasını satır satır okuyup listelere ayırıyoruz.
    try:
        with open(telemetri_dosya, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f) # Başlık satırına göre sütun isimleriyle okuma yapar
            for row in reader:
                zamanlar.append(float(row["zaman"]))
                x_list.append(float(row["x"]))
                y_list.append(float(row["y"]))
                irtifalar.append(float(row["irtifa"]))
                modlar.append(row["mod"])
    except FileNotFoundError:
        print(f"-> HATA: '{telemetri_dosya}' bulunamadı! Lütfen önce uçuşu ('gorev.py') gerçekleştirin.")
        return

    # 2. HEDEF NOKTALARI OKUMA
    # 'analiz.py' hedefleri elle yazmaz, 'gorev.py'nin oluşturduğu 'hedefler.csv'den okur.
    hedefler = []
    try:
        with open(hedefler_dosya, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                hedefler.append((float(row["x"]), float(row["y"])))
    except FileNotFoundError:
        print(f"-> HATA: '{hedefler_dosya}' bulunamadı!")
        return

    # ==============================================================================
    # 3. PERFORMANS VE MATEMATİK HESAPLAMALARI
    # ==============================================================================
    
    # A) Toplam Uçuş Süresi: Son zaman kaydı ile ilk zaman kaydı arasındaki fark
    toplam_sure = zamanlar[-1] - zamanlar[0] if zamanlar else 0.0
    
    # B) İrtifa Hesaplamaları: Maksimum ve ortalama irtifa
    max_irtifa = max(irtifalar) if irtifalar else 0.0
    ort_irtifa = sum(irtifalar) / len(irtifalar) if irtifalar else 0.0
    
    # C) Kat Edilen Toplam Mesafe: Ardışık telemetri (X, Y) noktaları arası Öklid mesafelerinin toplamı
    # Formül: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)
    toplam_mesafe = 0.0
    for i in range(1, len(x_list)):
        dx = x_list[i] - x_list[i-1]
        dy = y_list[i] - y_list[i-1]
        toplam_mesafe += math.sqrt(dx**2 + dy**2)
        
    # D) Hedef Noktalara Yaklaşma Mesafeleri:
    # Drone'un tüm uçuş boyunca her bir hedef noktaya en çok kaç metre yaklaştığını buluyoruz.
    en_yakin_mesafeler = []
    basarili_hedef_sayisi = 0
    
    for hx, hy in hedefler:
        min_m = float('inf') # Başlangıçta sonsuz büyük bir değer veriyoruz
        for ux, uy in zip(x_list, y_list):
            # Anlık uçuş konumu ile hedef nokta arasındaki mesafeyi hesaplıyoruz
            m = math.sqrt((hx - ux)**2 + (hy - uy)**2)
            if m < min_m:
                min_m = m # Bulunan en küçük mesafeyi güncelliyoruz
                
        en_yakin_mesafeler.append(min_m)
        # Eğer 2 metre veya daha yakınına geldiyse hedef başarıyla ziyaret edilmiş sayılır
        if min_m <= 2.0:
            basarili_hedef_sayisi += 1

    # ==============================================================================
    # 4. RAPOR METNİ OLUŞTURMA VE KAYDETME
    # ==============================================================================
    rapor_metni = []
    rapor_metni.append("==================================================")
    rapor_metni.append("          OTONOM UÇUŞ ANALİZ RAPORU               ")
    rapor_metni.append("==================================================\n")
    rapor_metni.append(f"1. Toplam Uçuş Süresi      : {toplam_sure:.2f} saniye")
    rapor_metni.append(f"2. Maksimum İrtifa         : {max_irtifa:.2f} metre")
    rapor_metni.append(f"3. Ortalama İrtifa         : {ort_irtifa:.2f} metre")
    rapor_metni.append(f"4. Kat Edilen Toplam Mesafe: {toplam_mesafe:.2f} metre\n")
    
    rapor_metni.append("--- HEDEFLERE EN YAKINLAŞILAN MESAFELER ---")
    for idx, dist in enumerate(en_yakin_mesafeler, 1):
        hx, hy = hedefler[idx-1]
        rapor_metni.append(f" - Hedef {idx} (X:{hx:.1f}, Y:{hy:.1f}) -> En Yakın Mesafe: {dist:.2f}m")
        
    rapor_metni.append(f"\n5. Başarılı Hedef Oranı (<=2m): {basarili_hedef_sayisi}/{len(hedefler)}")
    rapor_metni.append("==================================================")

    tam_rapor = "\n".join(rapor_metni)

    # A) Ekrana (Konsola) Yazdırıyoruz
    print(tam_rapor)

    # B) 'rapor.txt' Dosyasına Kaydediyoruz
    with open(rapor_dosya, mode='w', encoding='utf-8') as f:
        f.write(tam_rapor)
        
    print(f"\n[BİLGİ] Analiz raporu başarıyla '{rapor_dosya}' dosyasına kaydedildi.")


if __name__ == "__main__":
    analiz_et()