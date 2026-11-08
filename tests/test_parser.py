import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parser.screenplay_parser import parse_directory, timestamp_to_seconds

SAMPLES = ROOT / "data" / "samples"

class ParserTests(unittest.TestCase):
    def test_timestamp_conversion(self):
        self.assertEqual(timestamp_to_seconds("00:54.50"), 54.5)
        self.assertEqual(timestamp_to_seconds("02:18.00"), 138.0)

    def test_all_six_samples(self):
        result = parse_directory(SAMPLES)
        self.assertEqual(result["episode_count"], 6)
        self.assertEqual(result["scene_count"], 9)
        self.assertEqual(result["event_count"], 556)
        self.assertTrue(result["run_validation"]["all_episodes_valid"])

    def test_overlapping_events_are_preserved(self):
        result = parse_directory(SAMPLES)
        ep5 = next(e for e in result["episodes"] if e["episode_id"] == "Episode 5")
        scene = ep5["scenes"][0]
        self.assertGreater(len(scene["events"]), 1)
        # Events are separate tracks and are not merged or summed into clip duration.
        self.assertTrue(any(e["event_type"] == "CAMERA" for e in scene["events"]))
        self.assertTrue(any(e["event_type"] == "ACTION" for e in scene["events"]))

if __name__ == "__main__":
    unittest.main()
