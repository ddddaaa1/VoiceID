from __future__ import annotations

import re
import unittest
from pathlib import Path

from voiceid.domain.authorization import ProtectedAction

ROOT = Path(__file__).parents[1]
SDK = ROOT / "sdk/swift/VoiceIDKit"


class SwiftSdkContractTests(unittest.TestCase):
    def test_swift_action_catalog_matches_server_owned_catalog(self) -> None:
        models = (SDK / "Sources/VoiceIDKit/Models.swift").read_text(encoding="utf-8")
        action_enum = models.split("public enum ActionRisk", maxsplit=1)[0]
        swift_values = set(re.findall(r'case \w+ = "([a-z_]+)"', action_enum))

        self.assertEqual(swift_values, {action.value for action in ProtectedAction})

    def test_sdk_preserves_step_up_and_raw_audio_boundaries(self) -> None:
        coordinator = (SDK / "Sources/VoiceIDKit/AuthorizationCoordinator.swift").read_text(
            encoding="utf-8"
        )
        capture = (SDK / "Sources/VoiceIDKit/AudioCapture.swift").read_text(encoding="utf-8")
        readme = (SDK / "README.md").read_text(encoding="utf-8")

        self.assertIn("case stepUpRequired(ActionAuthorization)", coordinator)
        self.assertNotIn("write(to:", capture)
        self.assertIn("not server-verifiable evidence", readme)
        self.assertIn("does not implement continuous listening", readme)


if __name__ == "__main__":
    unittest.main()
