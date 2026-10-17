"""File-picker cancellation, batch replacement, and staged native import; no device services."""

import contextlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from file_import import import_files, select_files
from profiles import Profile
from worker import WorkerError


def choice(key):
    return SimpleNamespace(key=key) if key else None


class FileImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.saved = self.root / 'english.state'
        self.saved.write_bytes(b'original memory')
        self.tool = self.root / 'blazie_files'
        self.tool.touch()
        self.profile = Profile('bl-en', 'English', self.root / 'fw', None, self.saved.name)
        self.worker = SimpleNamespace(saved=self.saved, request=Mock())
        self.dialogs = SimpleNamespace(request_file=Mock(), request_confirmation=Mock(return_value=False),
                                      show_message=Mock(), activity=lambda *a, **k: contextlib.nullcontext())
        self.paths = [self.root / 'story.txt', self.root / 'game.bns']
        self.window = object()

    def test_picker_multiple_files_duplicates_remove_and_shared_screen(self):
        dialogs = SimpleNamespace(request_file=Mock(side_effect=[self.paths[0], self.paths[0], self.paths[1]]),
                                  request_choice=Mock(side_effect=[choice(k) for k in ('a', 'a', 'r', '1', 'i')]))
        self.assertEqual(select_files(dialogs, stdscr=self.window), [self.paths[1]])
        for call in dialogs.request_file.call_args_list + dialogs.request_choice.call_args_list:
            self.assertIs(call.kwargs['stdscr'], self.window)
        self.assertEqual(dialogs.request_file.call_args.args[0], Path('/'))
        self.assertEqual(dialogs.request_file.call_args.kwargs['initial_dir'], self.root)

    def test_cancel_picker_or_batch_does_not_touch_worker(self):
        self.dialogs.request_file.return_value = None
        import_files(self.worker, self.dialogs, self.profile, self.tool)
        self.worker.request.assert_not_called()
        dialogs = SimpleNamespace(request_file=Mock(return_value=self.paths[0]), request_choice=Mock(return_value=None))
        self.assertEqual(select_files(dialogs), [])

    def test_conflict_declined_leaves_memory_and_removes_staging(self):
        with (patch('file_import.select_files', return_value=self.paths),
              patch('file_import.run_tool', return_value=subprocess.CompletedProcess([], 1, 'exists story.txt\n', '')) as tool):
            import_files(self.worker, self.dialogs, self.profile, self.tool)
        self.assertEqual(self.saved.read_bytes(), b'original memory')
        self.worker.request.assert_called_once_with('IMPORT_CHECK', 'SAVED')
        tool.assert_called_once()
        self.assertFalse(Path(str(self.saved) + '.import').exists())
        self.assertFalse(self.dialogs.request_confirmation.call_args.kwargs['default'])

    def test_success_uses_staging_then_worker_commit_and_retains_program_bank(self):
        Path(str(self.saved) + '.program').write_bytes(b'updated bank')
        def tool(executable, stage, paths, cp, **kwargs):
            self.assertEqual(stage.read_bytes(), b'original memory')
            self.assertEqual(Path(str(stage) + '.program').read_bytes(), b'updated bank')
            self.assertEqual(cp, 850)
            return subprocess.CompletedProcess([], 0, '2 added', '')
        with patch('file_import.select_files', return_value=self.paths), patch('file_import.run_tool', side_effect=tool):
            import_files(self.worker, self.dialogs, self.profile, self.tool, stdscr=self.window)
        self.assertEqual([c.args[0] for c in self.worker.request.call_args_list], ['IMPORT_CHECK', 'IMPORT_COMMIT'])
        self.assertEqual(self.saved.read_bytes(), b'original memory')  # Only the worker may commit.
        self.assertFalse(Path(str(self.saved) + '.import.program').exists())
        self.assertIn('Imported 2 files', self.dialogs.show_message.call_args.args[0])

    def test_busy_flash_or_failed_batch_never_commits(self):
        for busy in (False, True):
            with self.subTest(busy=busy):
                self.worker.request.reset_mock(side_effect=True)
                if busy:
                    self.worker.request.side_effect = WorkerError('flash busy')
                with (patch('file_import.select_files', return_value=self.paths),
                      patch('file_import.run_tool', return_value=subprocess.CompletedProcess([], 1, 'flash full', '')) as tool):
                    import_files(self.worker, self.dialogs, self.profile, self.tool)
                self.worker.request.assert_called_once_with('IMPORT_CHECK', 'SAVED')
                self.assertEqual(self.saved.read_bytes(), b'original memory')
                if busy:
                    tool.assert_not_called()

    def test_conflict_accepted_passes_replace_only_after_confirmation(self):
        self.dialogs.request_confirmation.return_value = True
        with (patch('file_import.select_files', return_value=self.paths), patch('file_import.run_tool', side_effect=[
                subprocess.CompletedProcess([], 1, 'exists story.txt\n', ''), subprocess.CompletedProcess([], 0, 'ok', '')]) as tool):
            import_files(self.worker, self.dialogs, self.profile, self.tool)
        self.assertTrue(tool.call_args.kwargs['replace'])
        self.worker.request.assert_called_with('IMPORT_COMMIT', 'IMPORTED')
