import RPi.GPIO as GPIO
import socket
import threading
import time
import sys

# ==========================================
# KONFIGURASI JARINGAN (VPS BRIDGE)
# ==========================================
BRIDGE_IP = "103.150.117.90"
BRIDGE_PORT = 6001

# ==========================================
# KONFIGURASI PIN BCM RASPBERRY PI 3
# ==========================================
# Motor Kiri
IN1 = 17
IN2 = 27
ENA = 12

# Motor Kanan
IN3 = 5
IN4 = 6
ENB = 13

# Sensor Rintangan (Active LOW)
SENSOR_TENGAH = 23
SENSOR_KIRI = 24
SENSOR_KANAN = 25

# Variabel Global
pwm_a = None
pwm_b = None
client_socket = None
is_running = True

def setup_gpio():
    global pwm_a, pwm_b
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # Setup Motor
    motor_pins = [IN1, IN2, ENA, IN3, IN4, ENB]
    for pin in motor_pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

    # Inisialisasi PWM pada 1000Hz
    pwm_a = GPIO.PWM(ENA, 1000)
    pwm_b = GPIO.PWM(ENB, 1000)
    pwm_a.start(0)
    pwm_b.start(0)

    # Setup Sensor (Pull-Up internal aktif karena sensor biasanya Open Collector)
    sensor_pins = [SENSOR_TENGAH, SENSOR_KIRI, SENSOR_KANAN]
    for pin in sensor_pins:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ==========================================
# FUNGSI KONTROL KINEMATIKA MOTOR
# ==========================================
def kendali_motor(arah, kecepatan=50):
    if arah == "maju":
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        pwm_a.ChangeDutyCycle(kecepatan)
        pwm_b.ChangeDutyCycle(kecepatan)
    elif arah == "mundur":
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        pwm_a.ChangeDutyCycle(kecepatan)
        pwm_b.ChangeDutyCycle(kecepatan)
    elif arah == "kiri":
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.HIGH)
        GPIO.output(IN3, GPIO.HIGH)
        GPIO.output(IN4, GPIO.LOW)
        pwm_a.ChangeDutyCycle(kecepatan)
        pwm_b.ChangeDutyCycle(kecepatan)
    elif arah == "kanan":
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        pwm_a.ChangeDutyCycle(kecepatan)
        pwm_b.ChangeDutyCycle(kecepatan)
    elif arah == "berhenti":
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.LOW)
        pwm_a.ChangeDutyCycle(0)
        pwm_b.ChangeDutyCycle(0)

def eksekusi_perintah(perintah):
    print(f"[EKSEKUSI] Menerima instruksi: {perintah}")
    
    if perintah == "/maju":
        kendali_motor("maju", 60)
    elif perintah == "/mundur":
        kendali_motor("mundur", 60)
    elif perintah == "/kiri":
        kendali_motor("kiri", 50)
    elif perintah == "/kanan":
        kendali_motor("kanan", 50)
    elif perintah == "/berhenti" or perintah == "/stop":
        kendali_motor("berhenti")

# ==========================================
# THREAD 1: PEMROSESAN SENSOR REAL-TIME
# ==========================================
def thread_sensor():
    while is_running:
        # Sensor E18-D80NK dan IR umumnya mengeluarkan sinyal LOW (0) saat mendeteksi rintangan
        tengah_nabrak = (GPIO.input(SENSOR_TENGAH) == GPIO.LOW)
        kiri_nabrak = (GPIO.input(SENSOR_KIRI) == GPIO.LOW)
        kanan_nabrak = (GPIO.input(SENSOR_KANAN) == GPIO.LOW)

        if tengah_nabrak or kiri_nabrak or kanan_nabrak:
            kendali_motor("berhenti")
            peringatan = "[HARDWARE REPORT] Rintangan terdeteksi! Sistem pengereman darurat aktif."
            print(peringatan)
            
            if client_socket:
                try:
                    client_socket.sendall((peringatan + "\n").encode('utf-8'))
                except:
                    pass
            
            # Beri jeda agar tidak mengirim log beruntun terus menerus
            time.sleep(1)
        
        time.sleep(0.05) # Polling sensor setiap 50 milidetik

# ==========================================
# THREAD 2: KOMUNIKASI TCP KE VPS BRIDGE
# ==========================================
def thread_jaringan():
    global client_socket
    while is_running:
        try:
            print(f"[JARINGAN] Mencoba terhubung ke {BRIDGE_IP}:{BRIDGE_PORT}...")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10) # Timeout koneksi 10 detik
            client_socket.connect((BRIDGE_IP, BRIDGE_PORT))
            client_socket.settimeout(None) # Hapus timeout saat membaca aliran data
            
            print("[JARINGAN] Terhubung ke Linux VPS Bridge!")
            client_socket.sendall(b"PI3_READY\n")

            while is_running:
                data = client_socket.recv(4096)
                if not data:
                    break # Koneksi terputus dari server
                
                pesan = data.decode('utf-8').strip()
                if pesan:
                    # Anda dapat menambahkan modul Dekripsi GOST Python di sini jika diperlukan
                    if pesan.startswith("/ENC:"):
                        print("[JARINGAN] Menerima Perintah Terenkripsi. Membutuhkan modul dekripsi.")
                        # eksekusi_perintah(plain_text)
                    else:
                        eksekusi_perintah(pesan)
                        
        except Exception as e:
            print(f"[JARINGAN ERROR] {e}. Mengulang dalam 5 detik...")
            if client_socket:
                client_socket.close()
                client_socket = None
            time.sleep(5)

# ==========================================
# PROGRAM UTAMA (MAIN LOOP)
# ==========================================
if __name__ == "__main__":
    print("=== Sistem Pengendali Archuskha-AMR (Raspberry Pi 3) ===")
    setup_gpio()

    t_sensor = threading.Thread(target=thread_sensor)
    t_jaringan = threading.Thread(target=thread_jaringan)

    t_sensor.start()
    t_jaringan.start()

    try:
        while True:
            # Main loop dibiarkan idle karena eksekusi dilakukan oleh thread
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEM] Mematikan program...")
        is_running = False
        kendali_motor("berhenti")
        if client_socket:
            client_socket.close()
        GPIO.cleanup()
        sys.exit(0)