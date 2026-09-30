"""Window placement across monitors, and the --with-game entry point."""
import json
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard
import launcher

PRIMARY = (0, 0, 2560, 1400, True)
SECOND = (386, 1728, 2690, 3120, False)  # below the primary, like the user's laptop screen


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name) / 'window.json'
        patcher = patch.object(launcher, 'STATE_PATH', self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()
        self.dir.cleanup()

    def geometry(self):
        self.root.update_idletasks()
        return self.root.wm_geometry()

    def test_first_run_goes_to_the_second_screen(self):
        launcher.place(self.root, 1220, 860, [PRIMARY, SECOND])
        self.assertEqual(self.geometry(), '1220x860+426+1768')

    def test_only_one_screen_keeps_tk_default_position(self):
        launcher.place(self.root, 1220, 860, [PRIMARY])
        self.assertTrue(self.geometry().startswith('1220x860'))

    def test_last_spot_is_restored_while_its_screen_exists(self):
        self.state.write_text(json.dumps(dict(x=500, y=1800, width=1000, height=700, zoomed=False)))
        launcher.place(self.root, 1220, 860, [PRIMARY, SECOND])
        self.assertEqual(self.geometry(), '1000x700+500+1800')

    def test_last_spot_on_an_unplugged_screen_falls_back(self):
        self.state.write_text(json.dumps(dict(x=-3000, y=100, width=1000, height=700, zoomed=False)))
        launcher.place(self.root, 1220, 860, [PRIMARY, SECOND])
        self.assertEqual(self.geometry(), '1220x860+426+1768')

    def test_hidden_windows_are_not_remembered(self):
        launcher.remember(self.root)
        self.assertFalse(self.state.exists())

    def test_visible_window_is_remembered(self):
        self.root.attributes('-alpha', 0.0)
        self.root.geometry('900x600+120+140')
        self.root.deiconify()
        self.root.update()
        launcher.remember(self.root)
        saved = json.loads(self.state.read_text())
        self.assertEqual((saved['width'], saved['height']), (900, 600))


class WithGameTests(unittest.TestCase):
    def test_already_open_only_starts_the_game(self):
        with patch.object(sys, 'argv', ['dashboard', '--with-game']), \
                patch('dashboard.claim_single_instance', return_value=False), \
                patch('dashboard.start_game') as start, \
                patch('dashboard.tk.Tk', side_effect=AssertionError('no second window')):
            dashboard.main()
        start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
