# Gather｜婚禮當日網站

繁體中文、手機優先的婚禮網站，使用 Flask + SQLite + Gunicorn，透過 Docker Compose 在 localhost 提供 HTTP，公開 HTTPS 由你部署的 Cloudflare Tunnel 處理。沒有第三方帳號、CDN 或外部字型依賴。`.env` 只需填寫 `DOMAIN`；管理員及工作階段密鑰會在持久化資料卷內建立。

## 功能

- 每位賓客擁有不可預測的 UUID 專屬連結及 PNG QR code。
- 婚禮資訊、地圖導航、當日流程、個人桌號及個人拍照組別。
- 原創 SVG 婚戒花園，CSS 3D 傾斜、點擊／觸控綻放動畫；支援鍵盤操作與減少動態效果設定。
- 管理員建立、編輯、刪除賓客及拍照組別，一人可分配多組，組別可排序。
- 單張 QR code 或整批 ZIP 下載，ZIP 附有 UUID／姓名／桌號／連結對照 CSV。
- 後臺統一切換婚禮頁、抽獎等候頁或自訂站內遊戲路徑。
- 管理員密碼雜湊、CSRF、登入速率限制、HTTP-only session、HTTPS secure cookie、CSP。

## 正式部署

需要安裝 Docker Engine 與 Docker Compose plugin 的主機。Cloudflare Tunnel 由你另外設定；此 Compose 只啟動網站，不包含 cloudflared。網站只綁定主機的 `127.0.0.1`，不需要為網站開放對外的 80／443 或 8080 連接埠。

```bash
cp .env.example .env
```

編輯 `.env`，只有一行：

```dotenv
DOMAIN=wedding.example.com
```

填寫實際網域，不要加 `https://`、路徑或尾端斜線。正式部署後請保持網域不變，以免已印製的 QR code 連不到原址。

```bash
docker compose up -d --build
docker compose ps
```

預設本機入口為 `http://127.0.0.1:8080`。連接埠直接在 `compose.yaml` 設定：

```yaml
ports:
  - "127.0.0.1:8080:8000"
```

修改左側 `8080` 為你要的主機連接埠，右側 `8000` 是容器內部連接埠，保持不變。修改後重新執行 `docker compose up -d`。

### Cloudflare Tunnel

在主機上運行 cloudflared，將公開 hostname（與 `.env` 的 `DOMAIN` 相同）對應到 HTTP service `http://127.0.0.1:8080`。若更換主機連接埠，也需同步修改 Tunnel 的 service URL。

```text
賓客 → https://你的網域 → Cloudflare Tunnel → http://127.0.0.1:8080 → app:8000
```

若 cloudflared 運行在另一個容器，該容器的 `localhost` 不是主機。可讓 cloudflared 加入本專案的 Docker network，並將 service URL 設為 `http://app:8000`；不要使用該容器內的 `127.0.0.1:8080`。

公開入口為 `https://你的網域`，後臺為 `https://你的網域/admin`。QR code 一律使用 `.env` 的公開網域，不會使用本機連接埠。當 `DOMAIN` 為正式網域，session cookie 保持 `Secure`，請透過 Tunnel 的 HTTPS 網址初始化及登入後臺。登入限速使用 Tunnel 提供的 `CF-Connecting-IP`；此信任建立在 origin 僅供本機／可信任 Tunnel 存取，不要將 app 直接公開至網際網路。

### 首次建立管理員

透過主機終端取得一次性設定碼：

```bash
docker compose exec app cat /app/data/setup.token
```

開啟 `https://你的網域/admin/setup`，輸入設定碼，設定帳號與至少 12 個字元的密碼。建立完成後設定碼檔案會刪除，初始化頁不再接受新管理員。設定碼相當於初始化權限，勿轉寄給賓客。

登入後依序：

1. 在「婚禮資訊」替換示範新人姓名、日期、場地地址、祝福文字及行程。
2. 新增拍照組別，設定時間、地點、排序。
3. 新增賓客並勾選所屬組別，填寫桌號及提醒。
4. 下載 QR code，實際用手機掃描確認後再印製。
5. 現場需要時切換「現場跳轉模式」。

### 本機 Docker 測試

尚未建立 Tunnel 時，可暫時將 `.env` 設為 `DOMAIN=localhost:8080`，啟動後使用 `http://localhost:8080` 測試完整登入流程。若修改 Compose 的主機連接埠，這裡也需一致。本機模式的 QR code 僅供本機測試，手機無法用 localhost 連到主機。

正式啟用前將 `DOMAIN` 改回公開網域，重新執行 `docker compose up -d`，再產生並印製正式 QR code。

## 掃碼與擴充規則

```text
https://domain/賓客UUID  ← 永久寫入 QR code 的網址
            │ 每次掃描讀取後臺設定，302 + Cache-Control: no-store
            ├─ wedding → /invitation/賓客UUID
            ├─ lottery → /games/lottery?guest=賓客UUID
            └─ custom  → /games/你新增的路由?guest=賓客UUID
```

已開啟的頁面不會被強制跳轉；賓客再次掃碼才套用新模式。邀請函的直接網址仍可開啟。刪除賓客會讓其 QR code、邀請函及抽獎入口失效；編輯姓名不會改變 UUID。

`/games/lottery` **只是抽獎等候頁**，沒有抽獎、得獎判定或參加登記。日後可以在 `app.py` 加入遊戲路由，使用 `get_guest(request.args.get('guest', ''))` 驗證賓客，再開發獨立的參賽資料表及規則。自訂路徑只允許 `/games/` 下的站內路由；必須先實作，否則該路徑會回傳 404。UUID 是持有即可存取的邀請憑證，切勿公開名單或連結；涉及獎品領取時應另做核驗。

## 資料與備份

- `wedding_data`：SQLite 資料庫、session 密鑰、尚未使用的初始化碼。
- 更新程式用 `docker compose up -d --build`，既有資料保留。
- `docker compose down` 保留資料卷；**`docker compose down -v` 會刪除資料，請勿當成一般重啟命令使用。**

一致性離線備份（會短暫中斷服務）：

```bash
docker compose stop app
docker compose run --rm --no-deps --user root --entrypoint tar app -czf - -C /app data > wedding-backup.tar.gz
docker compose start app
```

請確認備份命令成功再保存檔案，並將備份存到主機以外的安全位置。備份包含個人資料與密鑰。

還原到相同專案的資料卷（會覆寫備份內的對應檔案，請先備份現有資料）：

```bash
docker compose stop app
docker compose run --rm --no-deps -T --user root --entrypoint sh app -c 'rm -f /app/data/wedding.db-wal /app/data/wedding.db-shm; tar -xzf - -C /app; chown -R wedding:wedding /app/data' < wedding-backup.tar.gz
docker compose start app
```

單一 app 服務的兩個 Gunicorn workers 共用 SQLite WAL，適合單場婚禮。不要跨主機共用 SQLite 或擴展為多個 app replicas；需要多主機時應遷移 PostgreSQL。工作階段期限為 8 小時，重啟保留密鑰與登入狀態。

## 開發及測試

需 Python 3.12+：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
DOMAIN=localhost:8000 .venv/bin/flask --app app run --host 127.0.0.1 --port 8000
```

開啟 `http://localhost:8000`，初始化碼位於 `data/setup.token`。Flask 開發伺服器只適用於本機開發。測試使用臨時資料庫，不會修改 `data/`。

`requirements.in` 記錄直接依賴；`requirements.txt` 鎖定直接及間接依賴與雜湊。需要更新時可執行 `uv pip compile requirements.in -o requirements.txt --generate-hashes`。

專案結構：

```text
app.py                  路由、驗證、資料庫、QR code
static/style.css        響應式佈局與動畫
static/app.js           SVG 互動、賓客搜尋、操作確認
templates/              賓客、管理員、登入、等候頁
tests/test_app.py       功能及安全邊界整合測試
compose.yaml            localhost HTTP 連接埠 + app + 持久化資料卷
Dockerfile              非 root Gunicorn 容器
```

目前測試覆蓋初始化／登入／登出、權限與 CSRF、登入限速、賓客及組別操作、個人資料隔離、固定連結切換、QR code 與 ZIP、輸入驗證及 HTML 跳脫。部署前仍需在實際網域驗證 Cloudflare Tunnel、TLS，並在目標手機實際掃碼與檢查動畫。
