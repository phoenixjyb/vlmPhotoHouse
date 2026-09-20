"""Synthetic filesystem faults in the offline upload transfer primitive."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.access import promotion
from app.access.provisioning import PlanRejected


class PromotionTransferTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.source = self.root / 'source.png'
        self.destination = self.root / 'originals' / 'target.png'
        self.source.write_bytes(b'synthetic image bytes')

    def cross_device(self):
        link = os.link
        def simulate(source, destination):
            if Path(source) == self.source:
                raise OSError(errno.EXDEV, 'synthetic different device')
            return link(source, destination)
        return patch.object(promotion.os, 'link', side_effect=simulate)

    def test_same_device_and_cross_device_preserve_bytes(self):
        for cross_device in (False, True):
            with self.subTest(cross_device=cross_device):
                self.source.write_bytes(b'synthetic image bytes')
                context = self.cross_device() if cross_device else patch.object(promotion.os, 'link', wraps=os.link)
                with context:
                    promotion._place(self.source, self.destination)
                self.assertFalse(self.source.exists())
                self.assertEqual(self.destination.read_bytes(), b'synthetic image bytes')
                self.destination.unlink()
                self.assertEqual(list(self.destination.parent.iterdir()), [])

    def test_destination_created_after_preflight_is_not_overwritten(self):
        link = os.link
        def raced(source, destination):
            Path(destination).write_bytes(b'other original')
            return link(source, destination)
        with patch.object(promotion.os, 'link', side_effect=raced):
            with self.assertRaises(FileExistsError):
                promotion._place(self.source, self.destination)
        self.assertEqual(self.destination.read_bytes(), b'other original')
        self.assertEqual(self.source.read_bytes(), b'synthetic image bytes')

    def test_source_unlink_failure_removes_only_new_destination(self):
        for cross_device in (False, True):
            with self.subTest(cross_device=cross_device):
                unlink = os.unlink
                def refuse_source(path, *args, **kwargs):
                    if Path(path) == self.source:
                        raise PermissionError('synthetic source is busy')
                    return unlink(path, *args, **kwargs)
                context = self.cross_device() if cross_device else patch.object(promotion.os, 'link', wraps=os.link)
                with context, patch.object(promotion.os, 'unlink', side_effect=refuse_source):
                    with self.assertRaises(PermissionError):
                        promotion._place(self.source, self.destination)
                self.assertEqual(self.source.read_bytes(), b'synthetic image bytes')
                self.assertFalse(self.destination.exists())
                self.assertEqual(list(self.destination.parent.iterdir()), [])

    def test_cleanup_does_not_delete_replaced_destination(self):
        unlink = os.unlink
        def replaced(path, *args, **kwargs):
            if Path(path) == self.source:
                unlink(self.destination)
                self.destination.write_bytes(b'another file')
                raise PermissionError('synthetic source is busy')
            return unlink(path, *args, **kwargs)
        with patch.object(promotion.os, 'unlink', side_effect=replaced):
            with self.assertRaisesRegex(PlanRejected, 'manual recovery required'):
                promotion._place(self.source, self.destination)
        self.assertEqual(self.source.read_bytes(), b'synthetic image bytes')
        self.assertEqual(self.destination.read_bytes(), b'another file')

    def test_interrupted_copy_removes_private_partial_and_retains_source(self):
        def interrupt(source, destination):
            destination.write(b'partial')
            raise OSError('synthetic interrupted copy')
        with self.cross_device(), patch.object(promotion.shutil, 'copyfileobj', side_effect=interrupt):
            with self.assertRaises(OSError):
                promotion._place(self.source, self.destination)
        self.assertTrue(self.source.exists())
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.iterdir()), [])
