"""Translation and manifest tests."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from custom_components.edifier_ble.protocol import (
    DISTANCE_TO_OPTION,
    EQ_MODE_TO_OPTION,
    LIGHT_TIME_TO_OPTION,
    SOURCE_TO_OPTION,
)

BASE = Path(__file__).parent.parent / 'custom_components' / 'edifier_ble'
SELECT_OPTIONS = {
    'source': set(SOURCE_TO_OPTION.values()),
    'eq_mode': set(EQ_MODE_TO_OPTION.values()),
    'light_time': set(LIGHT_TIME_TO_OPTION.values()),
    'light_distance': set(DISTANCE_TO_OPTION.values()),
}


class TranslationTest(unittest.TestCase):
    """Validate translated select options and diagnostic entities."""

    def test_all_select_options_are_translated(self) -> None:
        """English and Chinese should translate every select option."""
        for translation in ('en.json', 'zh-Hans.json'):
            data = json.loads((BASE / 'translations' / translation).read_text())
            select = data['entity']['select']
            for key, options in SELECT_OPTIONS.items():
                self.assertEqual(set(select[key]['state']), options, translation)

    def test_diagnostic_entities_updated(self) -> None:
        """MAC and firmware sensors are gone; RSSI and status are present."""
        data = json.loads((BASE / 'translations' / 'en.json').read_text())
        entity = data['entity']
        self.assertNotIn('mac_address', entity['sensor'])
        self.assertNotIn('firmware_version', entity['sensor'])
        self.assertIn('rssi', entity['sensor'])
        self.assertIn('audio_mac_address', entity['sensor'])
        self.assertIn('connection_status', entity['binary_sensor'])

    def test_config_flow_translations_use_step_section(self) -> None:
        """Bluetooth confirmation must use the standard config.step section."""
        for translation in ('en.json', 'zh-Hans.json'):
            data = json.loads((BASE / 'translations' / translation).read_text())
            self.assertNotIn('flow', data['config'])
            self.assertIn('bluetooth_confirm', data['config']['step'])
            self.assertEqual(data['config']['flow_title'], '{name}')

    def test_manifest_has_no_upper_requirement_bound(self) -> None:
        """Requirements should follow the latest HA-compatible versions."""
        manifest = json.loads((BASE / 'manifest.json').read_text())
        requirements = manifest['requirements']
        self.assertTrue(requirements)
        self.assertTrue(all('<' not in requirement for requirement in requirements))


if __name__ == '__main__':
    unittest.main()
