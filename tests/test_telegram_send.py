import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from versline.services import telegram_send as ts
from versline.services.channel_archive.sources.telegram import SendError
from versline.services.telegram_people import (
    classify, normalize_phone, parse_recipients, phone_key, read_recipients, write_rows,
)


def user(uid, first, last="", username=None, phone=None, contact=True):
    return SimpleNamespace(id=uid, first_name=first, last_name=last or None, username=username, phone=phone,
                           contact=contact, mutual_contact=True, bot=False)


def row_of(u):
    return {"id": u.id, "name": " ".join(filter(None, [u.first_name, u.last_name])), "first_name": u.first_name,
            "last_name": u.last_name or "", "username": u.username or "", "phone": f"+{u.phone}" if u.phone else "",
            "type": "user"}


class FakeSource:
    def __init__(self, users, fail=None):
        self.users = users
        self.sent = []  # (entity id, text, file)
        self.forwarded = []
        self.fail = fail or {}  # entity id -> list of SendErrors to raise in order
        self.uploads = 0

    def list_contacts(self, search=None, mutual_only=False, with_entity=False):
        return [{**row_of(u), "entity": u} for u in self.users if u.contact]

    def iter_dialogs(self, **kw):
        return [{**row_of(u), "title": row_of(u)["name"], "kind": "user", "entity": u} for u in self.users]

    def entity_of(self, ref):
        for u in self.users:
            if ref in (u.id, u.username, "me"):
                return u
        raise ValueError("no such user")

    def send(self, entity, text, parse_mode=None, file=None, link_preview=True):
        queue = self.fail.get(entity.id)
        if queue:
            raise queue.pop(0)
        if file is not None and file != "MEDIA":
            self.uploads += 1
        self.sent.append((entity.id, text, file))
        return {"id": len(self.sent), "media": "MEDIA" if file else None}

    def forward(self, entity, from_entity, ids, drop_author=False, drop_captions=False):
        self.forwarded.append((entity.id, from_entity, ids, drop_author))
        return [100 + i for i in ids]


USERS = [user(1, "علی", "رضایی", "ali_r", "989121234567"), user(2, "Sara", "K", "sara_k", "989351111111"),
         user(3, "Sara", "K", None, None), user(4, "Nobody", username="nobody_x", contact=False)]


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class TestRecipients(unittest.TestCase):
    def test_phone_normalisation(self):
        self.assertEqual(phone_key("0912 123 4567"), phone_key("+98 912 123 4567"))
        self.assertEqual(phone_key("۰۹۱۲۱۲۳۴۵۶۷"), phone_key("+989121234567"))
        self.assertEqual(normalize_phone("00989121234567"), "+989121234567")

    def test_classify(self):
        self.assertEqual(classify("@ali"), "username")
        self.assertEqual(classify("https://t.me/ali_r"), "username")
        self.assertEqual(classify("09121234567"), "phone")
        self.assertEqual(classify("+989121234567"), "phone")
        self.assertEqual(classify("-1001234567890"), "id")
        self.assertEqual(classify("123456789"), "id")
        self.assertEqual(classify("علی رضایی"), "name")

    def test_csv_with_persian_headers_and_extra_columns(self):
        text = "نام,شماره,شهر\nعلی,0912 123 4567,تهران\nسارا,@sara,شیراز\n"
        people = parse_recipients(text, ".csv")
        self.assertEqual([(p.kind, p.ref) for p in people], [("phone", "0912 123 4567"), ("username", "sara")])
        self.assertEqual(people[0].fields["شهر"], "تهران")
        self.assertEqual(people[0].name, "علی")

    def test_id_column_wins_and_bom(self):
        people = parse_recipients("﻿id,name,username,phone\n5,Ali,ali,+98912\n", ".csv")
        self.assertEqual((people[0].kind, people[0].ref), ("id", "5"))

    def test_headerless_contacts_export_is_not_mistaken_for_a_header(self):
        text = "\ufeff523808197,محمد,M_Moqadam,+989303493683,user,2026-11-20 11:59,0,False\r\n2038267875,دفتر,ens_admin,+989022751111,user,2026-10-31 16:35,0,False\r\n"
        people = parse_recipients(text, ".csv")
        self.assertEqual([(p.kind, p.ref) for p in people], [("id", "523808197"), ("id", "2038267875")])

    def test_markdown_table_bullets_and_lines(self):
        table = "| name | username |\n| --- | --- |\n| Ali | @ali |\n| Sara | @sara |\n"
        self.assertEqual([p.ref for p in parse_recipients(table, ".md")], ["ali", "sara"])
        bullets = "# List\n- @ali\n- 09121234567\n* علی رضایی\n"
        self.assertEqual([(p.kind, p.ref) for p in parse_recipients(bullets, ".md")],
                         [("username", "ali"), ("phone", "09121234567"), ("name", "علی رضایی")])
        self.assertEqual([p.ref for p in parse_recipients("@a_user\n@b_user\n", ".txt")], ["a_user", "b_user"])

    def test_headerless_csv_and_column_option(self):
        self.assertEqual([p.ref for p in parse_recipients("@ali_r\n@sara_k\n", ".csv")], ["ali_r", "sara_k"])
        people = parse_recipients("who,contact\nAli,@ali\n", ".csv", column="contact")
        self.assertEqual((people[0].kind, people[0].ref), ("username", "@ali"))
        with self.assertRaises(ValueError):
            parse_recipients("a,b\n1,2\n", ".csv", column="zzz")

    def test_written_list_reads_back(self):
        rows = [row_of(u) for u in USERS[:2]]
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in (".csv", ".md"):
                path = write_rows(rows, Path(tmp) / f"contacts{suffix}")
                people = read_recipients(path)
                self.assertEqual([(p.kind, p.ref) for p in people], [("id", "1"), ("id", "2")])
                self.assertEqual(people[0].name, "علی رضایی")
            self.assertTrue(write_rows(rows, Path(tmp) / "c.json").read_text(encoding="utf-8").startswith("["))
            with self.assertRaises(ValueError):
                write_rows(rows, Path(tmp) / "c.xlsx")


class TestResolve(unittest.TestCase):
    def test_resolution_and_skip_reasons(self):
        people = parse_recipients("phone\n09121234567\n09999999999\n", ".csv")
        people += parse_recipients("@sara_k\n@nobody_x\n@ghost_zz\nعلی رضایی\nSara K\n", ".txt")
        resolved, skipped = ts.resolve_recipients(FakeSource(USERS), people, sleep=lambda s: None)
        self.assertEqual([r.entity_id for r in resolved], [1, 2, 4])
        reasons = {r.ref: reason for r, reason in skipped}
        self.assertIn("not among your contacts", reasons["09999999999"])
        self.assertIn("not found", reasons["ghost_zz"])
        self.assertIn("duplicate", reasons["علی رضایی"])
        self.assertIn("several", reasons["Sara K"])

    def test_phone_only_list_does_not_read_dialogs(self):
        source = FakeSource(USERS)
        source.iter_dialogs = lambda **kw: self.fail("dialogs not needed")
        resolved, _ = ts.resolve_recipients(source, parse_recipients("phone\n09351111111\n", ".csv"))
        self.assertEqual(resolved[0].entity_id, 2)


    def test_dialogs_read_only_when_contacts_cannot_answer(self):
        source = FakeSource(USERS)
        calls = []
        original = source.iter_dialogs
        source.iter_dialogs = lambda **kw: calls.append(1) or original(**kw)
        people = parse_recipients("id\n1\n2\n", ".csv") + parse_recipients("@sara_k\n", ".txt")
        resolved, _ = ts.resolve_recipients(source, people)
        self.assertEqual((len(resolved), calls), (2, []))
        resolved, _ = ts.resolve_recipients(source, parse_recipients("@nobody_x\n", ".txt"))
        self.assertEqual((resolved[0].entity_id, calls), (4, [1]))


class TestMessage(unittest.TestCase):
    def test_placeholders(self):
        values = {"name": "علی", "city": "تهران"}
        self.assertEqual(ts.render("سلام {name} از {City} {unknown} {}", values), "سلام علی از تهران {unknown} {}")
        self.assertEqual(ts.render("{name}", {"name": "a<b"}, "html"), "a&lt;b")

    def test_forward_refs(self):
        p = ts.parse_forward_ref
        self.assertEqual((p("https://t.me/chan/55").chat, p("https://t.me/chan/55").msg_id), ("chan", 55))
        ref = p("https://t.me/c/123/9?single")
        self.assertEqual((ref.chat, ref.msg_id, ref.single), (-100123, 9, True))
        self.assertEqual(p("t.me/c/123/4/9").msg_id, 9)
        self.assertEqual((p("me:last").chat, p("me:last").msg_id), ("me", None))
        self.assertEqual((p("-1001234:7").chat, p("-1001234:7").msg_id), ("-1001234", 7))
        with self.assertRaises(ValueError):
            p("nonsense")


class TestPacer(unittest.TestCase):
    def test_batch_pause_and_estimate(self):
        pacer = ts.Pacer((10, 20), batch_size=3, batch_pause=100, rng=random.Random(1))
        waits = [pacer.next_wait(n) for n in range(1, 7)]
        self.assertEqual([w[1] for w in waits], ["next message", "next message", "batch pause"] * 2)
        self.assertTrue(all(10 <= w[0] <= 20 for w in waits if w[1] == "next message"))
        self.assertTrue(all(80 <= w[0] <= 120 for w in waits if w[1] == "batch pause"))
        self.assertAlmostEqual(pacer.estimate(7), 4 * 15 + 2 * 100)

    def test_daily_block(self):
        pacer = ts.Pacer(daily_limit=3)
        now = 10 * ts.DAY
        self.assertIsNone(pacer.daily_block([now - 5], now))
        times = [now - 3000, now - 2000, now - 1000, now - 2 * ts.DAY]
        self.assertEqual(pacer.daily_block(times, now), now - 3000 + ts.DAY)
        self.assertIsNone(ts.Pacer(daily_limit=0).daily_block(times, now))


def make_sender(tmp, source, payload=None, pacer=None, **kw):
    clock = FakeClock()
    payload = payload or ts.Payload(text="سلام {name}")
    state = ts.SendState(Path(tmp) / "state.json", "k")
    history = ts.SendHistory(Path(tmp) / "history.json")
    pacer = pacer or ts.Pacer((10, 10), batch_size=2, batch_pause=100, daily_limit=100, rng=random.Random(0))
    sender = ts.BulkSender(source, payload, pacer, state, history, sleep=clock.sleep, now=clock.now, rng=random.Random(0), **kw)
    return sender, state, history, clock


def resolved_for(source, refs):
    people = parse_recipients("\n".join(refs), ".txt")
    resolved, _ = ts.resolve_recipients(source, people, sleep=lambda s: None)
    return resolved


class TestBulkSender(unittest.TestCase):
    def test_sends_paced_with_personalised_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS)
            sender, state, history, clock = make_sender(tmp, source)
            summary = sender.run(resolved_for(source, ["@ali_r", "@sara_k", "@nobody_x"]))
            self.assertEqual((summary.sent, summary.failed), (3, 0))
            self.assertEqual([s[1] for s in source.sent], ["سلام علی رضایی", "سلام Sara K", "سلام Nobody"])
            # a 10 s delay after #1, the 100 s batch pause (±20%) after #2, none after the last one
            waited = sum(clock.slept)
            self.assertGreater(waited, 10 + 80)
            self.assertLess(waited, 10 + 120 + 2)
            self.assertEqual(len(history.times), 3)

    def test_resume_skips_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS)
            sender, state, *_ = make_sender(tmp, source)
            items = resolved_for(source, ["@ali_r", "@sara_k"])
            sender.run(items[:1])
            sender2, *_ = make_sender(tmp, source)
            summary = sender2.run(items)
            self.assertEqual((summary.already_sent, summary.sent), (1, 1))
            self.assertEqual(len(source.sent), 2)

    def test_flood_wait_is_waited_then_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS, fail={1: [SendError("flood", "x", 30)]})
            sender, _, _, clock = make_sender(tmp, source)
            summary = sender.run(resolved_for(source, ["@ali_r"]))
            self.assertEqual(summary.sent, 1)
            self.assertGreaterEqual(sum(clock.slept), 30)

    def test_long_flood_wait_and_peer_flood_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS, fail={1: [SendError("flood", "x", 7200)]})
            sender, *_ = make_sender(tmp, source, )
            summary = sender.run(resolved_for(source, ["@ali_r", "@sara_k"]))
            self.assertEqual((summary.sent, bool(summary.stopped)), (0, True))
            source = FakeSource(USERS, fail={1: [SendError("peer_flood", "limited")]})
            sender, *_ = make_sender(tmp, source)
            summary = sender.run(resolved_for(source, ["@ali_r", "@sara_k"]))
            self.assertEqual((summary.sent, "limited" in summary.stopped), (0, True))
            self.assertEqual(source.sent, [])

    def test_per_user_failure_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS, fail={1: [SendError("failed", "UserIsBlockedError")]})
            sender, state, *_ = make_sender(tmp, source)
            summary = sender.run(resolved_for(source, ["@ali_r", "@sara_k"]))
            self.assertEqual((summary.sent, summary.failed), (1, 1))
            self.assertEqual(state.recipients["username:ali_r"]["status"], "failed")

    def test_daily_limit_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS)
            pacer = ts.Pacer((0, 0), batch_size=0, daily_limit=1)
            sender, *_ = make_sender(tmp, source, pacer=pacer)
            summary = sender.run(resolved_for(source, ["@ali_r", "@sara_k"]))
            self.assertEqual(summary.sent, 1)
            self.assertIn("daily limit", summary.stopped)

    def test_attachment_uploaded_once_and_long_text_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.pdf"
            f.write_bytes(b"x")
            source = FakeSource(USERS)
            sender, *_ = make_sender(tmp, source, payload=ts.Payload(text="cap {name}", file=f))
            sender.run(resolved_for(source, ["@ali_r", "@sara_k"]))
            self.assertEqual(source.uploads, 1)
            self.assertEqual(source.sent[1][2], "MEDIA")
            long = "بند\n\n" * 1500
            source = FakeSource(USERS)
            (Path(tmp) / "second").mkdir()
            sender, *_ = make_sender(Path(tmp) / "second", source, payload=ts.Payload(text=long, file=f))
            sender.run(resolved_for(source, ["@ali_r"]))
            self.assertIsNone(source.sent[0][1])  # file first, without a caption
            self.assertGreater(len(source.sent), 2)

    def test_forward_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = FakeSource(USERS)
            payload = ts.Payload(text="نگاه کن {name}", forwards=[("CHAN", [5, 6])], hide_source=True)
            sender, *_ = make_sender(tmp, source, payload=payload)
            sender.run(resolved_for(source, ["@ali_r"]))
            self.assertEqual(source.sent[0][1], "نگاه کن علی رضایی")
            self.assertEqual(source.forwarded, [(1, "CHAN", [5, 6], True)])

    def test_prepare_forwards_expands_albums_and_rejects_missing(self):
        msgs = {5: SimpleNamespace(id=5, grouped_id=9), 6: SimpleNamespace(id=6, grouped_id=9), 7: SimpleNamespace(id=7, grouped_id=None)}

        class Src:
            def entity_of(self, ref):
                return "ENT"

            def get_messages(self, entity, ids):
                return [msgs[i] for i in ids if i in msgs]

            def album_of(self, entity, m):
                return [x for x in msgs.values() if x.grouped_id == m.grouped_id] if m.grouped_id else [m]

        refs = [ts.parse_forward_ref("t.me/c/1/5"), ts.parse_forward_ref("t.me/c/1/7")]
        self.assertEqual(ts.prepare_forwards(Src(), refs), [("ENT", [5, 6, 7])])
        self.assertEqual(ts.prepare_forwards(Src(), [ts.parse_forward_ref("t.me/c/1/5?single")])[0][1], [5])
        with self.assertRaises(ValueError):
            ts.prepare_forwards(Src(), [ts.parse_forward_ref("t.me/c/1/99")])

    def test_payload_key_changes_with_message(self):
        self.assertNotEqual(ts.payload_key(ts.Payload(text="a"), []), ts.payload_key(ts.Payload(text="b"), []))


class CliSource(FakeSource):
    def close(self):
        pass

    def set_flood_sleep_threshold(self, seconds):
        pass

    def iter_dialogs(self, search=None, limit=None, kinds=None, unread_only=False, archived=None, with_entity=False,
                     since=None, until=None):
        self.date_args = (since, until)
        self.limit_arg = limit
        rows = super().iter_dialogs()
        return [{**r, "type": "user", "last_message": "2026-03-01 10:00"} for r in rows]

    def list_contacts(self, search=None, mutual_only=False, with_entity=False):
        return [{**r, "mutual": True} for r in super().list_contacts()]


class TestSendCli(unittest.TestCase):
    def run_cli(self, args, source=None, tmp=None):
        from unittest import mock

        from typer.testing import CliRunner

        from versline.commands import telegram as tg

        source = source or CliSource(USERS)
        with mock.patch.object(tg, "_make_source", return_value=source), \
                mock.patch("versline.userconfig.user_config_dir", return_value=Path(tmp)):
            return CliRunner().invoke(tg.app, args), source

    def test_send_end_to_end_resume_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "people.csv"
            lst.write_text("name,phone,city\nعلی,09121234567,تهران\nسارا,0935 111 1111,شیراز\nغایب,09990000000,x\n", encoding="utf-8")
            args = ["send", str(lst), "-m", "سلام **{name}** از {city}", "--delay", "0-0", "--batch-pause", "0", "--yes"]
            res, source = self.run_cli(args, tmp=tmp)
            self.assertEqual(res.exit_code, 0, res.output)
            self.assertEqual([x[1] for x in source.sent], ["سلام **علی رضایی** از تهران", "سلام **Sara K** از شیراز"])
            self.assertIn("not among your contacts", res.output)
            report = (Path(tmp) / "people.csv.send-report.csv").read_text(encoding="utf-8-sig")
            self.assertIn("skipped", report)
            res, source = self.run_cli(args, tmp=tmp)  # rerun: everyone is done
            self.assertIn("Nothing left to send", res.output)
            self.assertEqual(source.sent, [])

    def test_dry_run_and_test_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "p.txt"
            lst.write_text("@ali_r\n@sara_k\n", encoding="utf-8")
            res, source = self.run_cli(["send", str(lst), "-m", "hi ||x|| {name}", "--dry-run"], tmp=tmp)
            self.assertEqual(res.exit_code, 0, res.output)
            self.assertIn("formatting: spoiler", res.output)
            self.assertEqual(source.sent, [])
            res, source = self.run_cli(["send", str(lst), "-m", "hi {name}", "--test"], tmp=tmp)
            self.assertEqual((res.exit_code, [x[1] for x in source.sent]), (0, ["hi علی رضایی"]))
            self.assertFalse((Path(tmp) / "p.txt.send-state.json").exists())

    def test_argument_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            lst = Path(tmp) / "p.txt"
            lst.write_text("@ali_r\n", encoding="utf-8")
            f = Path(tmp) / "f.pdf"
            f.write_bytes(b"x")
            for args in (["send", str(lst)], ["send", str(lst), "-m", "x", "--delay", "a-b"],
                         ["send", str(lst), "-m", "x", "--format", "rtf"],
                         ["send", str(lst), "--forward", "me:last", "--attach", str(f)],
                         ["send", str(lst), "-m", "x", "--forward", "nonsense"],
                         ["send", str(Path(tmp) / "missing.csv"), "-m", "x"]):
                res, _ = self.run_cli(args, tmp=tmp)
                self.assertNotEqual(res.exit_code, 0, args)

    def test_contacts_and_chats_write_lists_that_send_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "contacts.csv"
            res, _ = self.run_cli(["contacts", "-o", str(out)], tmp=tmp)
            self.assertEqual(res.exit_code, 0, res.output)
            header = out.read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertEqual(header, "id,name,username,phone,type,mutual")
            self.assertEqual(len(read_recipients(out)), 3)
            res, _ = self.run_cli(["chats", "--type", "user"], tmp=tmp)
            self.assertIn("علی رضایی", res.output)
            res, _ = self.run_cli(["chats", "--type", "alien"], tmp=tmp)
            self.assertNotEqual(res.exit_code, 0)
            res, source = self.run_cli(["chats", "--since", "1404-07-01", "--until", "2026-03-31", "-o", str(Path(tmp) / "c.csv")], tmp=tmp)
            self.assertEqual(res.exit_code, 0, res.output)
            since, until = source.date_args
            self.assertEqual((since.date().isoformat(), until.date().isoformat()), ("2025-09-23", "2026-03-31"))
            self.assertIn("last_message", (Path(tmp) / "c.csv").read_text(encoding="utf-8-sig").splitlines()[0])
            self.assertIsNone(source.limit_arg)  # a date range lists everything
            res, source = self.run_cli(["chats"], tmp=tmp)
            self.assertEqual(source.limit_arg, 50)
            res, source = self.run_cli(["chats", "-o", str(Path(tmp) / "d.csv")], tmp=tmp)
            self.assertIsNone(source.limit_arg)
            res, source = self.run_cli(["chats", "--since", "2026-01-01", "--limit", "7"], tmp=tmp)
            self.assertEqual(source.limit_arg, 7)
            res, _ = self.run_cli(["chats", "--since", "2026-05-01", "--until", "2026-03-01"], tmp=tmp)
            self.assertNotEqual(res.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
