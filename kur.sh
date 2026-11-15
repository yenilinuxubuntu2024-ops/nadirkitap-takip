#!/data/data/com.termux/files/usr/bin/bash
# Termux (Android) kurulum betiği: nadirkitap takip botunu telefonda kurar ve başlatır.
set -e
pkg install -y python git termux-api >/dev/null 2>&1 || pkg install -y python git
cd "$HOME"
if [ -d nadirkitap-takip ]; then
  git -C nadirkitap-takip pull -q || true
else
  git clone -q https://github.com/yenilinuxubuntu2024-ops/nadirkitap-takip.git
fi
cd nadirkitap-takip

if [ ! -f config.json ]; then
  read -rp "WhatsApp numaran (örn. +905xxxxxxxxx): " TEL
  read -rp "CallMeBot apikey: " KEY
  printf '{"telefon": "%s", "apikey": "%s"}\n' "$TEL" "$KEY" > config.json
  chmod 600 config.json
fi

# Döngü betiği: her 10 dakikada bir kontrol
cat > calistir.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd "$HOME/nadirkitap-takip"
termux-wake-lock 2>/dev/null || true
while true; do
  python takip.py >> takip.log 2>&1
  tail -n 300 takip.log > takip.log.tmp && mv takip.log.tmp takip.log
  sleep 600
done
EOF
chmod +x calistir.sh

# Termux her açıldığında otomatik başlasın
grep -q nadirkitap-takip "$HOME/.bashrc" 2>/dev/null || cat >> "$HOME/.bashrc" <<'EOF'
pgrep -f nadirkitap-takip/calistir.sh >/dev/null || nohup "$HOME/nadirkitap-takip/calistir.sh" >/dev/null 2>&1 &
EOF

python takip.py --test
pgrep -f nadirkitap-takip/calistir.sh >/dev/null || nohup "$HOME/nadirkitap-takip/calistir.sh" >/dev/null 2>&1 &
echo
echo "✅ Kurulum tamam. Takip arka planda çalışıyor (10 dakikada bir)."
echo "   WhatsApp'a test mesajı gönderildi."
