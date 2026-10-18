from versline.utils.common import align_words_to_good_text


def _words(text, step=0.5):
    return [{"word": w, "start": i * step, "end": i * step + step * 0.8} for i, w in enumerate(text.split())]


def test_formal_text_aligned_to_colloquial_words_cuts_on_word_boundaries():
    stt = "اون شب انقدر خوشحال بودم واقعا نمی‌تونستم بخوابم ولی این خوب نیست اشکالی نداره آدم یه بار اینجوری بشه"
    good = "آن شب آن‌قدر خوشحال بودم، واقعاً نمی‌توانستم بخوابم. ولی این خوب نیست. اشکالی ندارد آدم یک بار این‌طوری بشود."
    segs = align_words_to_good_text(good, _words(stt), min_len=1.0)
    assert [s["text"] for s in segs] == [
        "آن شب آن‌قدر خوشحال بودم، واقعاً نمی‌توانستم بخوابم.",
        "ولی این خوب نیست.",
        "اشکالی ندارد آدم یک بار این‌طوری بشود.",
    ]
    assert segs[0]["start"] == 0.0
    assert segs[1]["start"] == 4.0
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(segs, segs[1:]))


def test_unspoken_text_is_kept_and_interpolated():
    good = "**گوینده اول:** سلام به همه. [نامفهوم] خداحافظ."
    segs = align_words_to_good_text(good, _words("سلام به همه خداحافظ"), min_len=0.5)
    assert " ".join(s["text"] for s in segs) == good
    assert segs[-1]["text"].endswith("خداحافظ.")


def test_empty_inputs():
    assert align_words_to_good_text("", _words("a b")) == []
    assert align_words_to_good_text("متن", []) == []
