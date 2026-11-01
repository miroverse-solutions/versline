import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from versline.services import media


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
class TestShortClip(unittest.TestCase):
    def test_short_clip_gets_one_chunk_and_video_audio_extracts(self):
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "tone.mp3"
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=duration=5", "-y", str(src)], capture_output=True, check=True)
        chunks = media.split_audio_with_ffmpeg(str(src), 900, 180, str(tmp / "chunks"))
        self.assertEqual(len(chunks), 1)

        mp4 = tmp / "clip.mp4"
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=duration=3", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3",
                        "-shortest", "-y", str(mp4)], capture_output=True, check=True)
        out = media.extract_audio(str(mp4), str(tmp / "clip.mp3"))
        self.assertTrue(Path(out).stat().st_size > 0)

    def test_video_input_splits_into_nonempty_readable_chunks(self):
        tmp = Path(tempfile.mkdtemp())
        mp4 = tmp / "clip.mp4"
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=duration=25", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=25",
                        "-shortest", "-c:v", "libx264", "-c:a", "aac", "-y", str(mp4)], capture_output=True, check=True)
        chunks = media.split_audio_with_ffmpeg(str(mp4), 12, 2, str(tmp / "chunks"))
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertGreater(Path(c).stat().st_size, 0)
            self.assertGreater(media.get_audio_duration(c), 0)

    def test_empty_cached_chunks_are_discarded(self):
        tmp = Path(tempfile.mkdtemp())
        empty = tmp / "chunk_000.mp3"
        empty.write_bytes(b"")
        self.assertEqual(media.usable_cached_chunks([empty]), [])
        self.assertFalse(empty.exists())


if __name__ == "__main__":
    unittest.main()
