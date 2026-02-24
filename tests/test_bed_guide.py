import unittest

from main import (
    build_bed_guide_steps,
    detect_natural_bed_intent,
    render_bed_guide_step,
    resolve_bed_guide_shortcut_intent,
)


class TestBedGuide(unittest.TestCase):
    def test_detect_bed_guide_start_intent(self):
        intent, _ = detect_natural_bed_intent("how to use this bed")
        self.assertEqual(intent, "bed_guide_start")

    def test_detect_bed_guide_next_intent(self):
        intent, _ = detect_natural_bed_intent("next guide step")
        self.assertEqual(intent, "bed_guide_next")

    def test_render_bed_guide_step_has_progress(self):
        text = render_bed_guide_step(0)
        self.assertIn("Bed guide 1/", text)
        self.assertIn("next guide step", text)

    def test_render_bed_guide_completion_message(self):
        done = render_bed_guide_step(len(build_bed_guide_steps()))
        self.assertIn("Bed guide completed", done)

    def test_bed_guide_shortcut_next(self):
        self.assertEqual(resolve_bed_guide_shortcut_intent("next"), "bed_guide_next")

    def test_bed_guide_shortcut_next_step_phrase(self):
        self.assertEqual(resolve_bed_guide_shortcut_intent("next step"), "bed_guide_next")

    def test_bed_guide_shortcut_repeat_arabic(self):
        self.assertEqual(resolve_bed_guide_shortcut_intent("كرر"), "bed_guide_repeat")

    def test_bed_guide_shortcut_stop(self):
        self.assertEqual(resolve_bed_guide_shortcut_intent("stop"), "bed_guide_stop")


if __name__ == "__main__":
    unittest.main()
