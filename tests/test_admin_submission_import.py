import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("koko_creator_app", ROOT / "app.py")
APP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(APP)


def test_admin_submission_import_is_idempotent_and_preserves_return_time(tmp_path, monkeypatch):
    submissions_file = tmp_path / "creator_submissions.json"
    monkeypatch.setattr(APP, "SUBMISSIONS_FILE", submissions_file)
    monkeypatch.setattr(
        APP,
        "entry_by_id",
        lambda entry_id: {
            "entry_id": entry_id,
            "title": "Roteiro",
            "content_type": "剧情演绎",
        },
    )
    monkeypatch.setattr(
        APP,
        "load_creator_profiles",
        lambda: [
            {
                "profile_id": "a" * 32,
                "account_id": "creator01",
                "name": "Creator One",
                "kwai_id": "creator_one",
            }
        ],
    )
    payload = {
        "entry_id": "b" * 32,
        "video_url": "https://www.kwai.com/@creator_one/video/123",
        "creator_profile_id": "a" * 32,
        "created_at": "2026-09-20",
        "source": "test_batch",
    }

    first, first_created = APP.import_admin_submission(payload)
    second, second_created = APP.import_admin_submission(payload)

    assert first_created is True
    assert second_created is False
    assert first["created_at"] == "2026-09-20"
    assert second["creator_profile_id"] == "a" * 32
    assert len(APP.read_json_file(submissions_file, [])) == 1
