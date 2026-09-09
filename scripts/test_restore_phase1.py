"""Safety and integrity checks for the external archive restore helper."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
import restore_phase1 as restore


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = dict(source_workspace=str(self.root / 'protected'),
                             restore_order=[], archives=[])

    def archive(self, name, content):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as z:
            for key, value in content.items():
                z.writestr(key, value)
        self.manifest['restore_order'].append(name)
        self.manifest['archives'].append(dict(name=name, bytes=path.stat().st_size,
                                             sha256=restore.sha(path)))
        return path

    def test_ordered_overlay_and_completion(self):
        self.archive('first.zip', {'data/value.json': 'old', 'src/a.c': 'source'})
        self.archive('second.zip', {'data/value.json': 'new'})
        checked = restore.verify_archives(self.root, self.manifest)
        dest = restore.validate_destination(self.root / 'output', self.manifest)
        state = restore.restore(self.root, dest, self.manifest, checked)
        self.assertTrue(state['complete'])
        self.assertEqual((dest / 'data/value.json').read_text(), 'new')
        self.assertEqual((dest / 'src/a.c').read_text(), 'source')
        with self.assertRaises(ValueError):
            restore.validate_destination(dest, self.manifest)

    def test_missing_archive(self):
        path = self.archive('a.zip', {'a': 'x'})
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            restore.verify_archives(self.root, self.manifest)

    def test_same_size_corruption(self):
        path = self.archive('a.zip', {'a': 'x'})
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            restore.verify_archives(self.root, self.manifest)

    def test_unsafe_members(self):
        for name in ['../escape', '/absolute', 'a/../../escape', 'a\\b',
                     'C:/escape', '.git/config', '.phase1-restore.json', 'a/./b']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                restore.member_path(zipfile.ZipInfo(name))
        info = zipfile.ZipInfo('link')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            restore.member_path(info)

    def test_archive_preflight_rejects_traversal(self):
        self.archive('a.zip', {'../escape': 'x'})
        with self.assertRaises(ValueError):
            restore.verify_archives(self.root, self.manifest)
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_protected_and_nonempty_destinations(self):
        for dest in [restore.ROOT, restore.ROOT / 'raw', restore.ROOT.parent,
                     self.root / 'protected', self.root / 'protected/sub']:
            with self.subTest(dest=dest), self.assertRaises(ValueError):
                restore.validate_destination(dest, self.manifest)
        dest = self.root / 'nonempty'
        dest.mkdir()
        (dest / 'keep').write_text('important')
        with self.assertRaises(ValueError):
            restore.validate_destination(dest, self.manifest)
        self.assertEqual((dest / 'keep').read_text(), 'important')

    def test_symlink_destination(self):
        actual = self.root / 'actual'
        actual.mkdir()
        link = self.root / 'alias'
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            restore.validate_destination(link / 'child', self.manifest)


if __name__ == '__main__':
    unittest.main()
