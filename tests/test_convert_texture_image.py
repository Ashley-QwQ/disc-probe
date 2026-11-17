"""Safe converter publication; run with python -m unittest discover -s tests.

All images, outputs and injected partial writes live in temporary directories.
"""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "convert_texture_image.py"
SPEC = importlib.util.spec_from_file_location("convert_texture_image", SOURCE)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class ConvertTextureImageTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.image = self.root / "design.png"
        self.output = self.image.with_suffix(".npy")
        self.mapping = self.root / "map.json"
        # Deliberately use non-sorted keys: indices must follow JSON order,
        # not RGB order or texture names.
        self.mapping.write_text(json.dumps({
            "#0000ff": "92", "#ff0000": "A5"
        }), encoding="utf-8")
        with Image.new("RGB", (6000, 6000), "red") as image:
            image.putpixel((0, 0), (0, 0, 255))
            image.save(self.image)
        self.args = ["--image", str(self.image), "--map", str(self.mapping)]

    def convert(self):
        # Close Pillow handles even when the original parser raises.
        original_open = Image.open
        with contextlib.ExitStack() as stack:
            def open_image(*args, **kwargs):
                return stack.enter_context(original_open(*args, **kwargs))
            with mock.patch.object(converter.Image, "open", side_effect=open_image), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                converter.main(self.args)

    def seed_output(self):
        np.save(self.output, np.array([[17, 23]], dtype=np.int32))
        return self.output.read_bytes()

    def assert_no_temp_files(self):
        self.assertFalse(set(self.root.iterdir()) -
                         {self.image, self.mapping, self.output})

    def test_valid_conversion_with_and_without_existing_output(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.seed_output()
                self.convert()
                result = np.load(self.output, allow_pickle=False, mmap_mode="r")
                try:
                    self.assertEqual(result.shape, (6000, 6000))
                    self.assertEqual(result.dtype, np.dtype("int32"))
                    self.assertEqual(result[0, 0], 0)
                    self.assertEqual(np.count_nonzero(result), result.size - 1)
                    self.assertTrue(np.all(result[1:] == 1))
                finally:
                    result._mmap.close()
                self.assert_no_temp_files()
                self.output.unlink()

    def test_invalid_inputs_preserve_existing_output(self):
        for problem in ("missing_json", "invalid_json", "unmapped_color"):
            for existing in (False, True):
                with self.subTest(problem=problem, existing=existing):
                    self.mapping.write_text('{"#0000ff": "92", "#ff0000": "A5"}',
                                            encoding="utf-8")
                    before = self.seed_output() if existing else None
                    if problem == "missing_json":
                        self.mapping.unlink()
                        error = SystemExit
                    elif problem == "invalid_json":
                        self.mapping.write_text("{invalid", encoding="utf-8")
                        error = json.JSONDecodeError
                    else:
                        self.mapping.write_text('{"#0000ff": "92"}', encoding="utf-8")
                        error = Exception
                    with mock.patch.object(converter.np, "save") as save, \
                            mock.patch.object(tempfile, "NamedTemporaryFile") as temp:
                        with self.assertRaises(error) as raised:
                            self.convert()
                        if problem == "unmapped_color":
                            self.assertIn("Some colors were not properly mapped", str(raised.exception))
                        save.assert_not_called()
                        temp.assert_not_called()
                    if existing:
                        self.assertEqual(self.output.read_bytes(), before)
                        self.output.unlink()
                    else:
                        self.assertFalse(self.output.exists())
                    self.assert_no_temp_files()

    def test_io_failures_preserve_output_and_clean_temporary_file(self):
        def partial_write(file, array):
            self.assertEqual(Path(file.name).parent, self.output.parent)
            self.assertNotEqual(Path(file.name), self.output)
            file.write(b"incomplete npy")
            file.flush()
            raise OSError("injected write failure")

        for stage in ("create", "write", "replace"):
            for existing in (False, True):
                with self.subTest(stage=stage, existing=existing):
                    before = self.seed_output() if existing else None
                    if stage == "create":
                        patch = mock.patch.object(tempfile, "NamedTemporaryFile",
                                                  side_effect=OSError("injected create failure"))
                    elif stage == "write":
                        patch = mock.patch.object(converter.np, "save", side_effect=partial_write)
                    else:
                        patch = mock.patch.object(converter.Path, "replace",
                                                  side_effect=OSError("injected replace failure"))
                    with patch, self.assertRaisesRegex(OSError, "injected"):
                        self.convert()
                    if existing:
                        self.assertEqual(self.output.read_bytes(), before)
                        self.output.unlink()
                    else:
                        self.assertFalse(self.output.exists())
                    self.assert_no_temp_files()


if __name__ == "__main__":
    unittest.main()
