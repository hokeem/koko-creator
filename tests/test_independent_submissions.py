import unittest
from unittest.mock import patch

import app


class IndependentSubmissionTests(unittest.TestCase):
    def test_batch_is_idempotent_and_pending(self):
        accounts = [{'account_id': 'creator-a', 'kwai_id': 'creator_a', 'registration_status': 'registered'}]
        rows = []
        with (patch.object(app, 'load_accounts', return_value=accounts),
              patch.object(app, 'read_record_list', return_value=rows),
              patch.object(app, 'write_json_atomic')):
            result = app.import_independent_submissions([
                {'account_id': 'creator-a', 'video_url': 'https://example.com/video/1'},
                {'account_id': 'creator-a', 'video_url': 'https://example.com/video/1'},
            ])
        self.assertEqual(len(result['created']), 1)
        self.assertEqual(len(result['duplicates']), 1)
        self.assertEqual(result['created'][0]['status'], 'pending_review')
        self.assertEqual(result['created'][0]['entry_id'], '')

    def test_invalid_batch_does_not_write(self):
        with (patch.object(app, 'load_accounts', return_value=[{'account_id': 'a', 'registration_status': 'registered'}]),
              patch.object(app, 'write_json_atomic') as write):
            with self.assertRaises(ValueError):
                app.import_independent_submissions([{'account_id': 'missing', 'video_url': 'https://example.com/video'}])
        write.assert_not_called()
