"""Exercise CPython security backports inside the shipped Linux container."""

from __future__ import annotations

import contextlib
import os
import poplib
import shutil
import stat
import tempfile
import unittest
from unittest import mock


@unittest.skipUnless(
    os.environ.get("JAMF_MCP_CONTAINER_SECURITY") == "1",
    "run in the built container with JAMF_MCP_CONTAINER_SECURITY=1",
)
class ContainerSecurityTests(unittest.TestCase):
    def client(self):
        client = poplib.POP3.__new__(poplib.POP3)
        client._debugging = 0
        client.encoding = "UTF-8"
        sent = []
        client._putline = sent.append
        return client, sent

    def test_pop3_rejects_control_characters_before_send(self):
        client, sent = self.client()
        for character in [chr(n) for n in range(32)] + [chr(127)]:
            for command in [f"USER name{character}QUIT", f"PASS {character}password"]:
                with self.subTest(command=repr(command)), self.assertRaises(ValueError):
                    client._putcmd(command)
        self.assertEqual(sent, [])

    def test_pop3_preserves_printable_commands(self):
        client, sent = self.client()
        client._putcmd("USER ordinary-user")
        client._putcmd("PASS ordinary password")
        self.assertEqual(sent, [b"USER ordinary-user", b"PASS ordinary password"])

    def test_tempfile_cleanup_symlink_race_preserves_outside_file(self):
        self.assertNotEqual(os.getuid(), 0, "permission-error trigger needs a nonroot user")
        self.assertTrue(shutil.rmtree.avoids_symlink_attacks)
        with tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "file")
            with open(target, "wb") as stream:
                stream.write(b"retain this content")
            original_mode = os.stat(target).st_mode
            temporary = tempfile.TemporaryDirectory()
            child = os.path.join(temporary.name, "child")
            os.mkdir(child)
            with open(os.path.join(child, "file"), "wb") as stream:
                stream.write(b"temporary")
            os.chmod(child, 0o500)
            unlink = os.unlink
            swaps = []

            def race(path, *, dir_fd=None):
                try:
                    return unlink(path, dir_fd=dir_fd)
                except PermissionError:
                    if not os.path.islink(child):
                        os.chmod(child, 0o700)
                        os.rename(child, child + "_moved")
                        os.symlink(outside, child)
                        swaps.append(True)
                    raise

            try:
                with mock.patch("os.unlink", race), contextlib.suppress(OSError):
                    temporary.cleanup()
                self.assertTrue(swaps, "race trigger did not run")
                self.assertTrue(os.path.exists(target), "outside file was deleted")
                self.assertEqual(os.stat(target).st_mode, original_mode)
                with open(target, "rb") as stream:
                    self.assertEqual(stream.read(), b"retain this content")
            finally:
                if os.path.islink(child):
                    os.unlink(child)
                if os.path.exists(child + "_moved"):
                    os.chmod(child + "_moved", 0o700)
                temporary.cleanup()

    def test_tempfile_permission_reset_does_not_follow_replaced_link(self):
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "outside")
            with open(target, "wb") as stream:
                stream.write(b"outside")
            os.chmod(target, 0o600)
            child = os.path.join(root, "child")
            os.mkdir(child)
            os.chmod(child, 0)
            parent_fd = os.open(root, os.O_RDONLY)
            real_chmod = os.chmod
            swaps = []

            def replace_before_chmod(path, mode, **kwargs):
                if path == "child" and kwargs.get("dir_fd") == parent_fd:
                    if not os.path.islink(child):
                        os.rename(child, child + "_moved")
                        os.symlink(target, child)
                        swaps.append(True)
                return real_chmod(path, mode, **kwargs)

            try:
                with mock.patch("os.open", side_effect=PermissionError), mock.patch(
                    "os.chmod", replace_before_chmod
                ), contextlib.suppress(OSError, NotImplementedError):
                    tempfile._resetperms_at("child", parent_fd, child)
                self.assertTrue(swaps, "replacement trigger did not run")
                self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
            finally:
                os.close(parent_fd)
                if os.path.islink(child):
                    os.unlink(child)
                if os.path.exists(child + "_moved"):
                    real_chmod(child + "_moved", 0o700)

    def test_tempfile_root_permission_reset_does_not_follow_replaced_link(self):
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "outside")
            with open(target, "wb") as stream:
                stream.write(b"outside")
            os.chmod(target, 0o600)
            child = os.path.join(root, "child")
            os.mkdir(child)
            real_chmod = os.chmod
            swaps = []

            def replace_before_chmod(path, mode, **kwargs):
                if path == child and not os.path.islink(child):
                    os.rename(child, child + "_moved")
                    os.symlink(target, child)
                    swaps.append(True)
                return real_chmod(path, mode, **kwargs)

            try:
                with mock.patch("os.chmod", replace_before_chmod), contextlib.suppress(
                    OSError, NotImplementedError
                ):
                    tempfile._resetperms(child)
                self.assertTrue(swaps)
                self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o600)
            finally:
                if os.path.islink(child):
                    os.unlink(child)

    def test_tempfile_cleanup_handles_unwritable_contents(self):
        temporary = tempfile.TemporaryDirectory()
        child = os.path.join(temporary.name, "child")
        os.mkdir(child)
        with open(os.path.join(child, "file"), "wb") as stream:
            stream.write(b"temporary")
        for mode in [0, stat.S_IRUSR | stat.S_IXUSR]:
            with self.subTest(mode=mode):
                os.chmod(child, mode)
                parent_fd = os.open(temporary.name, os.O_RDONLY)
                try:
                    tempfile._resetperms_at("child", parent_fd, child)
                finally:
                    os.close(parent_fd)
        os.chmod(child, 0)
        temporary.cleanup()
        self.assertFalse(os.path.exists(temporary.name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
