"""Real HTTP/policy/migrations, synthetic SQLite only; no GPU or media I/O."""
import uuid

from test_library_reads import LibraryReadTests
from app.access.transport import COOKIE, csrf_token


class FamilyStoryTests(LibraryReadTests):
    def payload(self, **changes):
        return dict(title='Grandma’s garden', text='First visit. 奶奶的花园。', language='mixed',
                    byline='Dad', mutation_id=str(uuid.uuid4()), **changes)

    def write(self, method, path, body, token=None):
        return self.client.request(method, path, json=body,
            headers={'Authorization': 'Bearer ' + (token or self.owner_token)})

    def create(self, text=None, asset=101, token=None):
        body = self.payload()
        if text is not None:
            body['text'] = text
        response = self.write('POST', f'/assets/{asset}/stories?library=family-a', body, token)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def search(self, text, source='all', token=None, media='all'):
        return self.write('POST', '/library/search?library=family-a',
            dict(text=text, source=source, media=media, page='1'), token or self.member_token)

    def test_long_bilingual_story_edits_history_and_ai_coexist(self):
        text = ('A treasured memory. 珍贵的回忆。\n' * 400) + '<script>not markup</script>'
        story = self.create(text)
        path = f"/stories/{story['id']}?library=family-a"
        updated = self.payload(revision='1'); updated['text'] = 'Updated: 第一次走路'
        result = self.write('PUT', path, updated)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['revision'], 2)
        history = self.get(f"/stories/{story['id']}/history?library=family-a", self.owner_token).json()
        self.assertEqual([r['revision'] for r in history['items']], [2, 1])
        self.assertEqual(history['items'][1]['text'], text)
        self.assertEqual(self.get('/assets/101/captions?library=family-a').json()['items'][0]['text'], 'caption-101')
        # Simulate the inference persistence effect without importing/starting GPU code.
        self.mutate("UPDATE captions SET text='New AI description' WHERE id=101")
        self.assertEqual(self.get('/assets/101/stories?library=family-a').json()['items'][0]['text'], updated['text'])
        self.assertEqual(self.search('第一次').json()['items'][0]['match']['source'], 'family')
        self.assertEqual(self.search('treasured').json()['total'], 0)  # history not searchable
        self.assertEqual(self.search('New AI', source='ai').json()['total'], 1)

    def test_idempotency_conflicts_and_no_silent_overwrite(self):
        body = self.payload()
        first = self.write('POST', '/assets/101/stories?library=family-a', body).json()
        again = self.write('POST', '/assets/101/stories?library=family-a', body).json()
        self.assertEqual(first, again)
        body['text'] = 'Different retry'
        self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', body).status_code, 409)
        path = f"/stories/{first['id']}?library=family-a"
        edit = self.payload(revision='1')
        self.assertEqual(self.write('PUT', path, edit).status_code, 200)
        self.assertEqual(self.write('PUT', path, edit).json()['revision'], 2)
        stale = self.payload(revision='1')
        self.assertEqual(self.write('PUT', path, stale).status_code, 409)
        self.assertEqual(len(self.get('/assets/101/stories?library=family-a').json()['items']), 1)

    def test_permissions_and_parent_scope_on_every_operation(self):
        story = self.create()
        self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', self.payload(), self.member_token).status_code, 401)
        self.assertEqual(self.client.get('/assets/101/stories?library=family-a').status_code, 401)
        for asset in (103, 201, 999, 555):
            self.assertEqual(self.write('POST', f'/assets/{asset}/stories?library=family-a', self.payload()).status_code, 401)
        self.assertEqual(self.get('/assets/101/stories?library=family-a', self.other_token).status_code, 401)
        self.assertEqual(self.search('garden', token=self.other_token).status_code, 401)
        history = f"/stories/{story['id']}/history?library=family-a"
        self.assertEqual(self.get(history).status_code, 401)
        self.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?", (self.member_id,))
        own = self.create(token=self.member_token)
        self.assertTrue(own['can_edit'])
        self.assertEqual(self.write('PUT', f"/stories/{story['id']}?library=family-a", self.payload(revision='1'), self.member_token).status_code, 401)
        self.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        self.assertEqual(self.get(history, self.owner_token).status_code, 401)
        self.assertEqual(self.search('garden').json()['total'], 0)

    def test_cookie_csrf_and_bearer_transport(self):
        self.client.cookies.set(COOKIE, self.owner_token)
        path = '/assets/101/stories?library=family-a'
        self.assertEqual(self.client.post(path, json=self.payload()).status_code, 403)
        headers = {'Origin': 'https://photohouse.test', 'X-CSRF-Token': csrf_token(self.owner_token)}
        self.assertEqual(self.client.post(path, json=self.payload(), headers=headers).status_code, 201)
        self.assertEqual(self.client.post(path, json=self.payload(), headers={**headers, 'Origin': 'https://evil.test'}).status_code, 403)

    def test_delete_is_versioned_and_removed_from_search(self):
        story = self.create('UniqueDeleteStory')
        path = f"/stories/{story['id']}?library=family-a"
        body = dict(revision='1', mutation_id=str(uuid.uuid4()))
        self.assertEqual(self.write('DELETE', path, body).status_code, 200)
        self.assertEqual(self.write('DELETE', path, body).status_code, 200)
        self.assertEqual(self.search('UniqueDeleteStory').json()['total'], 0)
        self.assertEqual(self.get('/assets/101/stories?library=family-a').json()['items'], [])
        history = self.get(f"/stories/{story['id']}/history?library=family-a", self.owner_token).json()
        self.assertTrue(history['items'][0]['deleted'])
        self.assertEqual(history['items'][1]['text'], 'UniqueDeleteStory')

    def test_search_literal_short_chinese_filters_and_dedup(self):
        self.create('奶奶 100%_safe')
        self.create('奶奶 another contribution')
        self.mutate("UPDATE assets SET mime='video/mp4' WHERE id=101")
        self.assertEqual(self.search('奶').json()['total'], 1)
        self.assertEqual(self.search('100%_').json()['total'], 1)
        self.assertEqual(self.search('%').json()['total'], 1)
        self.assertEqual(self.search('奶', media='image').json()['total'], 0)
        self.assertEqual(self.search('奶', media='video').json()['total'], 1)
        self.assertEqual(self.search('奶', source='ai').json()['total'], 0)
        self.assertEqual(self.search('old-hidden').json()['total'], 0)
        self.assertEqual(self.search('caption-201').json()['total'], 0)
        self.assertEqual(self.search('caption-999').json()['total'], 0)
        self.assertEqual(self.search('caption-103').json()['total'], 0)
        self.assertNotIn('private-', self.search('caption').text)

    def test_body_validation_and_pagination(self):
        for text in (' ', '\x00', '回' * 23000):
            body = self.payload(); body['text'] = text
            self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', body).status_code, 422)
        body = self.payload(); body['author_id'] = self.member_id
        self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', body).status_code, 400)
        body = self.payload(); body['text'] = 'a' * (512*1024)
        self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', body).status_code, 413)
        for _ in range(6):
            self.create()
        self.assertTrue(self.get('/assets/101/stories?library=family-a').json()['has_more'])
        self.assertEqual(len(self.get('/assets/101/stories?library=family-a&page=2').json()['items']), 1)

    def test_maximum_escaped_stories_have_explicit_whole_page_wire_budgets(self):
        # Six bytes of JSON for each one-byte control character; no content filtering.
        text = '\x01' * (64 * 1024)
        body = self.payload(); body.update(text=text, title='t' * 512, byline='b' * 256)
        path = '/assets/101/stories?library=family-a'
        for _ in range(6):
            body['mutation_id'] = str(uuid.uuid4())
            response = self.write('POST', path, body)
            self.assertEqual(response.status_code, 201, response.text)
        first = self.get(path).json()
        self.assertEqual(len(first['items']), 5)
        self.assertTrue(first['has_more'])
        second = self.get(path + '&page=2').json()
        self.assertEqual(len(second['items']), 1)
        self.assertTrue(all(story['text'] == text for story in first['items'] + second['items']))
        story = first['items'][0]
        for revision in range(1, 6):
            body.update(revision=str(revision), mutation_id=str(uuid.uuid4()))
            self.assertEqual(self.write('PUT', f"/stories/{story['id']}?library=family-a", body).status_code, 200)
        history = self.get(f"/stories/{story['id']}/history?library=family-a", self.owner_token)
        self.assertEqual(len(history.json()['items']), 5)
        self.assertEqual(history.json()['story']['text'], text)
        self.assertTrue(all(row['text'] == text for row in history.json()['items']))
        self.assertLessEqual(len(history.content), 3 * 1024 * 1024)
        self.assertLessEqual(len(self.get(path).content), 3 * 1024 * 1024)
        self.assertEqual(self.get(path).headers['cache-control'], 'no-store')

    def test_old_exact_retry_returns_newer_current_content_without_rewriting_history(self):
        body = self.payload()
        story = self.write('POST', '/assets/101/stories?library=family-a', body).json()
        edit = self.payload(revision='1'); edit['text'] = 'Later current version'
        self.assertEqual(self.write('PUT', f"/stories/{story['id']}?library=family-a", edit).status_code, 200)
        retry = self.write('POST', '/assets/101/stories?library=family-a', body)
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(retry.json()['text'], edit['text'])
        self.assertEqual(retry.json()['revision'], 2)
        history = self.get(f"/stories/{story['id']}/history?library=family-a", self.owner_token).json()
        self.assertEqual(len(history['items']), 2)

    def test_history_failure_rolls_back_story_and_audit(self):
        self.mutate("""CREATE TRIGGER synthetic_history_failure BEFORE INSERT ON access_story_revisions
            BEGIN SELECT RAISE(ABORT, 'synthetic interruption'); END""")
        response = self.write('POST', '/assets/101/stories?library=family-a', self.payload())
        self.assertEqual(response.status_code, 503)
        with self.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_stories').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='story.create'").fetchone()[0], 0)

    def test_two_concurrent_writers_cannot_lose_an_update(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from app.access.stories import Stories
        from app.access.service import AccessService
        from app.access.transport import TransportError
        story = self.create()
        gate = Barrier(2)
        def save():
            gate.wait()
            with self.connection() as db:
                try:
                    Stories(AccessService(db, clock=lambda:self.now)).save(self.owner_token, 'family-a',
                        self.payload(revision='1'), story_id=story['id'])
                    return 200
                except TransportError as exc:
                    return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(save) for _ in range(2)]
            self.assertEqual(sorted(f.result() for f in futures), [200, 409])

    def test_revocation_blocks_story_reads_writes_history_search_and_replays(self):
        self.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?", (self.member_id,))
        body = self.payload()
        story = self.write('POST', '/assets/101/stories?library=family-a', body, self.member_token).json()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (self.member_id,))
        self.trace.clear()
        self.assertEqual(self.get('/assets/101/stories?library=family-a').status_code, 401)
        self.assertEqual(self.get(f"/stories/{story['id']}/history?library=family-a").status_code, 401)
        self.assertEqual(self.search('garden').status_code, 401)
        self.assertEqual(self.write('POST', '/assets/101/stories?library=family-a', body, self.member_token).status_code, 401)
        self.assertEqual(self.write('PUT', f"/stories/{story['id']}?library=family-a", self.payload(revision='1'), self.member_token).status_code, 401)
        self.assertFalse(any('FROM access_stories' in sql or 'FROM access_story_revisions' in sql for sql in self.trace))
