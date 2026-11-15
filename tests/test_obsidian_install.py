"""Installing/updating the Versobs plugin into a vault (GitHub calls stubbed)."""
import json
from pathlib import Path

import pytest

from versline.services import obsidian_plugin, releases
from versline.services.obsidian_plugin import PluginInstallError, install_plugin, installed_version, known_vaults


def make_release(monkeypatch, version="1.2.0", plugin_id="versobs", assets=("manifest.json", "main.js", "styles.css")):
    files = {
        "manifest.json": json.dumps({"id": plugin_id, "version": version}),
        "main.js": f"// main {version}",
        "styles.css": "/* css */",
    }

    def fetch_release(repo, tag=None, timeout=15.0, proxy=None):
        assert repo == obsidian_plugin.PLUGIN_REPO
        return {"tag": f"v{version}", "assets": {n: f"https://example/{n}" for n in assets}, "url": "https://example"}

    def download(url, dest, timeout=60.0, proxy=None):
        Path(dest).write_text(files[url.rsplit("/", 1)[-1]], encoding="utf-8")
        return Path(dest)

    monkeypatch.setattr(releases, "fetch_release", fetch_release)
    monkeypatch.setattr(releases, "download", download)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "Vault" / ".obsidian").mkdir(parents=True)
    return tmp_path / "Vault"


def test_install_update_and_up_to_date(vault, monkeypatch):
    make_release(monkeypatch, "1.0.0")
    result = install_plugin(vault)
    target = vault / ".obsidian" / "plugins" / "versobs"
    assert result.status == "installed" and result.version == "1.0.0"
    assert (target / "main.js").read_text() == "// main 1.0.0"
    (target / "data.json").write_text('{"keep": true}')

    assert install_plugin(vault).status == "up-to-date"

    make_release(monkeypatch, "1.2.0")
    result = install_plugin(vault)
    assert result.status == "updated" and result.previous == "1.0.0"
    assert installed_version(vault) == "1.2.0"
    assert json.loads((target / "data.json").read_text()) == {"keep": True}
    assert not list(target.parent.glob(".versobs-*")), "staging folder left behind"


def test_rejects_non_vault_and_wrong_manifest(tmp_path, vault, monkeypatch):
    make_release(monkeypatch)
    with pytest.raises(PluginInstallError):
        install_plugin(tmp_path / "not-a-vault")
    make_release(monkeypatch, plugin_id="other")
    with pytest.raises(PluginInstallError):
        install_plugin(vault)
    assert installed_version(vault) is None


def test_release_without_main_js_is_refused(vault, monkeypatch):
    make_release(monkeypatch, assets=("manifest.json",))
    with pytest.raises(PluginInstallError):
        install_plugin(vault)


def test_known_vaults_reads_obsidian_json(tmp_path, vault, monkeypatch):
    config = tmp_path / "obsidian.json"
    config.write_text(json.dumps({"vaults": {
        "a": {"path": str(vault), "ts": 2, "open": True},
        "b": {"path": str(tmp_path / "gone"), "ts": 5},
    }}))
    monkeypatch.setattr(obsidian_plugin, "obsidian_config_candidates", lambda: [config])
    rows = known_vaults()
    assert [r["name"] for r in rows] == ["Vault", "gone"]
    assert rows[0]["exists"] and not rows[1]["exists"]
    assert obsidian_plugin.resolve_vault(None) == vault


def test_version_tuple():
    assert releases.version_tuple("v1.10.0") > releases.version_tuple("1.9.9")
    assert releases.is_newer("1.0.1", "1.0.0") and not releases.is_newer(None, "1.0.0")
