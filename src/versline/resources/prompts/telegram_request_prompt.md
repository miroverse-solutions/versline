# Classify a request about a recorded talk

A listener replied to a recorded talk (a lecture, podcast, lesson or meeting) with the request below. Decide what they want:

* `taqrir`: a write-up of the whole talk (or of a large part of it), e.g. "تقریر کن", "کلش رو بنویس", "خلاصه‌ی مفصل", "پیاده کن"
* `find`: specific things said in it, e.g. a point, a quotation, a narration, a verse, an example, "the two points about…", "اون روایتی که از امام صادق خوند", "کجا گفت که…"

Request:

"""
{request}
"""

Output ONLY JSON, with no code fence or commentary:

{{"mode": "taqrir" or "find", "query": "for find: what to look for, restated clearly and completely in the request's language; otherwise empty", "instruction": "for taqrir: any focus or guidance the listener gave; otherwise empty"}}
