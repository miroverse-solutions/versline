import unittest

from versline.services.telegram_format import parse, split_message


def spans(text, entities):
    raw = text.encode("utf-16-le")
    return [(type(e).__name__.replace("MessageEntity", ""), raw[e.offset * 2:(e.offset + e.length) * 2].decode("utf-16-le"))
            for e in entities]


class TestFormat(unittest.TestCase):
    def test_inline_entities_with_persian_and_emoji_offsets(self):
        text, ents = parse("سلام 🙂 **علی** و *ایتالیک* و __زیر__ و ~~خط~~ و ||راز|| و `کد`")
        self.assertEqual(spans(text, ents), [("Bold", "علی"), ("Italic", "ایتالیک"), ("Underline", "زیر"),
                                             ("Strike", "خط"), ("Spoiler", "راز"), ("Code", "کد")])

    def test_links_mentions_and_custom_emoji(self):
        text, ents = parse("[سایت](https://a.com/x?a=1&b=2) و https://t.me/foo. ![🙂](emoji:5368324170671202286)")
        kinds = spans(text, ents)
        self.assertIn(("TextUrl", "سایت"), kinds)
        self.assertIn(("TextUrl", "https://t.me/foo"), kinds)
        self.assertEqual(ents[0].url, "https://a.com/x?a=1&b=2")
        emoji = [e for e in ents if type(e).__name__ == "MessageEntityCustomEmoji"][0]
        self.assertEqual(emoji.document_id, 5368324170671202286)

    def test_code_block_is_not_formatted(self):
        text, ents = parse("```py\nx = **a**\n```")
        self.assertEqual(text, "x = **a**")
        self.assertEqual([type(e).__name__ for e in ents], ["MessageEntityPre"])
        self.assertEqual(ents[0].language, "py")

    def test_quotes_headings_and_lists(self):
        text, ents = parse("# عنوان\n- یک\n* دو\n> نقل\n>! جمع‌شونده")
        self.assertEqual(text.splitlines()[:3], ["عنوان", "• یک", "• دو"])
        quotes = [e for e in ents if type(e).__name__ == "MessageEntityBlockquote"]
        self.assertEqual([bool(q.collapsed) for q in quotes], [False, True])
        self.assertEqual(spans(text, ents)[0], ("Bold", "عنوان"))

    def test_tables(self):
        md = "| نام | سن |\n| --- | --- |\n| علی | 20 |"
        text, ents = parse(md, tables="pre")
        self.assertEqual([type(e).__name__ for e in ents], ["MessageEntityPre"])
        self.assertIn("علی", text)
        text, ents = parse(md, tables="list")
        self.assertEqual(text, "نام: علی\nسن: 20")

    def test_plain_and_html(self):
        self.assertEqual(parse("**x**", "plain"), ("**x**", []))
        text, ents = parse("<b>x</b> & y", "html")
        self.assertEqual((text, spans(text, ents)), ("x & y", [("Bold", "x")]))
        with self.assertRaises(ValueError):
            parse("x", "rtf")

    def test_ampersand_and_angle_brackets_are_escaped(self):
        text, ents = parse("a < b & c > d")
        self.assertEqual((text, ents), ("a < b & c > d", []))

    def test_split_message(self):
        parts = split_message("\n\n".join(["بند " * 300] * 10), 4096)
        self.assertTrue(all(len(p) <= 4096 for p in parts))
        self.assertGreater(len(parts), 1)
        code = "```\n" + "x\n\n" * 3000 + "```"
        self.assertEqual(len(split_message(code[:100])), 1)
        self.assertEqual(split_message("short"), ["short"])


if __name__ == "__main__":
    unittest.main()
