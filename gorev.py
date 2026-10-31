import time
import csv
import threading
from kuasar_lib import *

# ==============================================================================
# 1. AYARLAR BÖLÜMÜ (Tüm Parametreler Kodun Başında Toplanmıştır)
# ==============================================================================
# Neden En Başta?: Değerleri kodun içine gömmemek (hardcoding yapmamak) ve 
# tek bir yerden kolayca değiştirebilmek için parametreleri buraya topluyoruz.
BAGLANTI_ADRESI = "udp:127.0.0.1:14552" # SITL simülasyon adresi ve portu
HEDEF_IRTIFA    = 10.0                 # Drone'un çıkacağı hedef irtifa (Metre)
TOLERANS        = 2.0                  # Hedef noktaya ne kadar yaklaşıldığında varıldı sayılacağı (Metre)
KENAR_UZUNLUGU  = 20.0                 # Kare rotasının kenar uzunluğu (Metre)
LOG_ARALIGI     = 1.0                  # Telemetri verisinin CSV'ye kaç saniyede bir yazılacağı (Saniye)

# Küresel Bayrak (Flag): Telemetri kaydı yapan arka plan döngüsünü durdurmak için kullanılır.
ucus_devam_ediyor = True


# ==============================================================================
# 2. TELEMETRİ KAYIT FONKSİYONU (Arka Planda Saniyede Bir CSV'ye Yazma)
# ==============================================================================
def telemetri_kaydet(master, dosya_adi="telemetri.csv"):
    """
    NE İŞE YARAR?: Uçuş boyunca dronun anlık zaman, konum (X,Y), irtifa ve mod 
    bilgilerini 'telemetri.csv' dosyasına saniyede bir yazar.
    """
    global ucus_devam_ediyor
    baslangic_zamani = time.time()
    
    # 'w' modunda açarak dosyayı sıfırdan oluşturuyoruz ve başlık satırını ekliyoruz
    with open(dosya_adi, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["zaman", "x", "y", "irtifa", "mod"]) # CSV Kolon İsimleri
        
        while ucus_devam_ediyor:
            # Geçen süreyi saniye cinsinden hesaplıyoruz
            gecen_sure = round(time.time() - baslangic_zamani, 2)
            
            # Dronun anlık konumunu okuyoruz
            msg_pos = master.recv_match(type='LOCAL_POSITION_NED', blocking=False)
            
            x, y, irtifa = 0.0, 0.0, 0.0
            mevcut_mod = master.flightmode if master.flightmode else "UNKNOWN"
            
            if msg_pos:
                x = round(msg_pos.x, 2)
                y = round(msg_pos.y, 2)
                irtifa = round(-msg_pos.z, 2) # NED sisteminde Z eksi olduğu için - ile çarparak pozitif yapıyoruz
                
            # Veriyi CSV dosyasına yeni bir satır olarak yazıyoruz
            writer.writerow([gecen_sure, x, y, irtifa, mevcut_mod])
            f.flush() # Verinin anında dosyaya yazılmasını sağlar, tamponda bekletmez
            
            time.sleep(LOG_ARALIGI)


# ==============================================================================
# 3. ANA UÇUŞ AKIŞI
# ==============================================================================
if __name__ == "__main__":
    # 1. BAĞLANTI KURMA
    # 'kuasar_lib.py' içindeki 'net_connection' fonksiyonunu çağırıyoruz.
    master = net_connection(baglanti_adresi=BAGLANTI_ADRESI, timeout=10)
    if not master:
        print("Sistem bağlantısı başarısız olduğu için program sonlandırılıyor.")
        exit()

    # 2. TELEMETRİ KAYDINI ARKA PLANDA BAŞLATMA
    # 'threading' kullanarak telemetri kaydının uçuş kodunu aksatmadan arkada paralel çalışmasını sağlıyoruz.
    telemetri_thread = threading.Thread(target=telemetri_kaydet, args=(master, "telemetri.csv"))
    telemetri_thread.daemon = True # Ana program kapanınca thread de otomatik kapansın
    telemetri_thread.start()

    try:
        # 3. MODU GUIDED YAPMA
        if set_mode(master, hedef_mod="GUIDED", timeout=20):
            # 4. MOTORLARI ARM ETME
            if arm_drone(master, timeout=20):
                # 5. OTONOM KALKIŞ YAPMA
                if takeoff(master, hedef_irtifa=HEDEF_IRTIFA, timeout=30):
                    
                    # Kalkış sonrası anlık başlangıç konumunu (x0, y0) okuyoruz
                    pos_msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=5)
                    x0 = pos_msg.x if pos_msg else 0.0
                    y0 = pos_msg.y if pos_msg else 0.0
                    
                    # Başlangıç konumuna (x0, y0) göre hedef kare noktalarını üretiyoruz
                    rotadaki_noktalar = kare_noktalari(x0, y0, kenar=KENAR_UZUNLUGU)
                    
                    # 6. HEDEFLERİ 'hedefler.csv' DOSYASINA KAYDETME
                    # 'analiz.py' dosyası bu hedefleri elle koddan değil, bu CSV'den okuyacak.
                    with open("hedefler.csv", mode='w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(["hedef_id", "x", "y"])
                        for idx, (hx, hy) in enumerate(rotadaki_noktalar, 1):
                            writer.writerow([idx, round(hx, 2), round(hy, 2)])
                    print("\n[BİLGİ] Hedef koordinatlar 'hedefler.csv' dosyasına yazıldı.")
                    
                    # 7. ROTAYI UÇMA
                    rota_ucur(master, rotadaki_noktalar, hedef_z=-HEDEF_IRTIFA, tolerans=TOLERANS, timeout_nokta=40)

    except Exception as e:
        print(f"\n[HATA] Uçuş sırasında beklenmeyen bir hata oluştu: {e}")

    finally:
        # 8. GÜVENLİK (FAIL-SAFE) PROSEDÜRÜ
        # 'try...finally' yapısı sayesinde kalkış başarısız olsa veya kodda hata çıksa bile 
        # program mutlaka bu kısma girer ve RTL (Eve Dönüş / İniş) dener!
        print("\n[GÜVENLİK] İniş prosedürü başlatılıyor...")
        rtl_and_land(master, timeout=60)
        
        # Telemetri kayıt döngüsünü durduruyoruz
        ucus_devam_ediyor = False
        time.sleep(1)
        print("\n*** GÖREV VE TELEMETRİ KAYDI TAMAMLANDI ***")