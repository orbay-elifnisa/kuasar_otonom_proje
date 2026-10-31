import time
import math
from pymavlink import mavutil

# ==============================================================================
# 1. BAĞLANTI FONKSİYONU
# ==============================================================================
def net_connection(baglanti_adresi="udp:127.0.0.1:14552", timeout=10):    #net_connection bağlantı pythonun dronu görmesini ve haberleşmesini başlatır 
    print(f"[BAĞLANTI] {baglanti_adresi} adresine bağlanılıyor...")
    try:
        master = mavutil.mavlink_connection(baglanti_adresi)
        
        # MAVLink paketi duyana kadar bekler.
        # Eksik düzeltmesi: Sonsuz döngü olmaması için 'timeout' verdik.
        hb = master.wait_heartbeat(timeout=timeout)
        
        if hb is None:
            print("-> HATA: Heartbeat alınamadı! Bağlantı zaman aşımına uğradı.")
            return None
            
        print(f"-> BAŞARILI: Sistem {master.target_system}, Bileşen {master.target_component} bağlandı.")
        return master
    except Exception as e:
        print(f"-> HATA: Bağlantı kurulurken bir sorun oluştu: {e}")
        return None


# ==============================================================================
# 2. GENEL MOD DEĞİŞTİRME FONKSİYONU
# ==============================================================================
def set_mode(master, hedef_mod="GUIDED", timeout=20):    #set_mode mod değiştirme tek fonksiyon ile "GUIDED" yazarsak GUIDED, "RTL" yazarsak RTL yapar. önce kkomutu göderir sonra gelen HEARTBEAT paketlerine göre o moda geçip geçmediğini doğrular ve true yada false göderir
    print(f"[MOD] Mod '{hedef_mod}' olarak ayarlanıyor...")
    master.set_mode(hedef_mod)
    baslangic = time.time()
    
    while (time.time() - baslangic) < timeout:
        # HEARTBEAT mesajını dinleyerek modun gerçekten değişip değişmediğini kontrol ediyoruz
        hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb:
            mevcut_mod = mavutil.mode_string_v10(hb)
            if mevcut_mod == hedef_mod:
                print(f"-> BAŞARILI: Mod '{hedef_mod}' olarak doğrulandı.")
                return True
                
    print(f"-> HATA: Zaman aşımı! Mod '{hedef_mod}' yapılamadı.")
    return False

# ==============================================================================
# 3. ARM ETME FONKSİYONU
# ==============================================================================
def arm_drone(master, timeout=20):   
    print("[ARM] Drone motorları çalıştırılıyor...")
    master.arducopter_arm()
    baslangic = time.time()
    
    while (time.time() - baslangic) < timeout:
        # Hem HEARTBEAT hem de STATUSTEXT mesajlarını dinliyoruz çünkü dron motorları çalışmasada(arm olmazsa) PyMAVLink sessizce kalabilir o yüzden hata mesajlarını ekrana yazdırıyoruz ki sorunu görelim 
        msg = master.recv_match(type=['HEARTBEAT', 'STATUSTEXT'], blocking=True, timeout=1)
        if msg:
            if msg.get_type() == 'HEARTBEAT':
                if master.motors_armed():
                    print("-> BAŞARILI: Motorlar devreye girdi (ARM edildi).")
                    return True
            elif msg.get_type() == 'STATUSTEXT':
                # Eğer dron bir sebepten ARM olamıyorsa (örn: GPS yok, Pusula hatası) hatayı ekrana basar
                print(f"   [DRONE UYARISI]: {msg.text}")
                
    print("-> HATA: Zaman aşımı! Drone ARM edilemedi.")
    return False


# ==============================================================================
# 4. OTONOM KALKIŞ FONKSİYONU
# ==============================================================================
def takeoff(master, hedef_irtifa=10.0, timeout=30):  
    print(f"[KALKIŞ] {hedef_irtifa} metreye otonom kalkış yapılıyor...")
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, hedef_irtifa
    )
    
    baslangic = time.time()
    while (time.time() - baslangic) < timeout:
        # İrtifayı anlık olarak takip etmek için GLOBAL_POSITION_INT mesajını dinliyoruz
        msg = master.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=1)
        if msg:
            mevcut_irtifa = msg.relative_alt / 1000.0  # Milimetreyi metreye çeviriyoruz
            print(f"   Anlık İrtifa: {mevcut_irtifa:.2f} m")
            
            # Hedef irtifaya 0.5m kala kalkış tamamlandı sayıyoruz
            if mevcut_irtifa >= (hedef_irtifa - 0.5):
                print(f"-> BAŞARILI: Hedef irtifaya ulaşıldı! ({mevcut_irtifa:.2f} m)")
                return True
                
    print("-> HATA: Zaman aşımı! Belirlenen sürede hedef irtifaya kalkış tamamlanamadı.")
    return False

# ==============================================================================
# 5. TEK BİR NOKTAYA GİTME FONKSİYONU (LOCAL NED KOORDİNAT SİSTEMİ)
# ==============================================================================
def go_to_mc(master, hedef_x, hedef_y, hedef_z=-10.0, tolerans=2.0, timeout=40):
    """
    NE İŞE YARAR?: Drone'a belirli bir (X, Y, Z) koordinatını hedef gösterir.
    NED (North-East-Down) Mantığı:
      - X : Kuzey (+) / Güney (-)
      - Y : Doğu (+) / Batı (-)
      - Z : Aşağı (+) / Yukarı (-) -> İrtifa için Z değeri EKSİ (-) yazılır! (Örn: -10 = 10m Yukarı)
    """
    baslangic = time.time()
    
    while (time.time() - baslangic) < timeout:
        # set_position_target_local_ned_send: Dronun yerel başlangıç noktasına göre komut gönderir.
        # 0b0000111111111000 (Type Mask): Sadece X,Y,Z konumunu dikkate al, hız ve ivmeyi yoksay demektir.
        master.mav.set_position_target_local_ned_send(
            0, master.target_system, master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000111111111000,
            hedef_x, hedef_y, hedef_z,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        
        # Dronun anlık konumunu okumak için LOCAL_POSITION_NED mesajını dinliyoruz
        msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=1)
        if msg:
            mevcut_x = msg.x
            mevcut_y = msg.y
            
            # Öklid Mesafesi Formülü: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)
            # Dronun anlık konumu ile hedef nokta arasındaki mesafeyi metre cinsinden hesaplar.
            mesafe = math.sqrt((hedef_x - mevcut_x)**2 + (hedef_y - mevcut_y)**2)
            
            # Eğer kalan mesafe belirlenen toleransın (örn: 2 metre) altına indiyse noktaya varıldı sayılır
            if mesafe <= tolerans:
                print(f"   -> Noktaya ulaşıldı (X:{hedef_x:.1f}, Y:{hedef_y:.1f}) - Kalan Mesafe: {mesafe:.2f}m")
                return True
                
    print(f"-> HATA: Zaman aşımı! Noktaya ulaşılamadı: X={hedef_x}, Y={hedef_y}")
    return False


# ==============================================================================
# 6. ROTA NOKTA ÜRETİCİLERİ (BAŞLANGIÇ KONUMUNA GÖRE NÖTR HESAPLAMA)
# ==============================================================================
def kare_noktalari(x0, y0, kenar=20.0):
    """
    NE İŞE YARAR?: Drone'un o an kalktığı (x0, y0) konumunu başlangıç kabul ederek
    4 adet kare köşe koordinatı üretir ve liste halinde döndürür.
    """
    return [
        (x0 + kenar, y0),          # 1. Köşe: Kuzey yönüne 'kenar' kadar git
        (x0 + kenar, y0 + kenar),  # 2. Köşe: Kuzey-Doğu çaprazına git
        (x0, y0 + kenar),          # 3. Köşe: Doğu yönünde 'kenar' kadar git
        (x0, y0)                   # 4. Köşe: Tam başladığın kalkış noktasına geri dön
    ]


def daire_noktalari(x0, y0, yaricap=10.0, sayi=16):
    """
    NE İŞE YARAR?: Trigonometri (Sinüs/Kosinüs) kullanarak (x0, y0) kalkış noktasından itibaren
    pürüzsüz bir çember çizmek için nokta koordinat listesi üretir.
    """
    noktalar = []
    for i in range(1, sayi + 1):
        aci = (2 * math.pi / sayi) * i        # 360 dereceyi (2*pi radyan) parça sayısına bölüyoruz
        x = x0 + yaricap * (1 - math.cos(aci)) # Kosinüs ile Kuzey eksenindeki eğim hesabı
        y = y0 + yaricap * math.sin(aci)        # Sinüs ile Doğu eksenindeki eğim hesabı
        noktalar.append((x, y))
    return noktalar


# ==============================================================================
# 7. GENEL ROTA UÇURMA FONKSİYONU
# ==============================================================================
def rota_ucur(master, noktalar, hedef_z=-10.0, tolerans=2.0, timeout_nokta=40):
    """
    NE İŞE YARAR?: Parametre olarak gelen liste (kare veya daire noktaları) içindeki 
    tüm koordinatları sırayla gezmek için 'go_to_mc' fonksiyonunu bir döngüde çalıştırır.
    """
    toplam = len(noktalar)
    print(f"\n[ROTA] Toplam {toplam} noktalı rota başlatılıyor...")
    
    for idx, (x, y) in enumerate(noktalar, 1):
        print(f"   - Hedef {idx}/{toplam}: X={x:.2f}m, Y={y:.2f}m")
        # Noktaya gitme fonksiyonunu tek tek çağırıyoruz
        basarili = go_to_mc(master, hedef_x=x, hedef_y=y, hedef_z=hedef_z, tolerans=tolerans, timeout=timeout_nokta)
        
        # Eğer tek bir noktada bile zaman aşımı olursa uçuşu tehlikeye atmamak için rotayı keser
        if not basarili:
            print(f"-> HATA: Rota {idx}. noktada tıkandı!")
            return False
            
    print("-> BAŞARILI: Rota tamamen uçuldu.")
    return True


# ==============================================================================
# 8. RTL (EVE DÖNÜŞ/İNİŞ) VE DISARM KONTROLÜ
# ==============================================================================
def rtl_and_land(master, timeout=60):
    """
    NE İŞE YARAR?: Drone'u otonom olarak eve döndürür (RTL), inişini takip eder ve motorlar 
    tamamen kapandığında (Disarm) görevin başarıyla bittiğini onaylar.
    """
    print("\n[RTL & İNİŞ] Güvenli iniş prosedürü başlatılıyor...")
    
    # RTL moduna geçişi 'set_mode' fonksiyonu üzerinden Heartbeat ile doğrulayarak yapıyoruz
    mod_ok = set_mode(master, hedef_mod="RTL", timeout=15)
    if not mod_ok:
        print("-> UYARI: set_mode ile RTL doğrulanamadı, tekrar komut gönderiliyor...")
        master.set_mode("RTL")
        
    baslangic = time.time()
    while (time.time() - baslangic) < timeout:
        msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'HEARTBEAT'], blocking=True, timeout=1)
        if msg:
            if msg.get_type() == 'GLOBAL_POSITION_INT':
                irtifa = msg.relative_alt / 1000.0
                print(f"   İniş yapılıyor... Anlık İrtifa: {irtifa:.2f} m")
            
            # Motorlar disarm oldu mu (otomatik kapandı mı)?
            if not master.motors_armed():
                print("-> BAŞARILI: Drone güvenle yere indi ve motorlar kapandı (Disarm).")
                return True
                
    print("-> HATA: Zaman aşımı! Drone belirlenen sürede inip motorları kapatamadı.")
    return False

# ==============================================================================
# 5. TEK BİR NOKTAYA GİTME FONKSİYONU (LOCAL NED KOORDİNAT SİSTEMİ)
# ==============================================================================
def go_to_mc(master, hedef_x, hedef_y, hedef_z=-10.0, tolerans=2.0, timeout=40):
    """
    NE İŞE YARAR?: Drone'a belirli bir (X, Y, Z) koordinatını hedef gösterir.
    NED (North-East-Down) Mantığı:
      - X : Kuzey (+) / Güney (-)
      - Y : Doğu (+) / Batı (-)
      - Z : Aşağı (+) / Yukarı (-) -> İrtifa için Z değeri EKSİ (-) yazılır! (Örn: -10 = 10m Yukarı)
    """
    baslangic = time.time()
    
    while (time.time() - baslangic) < timeout:
        # set_position_target_local_ned_send: Dronun yerel başlangıç noktasına göre komut gönderir.
        # 0b0000111111111000 (Type Mask): Sadece X,Y,Z konumunu dikkate al, hız ve ivmeyi yoksay demektir.
        master.mav.set_position_target_local_ned_send(
            0, master.target_system, master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000111111111000,
            hedef_x, hedef_y, hedef_z,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        
        # Dronun anlık konumunu okumak için LOCAL_POSITION_NED mesajını dinliyoruz
        msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=1)
        if msg:
            mevcut_x = msg.x
            mevcut_y = msg.y
            
            # Öklid Mesafesi Formülü: d = sqrt((x2 - x1)^2 + (y2 - y1)^2)
            # Dronun anlık konumu ile hedef nokta arasındaki mesafeyi metre cinsinden hesaplar.
            mesafe = math.sqrt((hedef_x - mevcut_x)**2 + (hedef_y - mevcut_y)**2)
            
            # Eğer kalan mesafe belirlenen toleransın (örn: 2 metre) altına indiyse noktaya varıldı sayılır
            if mesafe <= tolerans:
                print(f"   -> Noktaya ulaşıldı (X:{hedef_x:.1f}, Y:{hedef_y:.1f}) - Kalan Mesafe: {mesafe:.2f}m")
                return True
                
    print(f"-> HATA: Zaman aşımı! Noktaya ulaşılamadı: X={hedef_x}, Y={hedef_y}")
    return False


# ==============================================================================
# 6. ROTA NOKTA ÜRETİCİLERİ (BAŞLANGIÇ KONUMUNA GÖRE NÖTR HESAPLAMA)
# ==============================================================================
def kare_noktalari(x0, y0, kenar=20.0):
    """
    NE İŞE YARAR?: Drone'un o an kalktığı (x0, y0) konumunu başlangıç kabul ederek
    4 adet kare köşe koordinatı üretir ve liste halinde döndürür.
    """
    return [
        (x0 + kenar, y0),          # 1. Köşe: Kuzey yönüne 'kenar' kadar git
        (x0 + kenar, y0 + kenar),  # 2. Köşe: Kuzey-Doğu çaprazına git
        (x0, y0 + kenar),          # 3. Köşe: Doğu yönünde 'kenar' kadar git
        (x0, y0)                   # 4. Köşe: Tam başladığın kalkış noktasına geri dön
    ]


def daire_noktalari(x0, y0, yaricap=10.0, sayi=16):
    """
    NE İŞE YARAR?: Trigonometri (Sinüs/Kosinüs) kullanarak (x0, y0) kalkış noktasından itibaren
    pürüzsüz bir çember çizmek için nokta koordinat listesi üretir.
    """
    noktalar = []
    for i in range(1, sayi + 1):
        aci = (2 * math.pi / sayi) * i        # 360 dereceyi (2*pi radyan) parça sayısına bölüyoruz
        x = x0 + yaricap * (1 - math.cos(aci)) # Kosinüs ile Kuzey eksenindeki eğim hesabı
        y = y0 + yaricap * math.sin(aci)        # Sinüs ile Doğu eksenindeki eğim hesabı
        noktalar.append((x, y))
    return noktalar


# ==============================================================================
# 7. GENEL ROTA UÇURMA FONKSİYONU
# ==============================================================================
def rota_ucur(master, noktalar, hedef_z=-10.0, tolerans=2.0, timeout_nokta=40):
    """
    NE İŞE YARAR?: Parametre olarak gelen liste (kare veya daire noktaları) içindeki 
    tüm koordinatları sırayla gezmek için 'go_to_mc' fonksiyonunu bir döngüde çalıştırır.
    """
    toplam = len(noktalar)
    print(f"\n[ROTA] Toplam {toplam} noktalı rota başlatılıyor...")
    
    for idx, (x, y) in enumerate(noktalar, 1):
        print(f"   - Hedef {idx}/{toplam}: X={x:.2f}m, Y={y:.2f}m")
        # Noktaya gitme fonksiyonunu tek tek çağırıyoruz
        basarili = go_to_mc(master, hedef_x=x, hedef_y=y, hedef_z=hedef_z, tolerans=tolerans, timeout=timeout_nokta)
        
        # Eğer tek bir noktada bile zaman aşımı olursa uçuşu tehlikeye atmamak için rotayı keser
        if not basarili:
            print(f"-> HATA: Rota {idx}. noktada tıkandı!")
            return False
            
    print("-> BAŞARILI: Rota tamamen uçuldu.")
    return True


# ==============================================================================
# 8. RTL (EVE DÖNÜŞ/İNİŞ) VE DISARM KONTROLÜ
# ==============================================================================
def rtl_and_land(master, timeout=60):
    """
    NE İŞE YARAR?: Drone'u otonom olarak eve döndürür (RTL), inişini takip eder ve motorlar 
    tamamen kapandığında (Disarm) görevin başarıyla bittiğini onaylar.
    """
    print("\n[RTL & İNİŞ] Güvenli iniş prosedürü başlatılıyor...")
    
    # RTL moduna geçişi 'set_mode' fonksiyonu üzerinden Heartbeat ile doğrulayarak yapıyoruz
    mod_ok = set_mode(master, hedef_mod="RTL", timeout=15)
    if not mod_ok:
        print("-> UYARI: set_mode ile RTL doğrulanamadı, tekrar komut gönderiliyor...")
        master.set_mode("RTL")
        
    baslangic = time.time()
    while (time.time() - baslangic) < timeout:
        msg = master.recv_match(type=['GLOBAL_POSITION_INT', 'HEARTBEAT'], blocking=True, timeout=1)
        if msg:
            if msg.get_type() == 'GLOBAL_POSITION_INT':
                irtifa = msg.relative_alt / 1000.0
                print(f"   İniş yapılıyor... Anlık İrtifa: {irtifa:.2f} m")
            
            # Motorlar disarm oldu mu (otomatik kapandı mı)?
            if not master.motors_armed():
                print("-> BAŞARILI: Drone güvenle yere indi ve motorlar kapandı (Disarm).")
                return True
                
    print("-> HATA: Zaman aşımı! Drone belirlenen sürede inip motorları kapatamadı.")
    return False
