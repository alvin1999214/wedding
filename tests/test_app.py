import io
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ['DATA_DIR'] = TEMP.name
os.environ['DOMAIN'] = 'localhost'
from app import app, db, qr_bytes, BRANDING_DEFAULTS

class WeddingTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['TESTING'] = True
        with app.app_context():
            for table in ('memberships', 'guests', 'groups', 'admins', 'attempts'):
                db().execute('DELETE FROM ' + table)
            from app import DEFAULTS
            import json
            db().execute('UPDATE settings SET value=?', (json.dumps(DEFAULTS),))
            db().commit()
        Path(TEMP.name, 'setup.token').write_text('test-setup-token')

    def post(self, url, data=None):
        with self.client.session_transaction() as session:
            session.setdefault('csrf', 'test-csrf')
            token = session['csrf']
        return self.client.post(url, data={**(data or {}), 'csrf': token})

    def login(self):
        response = self.post('/admin/setup', {**BRANDING_DEFAULTS, 'token': 'test-setup-token', 'username': 'admin', 'password': 'long-test-password'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Path(TEMP.name, 'setup.token').exists())
        self.assertEqual(self.post('/admin/login', {'username': 'admin', 'password': 'long-test-password'}).status_code, 302)

    def guest(self, name='測試賓客', groups=None):
        response = self.post('/admin/guests', {'name': name, 'table_name': '第 3 桌', 'groups': groups or []})
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            return db().execute('SELECT id FROM guests WHERE name=?', (name,)).fetchone()['id']

    def test_petals_work_with_strict_style_policy(self):
        response = self.client.get('/')
        self.assertIn("style-src 'self';", response.headers['Content-Security-Policy'])
        petals = re.findall(r'<svg class="falling-petal [^>]+>', response.text)
        self.assertEqual(len(petals), 32)
        with self.client.get('/static/style.css') as stylesheet:
            css = stylesheet.text
        for petal in petals:
            self.assertNotIn('style=', petal)
        self.assertNotIn('@keyframes petal-fall', css)
        self.assertRegex(css, r'\.falling-petal\{[^}]*opacity:0')

    def test_public_and_auth_guards(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/health').json, {'status': 'ok'})
        for url in ('/admin', '/admin/qrcodes.zip', '/admin/qr/anything.png'):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post('/admin/guests', data={'name': 'attack'}).status_code, 400)
        self.assertEqual(self.post('/admin/guests', {'name': 'attack'}).status_code, 302)
        self.assertEqual(self.client.get('/00000000-0000-0000-0000-000000000000').status_code, 404)

    def test_setup_login_logout(self):
        self.assertEqual(self.client.get('/admin/setup').status_code, 200)
        self.post('/admin/setup', {'token': 'wrong', 'username': 'admin', 'password': 'long-test-password'})
        with app.app_context():
            self.assertIsNone(db().execute('SELECT 1 FROM admins').fetchone())
        self.login()
        self.assertEqual(self.client.get('/admin').status_code, 200)
        self.assertEqual(self.client.get('/admin/setup').status_code, 302)
        self.post('/admin/logout')
        self.assertEqual(self.client.get('/admin').status_code, 302)

    def test_groups_memberships_and_privacy(self):
        self.login()
        self.post('/admin/groups', {'name': '大學好友', 'time': '17:15', 'location': '花園', 'position': '1'})
        with app.app_context():
            group_id = str(db().execute('SELECT id FROM groups').fetchone()[0])
        first = self.guest('小明', [group_id])
        second = self.guest('小美')
        self.assertIn('大學好友', self.client.get('/invitation/'+first).text)
        self.assertNotIn('大學好友', self.client.get('/invitation/'+second).text)
        self.assertNotIn('小美', self.client.get('/invitation/'+first).text)
        self.assertEqual(self.client.get('/admin').status_code, 200)
        self.post('/admin/guests', {'id': first, 'name': '新名字', 'groups': [group_id]})
        self.assertIn('新名字', self.client.get('/invitation/'+first).text)
        self.post('/admin/groups/'+group_id+'/delete')
        with app.app_context():
            self.assertEqual(db().execute('SELECT COUNT(*) FROM memberships').fetchone()[0], 0)

    def test_modes_keep_same_qr(self):
        self.login()
        guest = self.guest()
        canonical = '/'+guest
        self.assertEqual(self.client.get(canonical).location, '/invitation/'+guest)
        self.post('/admin/mode', {'mode': 'lottery'})
        response = self.client.get(canonical)
        self.assertEqual(response.location, '/games/lottery?guest='+guest)
        self.assertIn('測試賓客', self.client.get(response.location).text)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.post('/admin/mode', {'mode': 'custom', 'custom_path': '/games/new'})
        self.assertEqual(self.client.get(canonical).location, '/games/new?guest='+guest)
        self.assertEqual(self.post('/admin/mode', {'mode': 'custom', 'custom_path': '//evil.com'}).status_code, 400)
        self.post('/admin/mode', {'mode': 'wedding'})
        self.assertEqual(self.client.get(canonical).location, '/invitation/'+guest)

    def test_qr_export(self):
        self.login()
        guest = self.guest()
        result = self.client.get('/admin/qr/'+guest+'.png')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.data.startswith(b'\x89PNG'))
        with patch('app.qrcode.make') as make:
            qr_bytes(guest)
            make.assert_called_once_with('http://localhost/'+guest)
        archive = zipfile.ZipFile(io.BytesIO(self.client.get('/admin/qrcodes.zip').data))
        self.assertIn(guest+'.png', archive.namelist())
        self.assertIn('測試賓客', archive.read('guests.csv').decode('utf-8-sig'))

    def test_delete_invalidates_invitation(self):
        self.login()
        guest = self.guest()
        self.post('/admin/guests/'+guest+'/delete')
        self.assertEqual(self.client.get('/'+guest).status_code, 404)
        self.assertEqual(self.client.get('/invitation/'+guest).status_code, 404)
        self.assertEqual(self.client.get('/games/lottery?guest='+guest).status_code, 404)

    def test_settings_validation_and_escaping(self):
        self.login()
        payload = dict(couple='<script>alert(1)</script>', date='2027-01-01', venue='婚宴場地', address='台北', message='歡迎', lottery_message='等候', schedule='18:00 | 婚宴\n16:00 | 迎賓')
        self.assertEqual(self.post('/admin/settings', payload).status_code, 302)
        page = self.client.get('/').text
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertEqual(self.post('/admin/settings', {**payload, 'schedule': '25:99 | wrong'}).status_code, 400)
        self.assertEqual(self.post('/admin/groups', {'name': '測試', 'position': 'bad'}).status_code, 400)

    def test_tunnel_client_ip_for_throttling(self):
        with self.client.session_transaction() as session:
            session['csrf'] = 'test-csrf'
        payload = {'csrf': 'test-csrf', 'token': 'wrong', 'username': 'admin', 'password': 'long-test-password'}
        for _ in range(15):
            self.client.post('/admin/setup', data=payload, headers={'CF-Connecting-IP': '192.0.2.1'})
        self.assertEqual(self.client.post('/admin/setup', data=payload, headers={'CF-Connecting-IP': '192.0.2.1'}).status_code, 429)
        self.assertEqual(self.client.post('/admin/setup', data=payload, headers={'CF-Connecting-IP': '192.0.2.2'}).status_code, 200)
        self.client.post('/admin/setup', data=payload, headers={'X-Forwarded-For': '192.0.2.99'})
        with app.app_context():
            self.assertIsNone(db().execute('SELECT 1 FROM attempts WHERE ip=?', ('192.0.2.99',)).fetchone())

    def test_branding_setup_and_updates(self):
        branding = {'brand_name': '我們的故事', 'brand_tagline': '今天一起相聚', 'site_title': '小明與小美的婚禮', 'admin_label': '婚禮控制室'}
        response = self.post('/admin/setup', {**branding, 'token': 'test-setup-token', 'username': 'admin', 'password': 'long-test-password'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('<title>小明與小美的婚禮</title>', self.client.get('/').text)
        self.assertIn('我們的故事', self.client.get('/admin/login').text)
        self.assertEqual(self.post('/admin/branding', branding).status_code, 302)
        self.post('/admin/login', {'username': 'admin', 'password': 'long-test-password'})
        guest = self.guest()
        for path in ('/', '/invitation/'+guest, '/games/lottery?guest='+guest, '/missing', '/admin'):
            page = self.client.get(path).text
            self.assertIn('我們的故事', page)
            self.assertNotIn('Gather', page)
        updated = {**branding, 'brand_name': '<script>bad</script>', 'site_title': '新的頁籤標題'}
        self.assertEqual(self.post('/admin/branding', updated).status_code, 302)
        page = self.client.get('/').text
        self.assertIn('<title>新的頁籤標題</title>', page)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', page)
        self.assertNotIn('<script>bad</script>', page)
        self.assertEqual(self.post('/admin/branding', {**branding, 'site_title': ''}).status_code, 400)
        self.assertIn('新的頁籤標題', self.client.get('/').text)
        self.assertEqual(self.post('/admin/branding', {**branding, 'brand_name': 'x'*121}).status_code, 400)

    def test_legacy_settings_branding_defaults(self):
        import json
        from app import DEFAULTS
        with app.app_context():
            legacy = {key: value for key, value in DEFAULTS.items() if key not in BRANDING_DEFAULTS}
            legacy['couple'] = '既有新人姓名'
            db().execute('UPDATE settings SET value=?', (json.dumps(legacy),))
            db().commit()
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn('既有新人姓名', page.text)
        self.assertIn('Gather', page.text)

    def test_login_throttling(self):
        for _ in range(15):
            self.post('/admin/setup', {'token': 'wrong', 'username': 'admin', 'password': 'long-test-password'})
        self.assertEqual(self.post('/admin/setup', {'token': 'wrong', 'username': 'admin', 'password': 'long-test-password'}).status_code, 429)

if __name__ == '__main__':
    unittest.main()
