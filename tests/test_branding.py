"""Brand asset tests for Home Assistant 2026.3+ local branding."""

from __future__ import annotations

from pathlib import Path
import struct
import unittest

BRAND_DIR = (
    Path(__file__).parent.parent
    / 'custom_components'
    / 'edifier_ble'
    / 'brand'
)
EXPECTED_IMAGES = {
    'icon.png': (256, 256),
    'icon@2x.png': (512, 512),
    'logo.png': (588, 128),
    'logo@2x.png': (1176, 256),
    'dark_logo.png': (588, 128),
    'dark_logo@2x.png': (1176, 256),
}


class BrandingTest(unittest.TestCase):
    """Validate local brand images."""

    def test_brand_images_exist_with_required_dimensions(self) -> None:
        """PNG dimensions should follow the Home Assistant brands spec."""
        for filename, expected_size in EXPECTED_IMAGES.items():
            path = BRAND_DIR / filename
            self.assertTrue(path.is_file(), filename)
            data = path.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n', filename)
            width, height = struct.unpack('>II', data[16:24])
            self.assertEqual((width, height), expected_size, filename)


if __name__ == '__main__':
    unittest.main()
