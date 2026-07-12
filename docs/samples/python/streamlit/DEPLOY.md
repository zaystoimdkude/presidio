# Presidio Streamlit — Сервер дээр байршуулах заавар
## (GitHub ашиглахгүйгээр)

---

## 1-р алхам: Файлуудыг серверт хуулах

### Арга А — ZIP файлаар (хамгийн амар)

**Таны Windows компьютер дээр:**
```powershell
# Streamlit folder-ийг ZIP болгох
Compress-Archive -Path "C:\Users\monok\OneDrive\Desktop\Presidio\presidio\docs\samples\python\streamlit\*" `
  -DestinationPath "C:\Users\monok\Desktop\presidio-streamlit.zip"
```

**Серверт upload хийх (SCP ашиглан):**
```bash
scp presidio-streamlit.zip your_user@your_server_ip:/home/your_user/
```

> Хэрэв Windows дээр WinSCP, FileZilla, эсвэл Cyberduck ашиглаж байгаа бол
> график интерфейсээр drag and drop хийж болно.

**Серверт задлах:**
```bash
ssh your_user@your_server_ip

mkdir -p ~/presidio-app
cd ~/presidio-app
unzip ~/presidio-streamlit.zip
```

### Арга Б — rsync (сүлжээгээр шууд хуулах)
```bash
rsync -avz \
  "C:/Users/monok/OneDrive/Desktop/Presidio/presidio/docs/samples/python/streamlit/" \
  your_user@your_server_ip:~/presidio-app/
```

---

## 2-р алхам: Python орчин тохируулах

```bash
# Python 3.10+ байгааг шалгах
python3 --version

# Virtual environment үүсгэх (тусгаарлагдсан орчин)
cd ~/presidio-app
python3 -m venv venv

# Идэвхжүүлэх
source venv/bin/activate

# Dependencies суулгах
pip install --upgrade pip
pip install -r requirements.txt

# spaCy model татах (default model)
python -m spacy download en_core_web_lg
```

> Анхны суулгалт 5-15 минут зарцуулна (torch, flair зэрэг том package).

---

## 3-р алхам: Туршиж ажиллуулах

```bash
cd ~/presidio-app
source venv/bin/activate

streamlit run presidio_streamlit.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true
```

Browser дээр нээж шалгах:
```
http://your_server_ip:8501
```

---

## 4-р алхам: Автоматаар ажиллах болгох (systemd)

```bash
# Service файл үүсгэх
sudo nano /etc/systemd/system/presidio-streamlit.service
```

Дараах агуулгыг оруулах (your_user-ийг өөрчил):
```ini
[Unit]
Description=Presidio Streamlit PII Masking App
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/presidio-app
Environment="PATH=/home/your_user/presidio-app/venv/bin"
ExecStart=/home/your_user/presidio-app/venv/bin/streamlit run presidio_streamlit.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Service-г идэвхжүүлж эхлүүлэх
sudo systemctl daemon-reload
sudo systemctl enable presidio-streamlit
sudo systemctl start presidio-streamlit

# Төлөв шалгах
sudo systemctl status presidio-streamlit

# Log харах
sudo journalctl -u presidio-streamlit -f
```

### Энгийн арга — nohup (туршилтанд)
```bash
cd ~/presidio-app
source venv/bin/activate

nohup streamlit run presidio_streamlit.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  > ~/presidio-app/streamlit.log 2>&1 &

echo "Log харах: tail -f ~/presidio-app/streamlit.log"
```

Зогсоох:
```bash
kill $(lsof -t -i:8501)
```

---

## 5-р алхам: Firewall тохируулах (шаардлагатай бол)

```bash
# Ubuntu UFW
sudo ufw allow 8501/tcp
sudo ufw reload

# CentOS/RHEL firewalld
sudo firewall-cmd --permanent --add-port=8501/tcp
sudo firewall-cmd --reload
```

---

## Хурдан лавлагаа

| Үйлдэл | Команд |
|--------|--------|
| Эхлүүлэх | `sudo systemctl start presidio-streamlit` |
| Зогсоох | `sudo systemctl stop presidio-streamlit` |
| Дахин эхлүүлэх | `sudo systemctl restart presidio-streamlit` |
| Log харах | `sudo journalctl -u presidio-streamlit -f` |
| App URL | `http://SERVER_IP:8501` |

---

## Асуудал гарвал

**Port аль хэдийн ашиглагдаж байна:**
```bash
sudo lsof -i :8501
kill -9 <PID>
```

**Module олдохгүй:**
```bash
cd ~/presidio-app && source venv/bin/activate
pip install -r requirements.txt
```

**spaCy model олдохгүй:**
```bash
source venv/bin/activate
python -m spacy download en_core_web_lg
```
